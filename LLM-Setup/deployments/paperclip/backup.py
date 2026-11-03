#!/usr/bin/env python3
"""Create a private database dump and matching instance/config archive."""
import datetime
import io
import os
from pathlib import Path
import subprocess
import tarfile

root = Path(__file__).resolve().parent
def archive_filter(member):
    # The coordinated dump supersedes application-generated database backups.
    parts = Path(member.name).parts
    if (len(parts) >= 5 and parts[:2] == ("data", "instances")
            and parts[3:5] == ("data", "backups")):
        return None
    if member.name == "worker-secrets/codex-worker-bridge-token":
        return None
    if "__pycache__" in parts:
        return None
    return member


os.umask(0o077)
destination = root / "backups" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
destination.mkdir(parents=True, exist_ok=False)
with (destination / "database.dump").open("wb") as output:
    subprocess.run(["sudo", "-n", "docker", "compose", "exec", "-T", "db", "pg_dump",
                    "-U", "paperclip", "-d", "paperclip", "-Fc"], cwd=root, stdout=output, check=True)
with tarfile.open(destination / "instance.tar.gz", "w:gz") as archive:
    for name in (".env", "admin-credentials.json", "compose.yaml", "nginx.conf", "agents",
                 "instance.json", "data", "validation", "seed.py", "admin_api.py", "backup.py",
                 "test_runtime.py", "test_department.py", "test_operations.py", "test_review_details.py", "test_control_center.py", "control-center", "codex-isolated", "enrich_pending_reviews.py", "setup_department.py", "setup_operations.py", "operations", "README.md", "pi-worker", "worker-secrets", "worker-workspaces"):
        if (root / name).exists():
            archive.add(root / name, arcname=name, filter=archive_filter)
    for unit in ('paperclip-observations.service', 'paperclip-observations.timer'):
        path = Path.home() / '.config/systemd/user' / unit
        if path.exists(): archive.add(path, arcname='systemd-user/' + unit)
    # Read-only host observation SSH identities are required to restore the same coverage.
    for name in ('krishadmin-hq-nvidia-gpu', 'krishadmin-hq-amd-gpu', 'known_hosts'):
        path = Path.home() / '.ssh' / name
        if path.exists(): archive.add(path, arcname='observation-ssh/' + name)
    # These controller files are root-only; stream them into the already-private archive without printing values.
    for private in ('codex-worker-auth/auth.json', 'codex-worker-auth/config.toml', 'worker-secrets/codex-worker-bridge-token'):
        path = root / private
        exists = subprocess.run(['sudo', '-n', 'test', '-f', str(path)], check=False).returncode == 0
        if exists:
            data = subprocess.check_output(['sudo', '-n', 'cat', str(path)])
            info = tarfile.TarInfo(private); info.size = len(data); info.mode = 0o600; info.uid = 0; info.gid = 0
            archive.addfile(info, io.BytesIO(data))
    # Retain the exact external client secrets and TLS material needed on a replacement HQ.
    for name, path in {
        "amd-gpu-api.txt": root.parent.parent / "secrets/amd-gpu-api.txt",
        "nvidia-gpu-api.txt": root.parent.parent / "secrets/nvidia-gpu-api.txt",
        "nvidia-gpu-server.crt": root.parent.parent / "secrets/nvidia-gpu-server.crt",
        "hq-server.crt": root.parent / "n8n/tls/server.crt",
        "hq-server.key": root.parent / "n8n/tls/server.key",
    }.items():
        archive.add(path, arcname="external-secrets/" + name)
print(destination)
