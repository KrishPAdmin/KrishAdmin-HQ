#!/usr/bin/env bash
#
# One‑shot installer / re‑installer for qBittorrent (LinuxServer.io image)
# – Always pulls the newest image (--pull always)
# – Creates folders, removes old container, and launches the new one
# – Prints the temporary Web‑UI password on first start
# ------------------------------------------------------------

set -euo pipefail

### ---- adjustable vars --------------------------------------
USER_NAME="$(whoami)"                   # UNIX user running Docker
DATA_DIR="/home/${USER_NAME}/docker/qbittorrent"
DOWNLOAD_DIR="/home/${USER_NAME}/media"
CONTAINER="qbittorrent"
TIMEZONE="America/Toronto"
WEBUI_PORT="8080"
IMAGE="lscr.io/linuxserver/qbittorrent:latest"   # always the latest tag
### -----------------------------------------------------------

echo "➤ Creating local folders …"
mkdir -p "${DATA_DIR}" "${DOWNLOAD_DIR}"

echo "➤ Removing any old container …"
docker rm -f "${CONTAINER}" 2>/dev/null || true

echo "➤ Pulling & starting the latest qBittorrent image …"
docker run --pull always -d \
  --name="${CONTAINER}" \
  -e PUID="$(id -u "${USER_NAME}")" \
  -e PGID="$(id -g "${USER_NAME}")" \
  -e TZ="${TIMEZONE}" \
  -e WEBUI_PORT="${WEBUI_PORT}" \
  -p "${WEBUI_PORT}:${WEBUI_PORT}" \
  -p 6881:6881 \
  -p 6881:6881/udp \
  -v "${DATA_DIR}":/config \
  -v "${DOWNLOAD_DIR}":/downloads \
  --restart unless-stopped \
  "${IMAGE}"

echo -e "\n➤ Waiting a few seconds for first‑start log …"
sleep 5

echo "------------------------------------------------------------"
docker logs "${CONTAINER}" 2>&1 | grep -i 'temporary password' || true
echo "------------------------------------------------------------"
echo "Visit http://<server‑ip>:${WEBUI_PORT} — user: admin, pw above."
echo "Immediately change it in Preferences → Web UI → Authentication."
