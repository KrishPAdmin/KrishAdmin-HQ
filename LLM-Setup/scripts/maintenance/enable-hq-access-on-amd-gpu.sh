#!/usr/bin/env bash
set -euo pipefail
if [[ "$(id -un)" != krishadmin ]]; then echo 'Run as krishadmin on the AMD-GPU host, without sudo.' >&2; exit 1; fi
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
key='from="198.51.100.21",no-agent-forwarding,no-port-forwarding,no-X11-forwarding,no-pty ssh-ed25519 REPLACE_WITH_YOUR_OBSERVER_PUBLIC_KEY krishadmin-hq-openwebui-management '
key="${key% }"
touch "$HOME/.ssh/authorized_keys"
chmod 600 "$HOME/.ssh/authorized_keys"
if ! grep -qxF "$key" "$HOME/.ssh/authorized_keys"; then printf '%s\n' "$key" >> "$HOME/.ssh/authorized_keys"; fi
echo 'HQ access enabled only from 198.51.100.21; forwarding and PTY disabled.'
echo 'Public host-key fingerprint (safe to share):'
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
