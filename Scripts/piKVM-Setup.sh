#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
PiKVM hardening script: change default passwords + hostname + Web UI display name.

USAGE (recommended, interactive passwords):
  sudo ./pikvm-harden.sh --hostname pikvm01.local --ui-name pikvm01.local

USAGE (non-interactive passwords, beware shell history):
  sudo ./pikvm-harden.sh \
    --hostname pikvm01.local \
    --ui-name pikvm01.local \
    --root-pass 'NEW_ROOT_PASSWORD' \
    --kvm-pass  'NEW_WEBUI_PASSWORD'

Optional: create a new Web UI user and (optionally) delete the default admin:
  sudo ./pikvm-harden.sh \
    --hostname pikvm01.local \
    --ui-name pikvm01.local \
    --create-kvm-user krish \
    --create-kvm-pass 'NEW_WEBUI_PASSWORD' \
    --delete-default-admin

Options:
  --hostname <name>            Sets system hostname (hostnamectl set-hostname ...)
  --ui-name <name>             Updates /etc/kvmd/meta.yaml for the name shown in Web UI
  --root-pass <pass>           Sets Linux root password (non-interactive)
  --kvm-user <user>            Web UI user to update (default: admin)
  --kvm-pass <pass>            Web UI password to set (non-interactive)
  --create-kvm-user <user>     Create an additional Web UI user (kvmd-htpasswd add)
  --create-kvm-pass <pass>     Password for the created Web UI user (non-interactive)
  --delete-default-admin       Deletes the default Web UI user "admin" (only when creating a new user)
  --reboot                     Reboot at the end
EOF
}

HOSTNAME=""
UI_NAME=""
ROOT_PASS=""
KVM_USER="admin"
KVM_PASS=""
NEW_KVM_USER=""
NEW_KVM_PASS=""
DEL_ADMIN=0
DO_REBOOT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --hostname) HOSTNAME="$2"; shift 2 ;;
    --ui-name) UI_NAME="$2"; shift 2 ;;
    --root-pass) ROOT_PASS="$2"; shift 2 ;;
    --kvm-user) KVM_USER="$2"; shift 2 ;;
    --kvm-pass) KVM_PASS="$2"; shift 2 ;;
    --create-kvm-user) NEW_KVM_USER="$2"; shift 2 ;;
    --create-kvm-pass) NEW_KVM_PASS="$2"; shift 2 ;;
    --delete-default-admin) DEL_ADMIN=1; shift ;;
    --reboot) DO_REBOOT=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
  esac
done

if [[ $(id -u) -ne 0 ]]; then
  echo "ERROR: Run as root (use sudo)." >&2
  exit 1
fi

if [[ -z "$HOSTNAME" ]]; then
  echo "ERROR: Missing --hostname" >&2
  usage
  exit 1
fi

if [[ -z "$UI_NAME" ]]; then
  UI_NAME="$HOSTNAME"
fi

echo "[1/5] Switching filesystem to RW mode (PiKVM defaults to RO)..."
rw
trap 'echo "[*] Switching filesystem back to RO mode..."; ro' EXIT

echo "[2/5] Setting system hostname to: $HOSTNAME"
hostnamectl set-hostname "$HOSTNAME"

echo "[3/5] Updating /etc/kvmd/meta.yaml (name shown in Web UI)..."
python3 - "$UI_NAME" <<'PY'
import sys, os, re

host = sys.argv[1]
path = "/etc/kvmd/meta.yaml"

lines = []
if os.path.exists(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.read().splitlines()

out = []
in_server = False
server_found = False
host_done = False

for line in lines:
    if re.match(r'^\s*server:\s*$', line):
        server_found = True
        in_server = True
        out.append(line)
        continue

    if in_server:
        # Server block ends when a new top-level key starts (non-indented, non-comment)
        if line.strip() and not line.startswith("    ") and not line.lstrip().startswith("#"):
            if not host_done:
                out.append(f"    host: {host}")
                host_done = True
            in_server = False
            out.append(line)
            continue

        # Replace existing host line inside server block
        if re.match(r'^\s{4}host:\s*', line):
            out.append(f"    host: {host}")
            host_done = True
            continue

    out.append(line)

if in_server and not host_done:
    out.append(f"    host: {host}")
    host_done = True

if not server_found:
    if out and out[-1].strip() != "":
        out.append("")
    out.append("server:")
    out.append(f"    host: {host}")

with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(out).rstrip() + "\n")
PY

echo "[4/5] Changing Linux OS root password..."
if [[ -n "$ROOT_PASS" ]]; then
  echo "root:${ROOT_PASS}" | chpasswd
  echo "  root password updated."
else
  echo "  No --root-pass provided, running interactive: passwd root"
  passwd root
fi

echo "[5/5] Changing Web UI (KVM) credentials..."
if [[ -n "$NEW_KVM_USER" ]]; then
  echo "  Creating Web UI user: $NEW_KVM_USER"
  if [[ -n "$NEW_KVM_PASS" ]]; then
    printf "%s\n%s\n" "$NEW_KVM_PASS" "$NEW_KVM_PASS" | kvmd-htpasswd add "$NEW_KVM_USER"
  else
    kvmd-htpasswd add "$NEW_KVM_USER"
  fi

  if [[ $DEL_ADMIN -eq 1 ]]; then
    echo "  Deleting default Web UI user: admin"
    kvmd-htpasswd del admin
  fi
else
  echo "  Updating Web UI password for user: $KVM_USER"
  if [[ -n "$KVM_PASS" ]]; then
    printf "%s\n%s\n" "$KVM_PASS" "$KVM_PASS" | kvmd-htpasswd set "$KVM_USER"
  else
    kvmd-htpasswd set "$KVM_USER"
  fi
fi

echo ""
echo "Done."
echo "  System hostname: $HOSTNAME"
echo "  Web UI display name: $UI_NAME"
echo ""

if [[ $DO_REBOOT -eq 1 ]]; then
  echo "[*] Switching filesystem back to RO mode before reboot..."
  ro
  trap - EXIT
  echo "[*] Rebooting..."
  reboot
else
  echo "Recommended next step: reboot (to apply hostname everywhere)"
fi
