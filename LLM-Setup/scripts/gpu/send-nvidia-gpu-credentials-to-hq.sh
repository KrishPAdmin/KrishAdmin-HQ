#!/usr/bin/env bash
# Run as your normal login user on 192.0.2.181.
set -euo pipefail
sudo test -s /opt/homelab-fast-ai/api-token
sudo test -s /opt/homelab-fast-ai/tls/server.crt
ssh krishadmin@192.0.2.180 'mkdir -p /home/operator/n8n/incoming; chmod 700 /home/operator/n8n/incoming'
sudo cat /opt/homelab-fast-ai/api-token | ssh krishadmin@192.0.2.180 'umask 077; cat > /home/operator/n8n/incoming/nvidia-gpu-token'
sudo cat /opt/homelab-fast-ai/tls/server.crt | ssh krishadmin@192.0.2.180 'umask 077; cat > /home/operator/n8n/incoming/nvidia-gpu-server.crt'
echo 'Token and public certificate transferred securely. No private TLS key was transferred.'
