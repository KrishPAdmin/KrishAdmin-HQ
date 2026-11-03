#!/usr/bin/env bash
# Public-key encrypted backup. Private recovery keys belong on the admin machine.
set -euo pipefail
umask 077
root=/home/operator/krishadmin-hq
recipients="$root/config/backup-recipients.txt"
if [[ ! -s "$recipients" ]]; then
  echo "Missing PUBLIC age recipient file: $recipients" >&2
  echo 'Follow docs/credential-security.md; do not copy a private recovery key here.' >&2
  exit 1
fi
[[ $EUID -eq 0 ]] || { echo 'Run with sudo to access Docker and protected backup files.' >&2; exit 1; }
command -v age >/dev/null
printf 'recipient-validation' | age -R "$recipients" > /dev/null
cd "$root/deployments/n8n"
docker compose config --quiet
backup_dir="$root/reports/encrypted-backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
restore_services() {
  previous_status=$?
  trap - EXIT
  if ! docker compose up -d --wait --wait-timeout 120 > /dev/null; then
    echo 'Backup finished or failed, but service restart needs attention.' >&2
    exit 1
  fi
  exit "$previous_status"
}
# This script expects the normal deployment to be running and restores that state.
if [[ "$(docker compose ps --status running --services | wc -l)" -ne 4 ]]; then
  echo 'Expected all four deployment services running; start/review the stack first.' >&2
  exit 1
fi
trap restore_services EXIT
docker compose stop proxy runners n8n
docker compose exec -T postgres pg_dump -U postgres -d n8n -Fc |
  age -R "$recipients" -o "$backup_dir/database.dump.age.partial"
mv "$backup_dir/database.dump.age.partial" "$backup_dir/database.dump.age"
docker compose run --rm --no-deps -T --entrypoint tar n8n -C /home/node/.n8n -cf - . |
  age -R "$recipients" -o "$backup_dir/n8n-data.tar.age.partial"
mv "$backup_dir/n8n-data.tar.age.partial" "$backup_dir/n8n-data.tar.age"
extra=()
if [[ -d trust ]]; then extra+=(trust); fi
tar -czf - .env compose.yaml init-db.sh nginx.conf tls README.md images.lock.txt backup.sh workflows portal connect-nvidia-gpu.py "${extra[@]}" |
  age -R "$recipients" -o "$backup_dir/deployment-secrets.tar.gz.age.partial"
mv "$backup_dir/deployment-secrets.tar.gz.age.partial" "$backup_dir/deployment-secrets.tar.gz.age"
cat > "$backup_dir/RESTORE.txt" <<'TXT'
All three archives are encrypted to the configured age recipient(s).
Use your separately stored private age identity on a trusted recovery machine:
  age -d -i PRIVATE-IDENTITY -o database.dump database.dump.age
  age -d -i PRIVATE-IDENTITY -o n8n-data.tar n8n-data.tar.age
  age -d -i PRIVATE-IDENTITY -o deployment-secrets.tar.gz deployment-secrets.tar.gz.age
Restore the configuration/secrets with restrictive permissions, restore the database
and n8n volume on an isolated host, and test login, credential decryption and a harmless
workflow. The original instance encryption key is required for existing credentials.
Do not copy decrypted secrets into shared folders. Keep an independent recovery copy
of the n8n instance encryption key under separate access controls.
TXT
printf 'Encrypted backup completed: %s\n' "$backup_dir"
