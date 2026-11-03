#!/usr/bin/env bash
# Run on the fresh GPU VM, not the n8n host. Ubuntu 24.04/26.04 amd64 only.
set -euo pipefail
umask 077
if [[ "${1:-}" == '--help' ]]; then
  echo 'Usage: sudo bash setup-nvidia-gpu-ollama.sh'
  echo 'Installs local GPU inference at https://192.0.2.181:11434; n8n client 192.0.2.180.'
  echo 'If NVIDIA drivers need installation, reboot when instructed and run this script again.'
  exit 0
fi
[[ $EUID -eq 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
source /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" =~ ^(24.04|26.04)$ && "$(uname -m)" == x86_64 ]] || {
  echo 'This script supports Ubuntu 24.04 or 26.04 amd64. Report your OS before adapting it.' >&2; exit 1;
}
python3 - <<'PY'
import json, subprocess
addresses=json.loads(subprocess.check_output(['ip','-j','address']))
assert any(a.get('local')=='192.0.2.181' for i in addresses for a in i.get('addr_info',[])), 'Run this on 192.0.2.181, not the n8n gateway.'
PY
ROOT=/opt/homelab-fast-ai
if [[ -e "$ROOT" && ! -f "$ROOT/.managed-by-setup" ]]; then
  echo "$ROOT already exists and is not managed by this script; stopping." >&2; exit 1
fi
install -d -m 700 "$ROOT" "$ROOT/tls"
touch "$ROOT/.managed-by-setup"
if command -v docker >/dev/null && docker info >/dev/null 2>&1; then
  foreign=$(docker ps --filter label=com.docker.compose.project!=homelab-fast-ai -q)
  [[ -z "$foreign" ]] || { echo 'Other containers are running. Stop and review before restarting Docker.' >&2; exit 1; }
fi
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=l
apt-get update
apt-get install -y ca-certificates curl gnupg openssl pciutils python3 ubuntu-drivers-common
lspci -nn | grep -qi NVIDIA || { echo 'No NVIDIA PCI device found. Configure GPU passthrough in Proxmox first.' >&2; exit 1; }
if ! nvidia-smi >/dev/null 2>&1; then
  if [[ -f "$ROOT/driver-install-attempted" ]]; then
    echo 'Driver still unavailable. Check GPU passthrough, Secure Boot/MOK enrollment and nvidia-smi after reboot.' >&2
    exit 1
  fi
  apt-get install -y "linux-headers-$(uname -r)"
  ubuntu-drivers install
  touch "$ROOT/driver-install-attempted"
  echo 'NVIDIA driver installed. Reboot this VM, then rerun the same script.'
  echo 'If Secure Boot requires MOK enrollment, complete it using the VM console.'
  exit 0
fi
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
if ! command -v docker >/dev/null; then
  apt-get install -y docker.io docker-compose-v2
elif ! docker compose version >/dev/null 2>&1; then
  echo 'Docker exists without Compose v2; install the matching Compose plugin, then rerun.' >&2; exit 1
fi
systemctl enable --now docker
curl --fail --silent --show-error --location https://nvidia.github.io/libnvidia-container/gpgkey -o "$ROOT/nvidia-key.asc"
gpg --batch --yes --dearmor -o /usr/share/keyrings/homelab-nvidia-toolkit.gpg "$ROOT/nvidia-key.asc"
chmod 644 /usr/share/keyrings/homelab-nvidia-toolkit.gpg
curl --fail --silent --show-error --location https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list -o "$ROOT/nvidia-toolkit.list"
sed 's#deb https://#deb [signed-by=/usr/share/keyrings/homelab-nvidia-toolkit.gpg] https://#g' "$ROOT/nvidia-toolkit.list" > /etc/apt/sources.list.d/homelab-nvidia-toolkit.list
chmod 644 /etc/apt/sources.list.d/homelab-nvidia-toolkit.list
apt-get update
apt-get install -y nvidia-container-toolkit
if [[ -f /etc/docker/daemon.json && ! -f "$ROOT/docker-daemon.before.json" ]]; then
  cp -a /etc/docker/daemon.json "$ROOT/docker-daemon.before.json"
fi
nvidia-ctk runtime configure --runtime=docker
systemctl restart docker
python3 - <<'PY'
from pathlib import Path
import json, secrets, subprocess
p=Path('/opt/homelab-fast-ai')
if not (p/'api-token').exists():
 (p/'api-token').write_text(secrets.token_hex(32)+'\n')
(p/'api-token').chmod(0o600)
token=(p/'api-token').read_text().strip()
assert len(token)==64 and all(c in '0123456789abcdef' for c in token)
mem=int(subprocess.check_output(['nvidia-smi','--query-gpu=memory.total','--format=csv,noheader,nounits'],text=True).splitlines()[0])
model='qwen3:8b' if mem>=14000 else 'qwen3:4b'
if not (p/'model-name').exists(): (p/'model-name').write_text(model+'\n')
(p/'nginx.conf').write_text('''map $http_authorization $authorized {
    default 0;
    "Bearer TOKEN" 1;
}
server {
    listen 11434 ssl;
    server_name 192.0.2.181;
    ssl_certificate /etc/nginx/tls/server.crt;
    ssl_certificate_key /etc/nginx/tls/server.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    allow 192.0.2.180;
    allow 192.0.2.181;
    deny all;
    if ($authorized = 0) { return 401; }
    client_max_body_size 8m;
    location ~ ^/(api/(chat|generate|tags|show|ps|embed|embeddings|version)|v1/(chat/completions|completions|models|embeddings))$ {
        proxy_pass http://ollama:11434;
        proxy_http_version 1.1;
        proxy_set_header Authorization "";
        proxy_set_header Host $host;
        proxy_buffering off;
        proxy_read_timeout 600s;
    }
    location / { return 403; }
}
'''.replace('TOKEN',token))
(p/'client.curl').write_text('cacert = "/opt/homelab-fast-ai/tls/server.crt"\nheader = "Authorization: Bearer '+token+'"\n')
(p/'client.curl').chmod(0o600)
# Resolve first-install image tags to immutable digests. Reruns preserve those versions.
if not (p/'images.json').exists():
 images={}
 for role,tag in [('ollama','ollama/ollama:latest'),('proxy','nginx:stable-alpine')]:
  subprocess.run(['docker','pull',tag],check=True)
  images[role]=json.loads(subprocess.check_output(['docker','image','inspect',tag]))[0]['RepoDigests'][0]
 (p/'images.json').write_text(json.dumps(images,indent=2)+'\n')
images=json.loads((p/'images.json').read_text())
(p/'compose.yaml').write_text('''name: homelab-fast-ai
services:
  ollama:
    image: OLLAMA_IMAGE
    restart: unless-stopped
    gpus: all
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
      OLLAMA_CONTEXT_LENGTH: 4096
      OLLAMA_NUM_PARALLEL: 1
      OLLAMA_MAX_LOADED_MODELS: 1
      OLLAMA_KEEP_ALIVE: 10m
      OLLAMA_NO_CLOUD: '1'
    volumes: [models:/root/.ollama]
    networks: [inference]
    healthcheck:
      test: [CMD, ollama, list]
      interval: 10s
      timeout: 5s
      retries: 30
  proxy:
    image: PROXY_IMAGE
    restart: unless-stopped
    ports: ["192.0.2.181:11434:11434"]
    volumes:
      - ./nginx.conf:/etc/nginx/conf.d/default.conf:ro
      - ./tls:/etc/nginx/tls:ro
    networks: [inference]
    depends_on:
      ollama:
        condition: service_healthy
    security_opt: [no-new-privileges:true]
volumes:
  models:
networks:
  inference:
'''.replace('OLLAMA_IMAGE',images['ollama']).replace('PROXY_IMAGE',images['proxy']))
print('Generated protected credentials and configuration without printing secrets.')
PY
if [[ ! -f "$ROOT/tls/server.crt" ]]; then
  openssl req -x509 -newkey rsa:3072 -nodes -days 365 \
    -keyout "$ROOT/tls/server.key" -out "$ROOT/tls/server.crt" \
    -subj /CN=192.0.2.181 -addext subjectAltName=IP:192.0.2.181
fi
chmod 600 "$ROOT/tls/server.key"
cd "$ROOT"
docker compose config --quiet
docker compose up -d --wait --wait-timeout 180
docker compose exec -T ollama nvidia-smi
model=$(cat model-name)
docker compose exec -T ollama ollama pull "$model"
MODEL_NAME="$model" python3 - <<'PY'
from pathlib import Path
import json, os
Path('smoke-request.json').write_text(json.dumps({'model':os.environ['MODEL_NAME'],'messages':[{'role':'user','content':'Reply with exactly: ready'}],'think':False,'stream':False,'options':{'num_ctx':4096,'num_predict':24}}))
PY
status=$(curl --silent --show-error --cacert tls/server.crt -o /dev/null -w '%{http_code}' https://192.0.2.181:11434/api/tags)
[[ "$status" == 401 ]] || { echo "Authentication check failed: expected 401, got $status" >&2; exit 1; }
curl --fail --silent --show-error --max-time 600 --config client.curl \
  -H 'Content-Type: application/json' --data-binary @smoke-request.json \
  https://192.0.2.181:11434/api/chat > smoke-response.json
python3 - <<'PY'
import json
r=json.load(open('smoke-response.json'))
assert r.get('done') and r.get('message',{}).get('content'), 'Inference did not complete'
print('Authenticated HTTPS inference succeeded.')
PY
docker compose exec -T ollama ollama ps
# Verify that the loaded model actually allocated GPU memory, rather than accepting CPU fallback.
curl --fail --silent --show-error --config client.curl https://192.0.2.181:11434/api/ps > loaded-models.json
python3 - <<'PY'
import json
models=json.load(open('loaded-models.json')).get('models',[])
assert any(m.get('size_vram',0)>0 for m in models), 'No GPU allocation detected; inspect Ollama logs.'
print('GPU memory allocation verified.')
PY
printf '\nReady: https://192.0.2.181:11434\nModel: %s\n' "$model"
echo 'API token: /opt/homelab-fast-ai/api-token (root-only; enter into n8n Credentials, never chat)'
echo 'Public certificate: /opt/homelab-fast-ai/tls/server.crt (copy to n8n host to establish TLS trust)'
echo 'Access allowed only from 192.0.2.180 and this VM. Model administration stays local.'
echo 'For fast generation use think:false in /api/chat or /api/generate requests.'
openssl x509 -in tls/server.crt -noout -fingerprint -sha256
