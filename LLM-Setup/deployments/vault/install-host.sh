#!/bin/bash
set -euo pipefail
src=/home/operator/krishadmin-hq/deployments/vault
getent passwd hq-vault >/dev/null || useradd --system --home /var/lib/openbao --shell /usr/sbin/nologin hq-vault
install -m 0755 "$src/downloads/bao" /usr/local/bin/bao
install -d -m 0750 -o root -g hq-vault /etc/openbao
install -d -m 0700 -o hq-vault -g hq-vault /var/lib/openbao /var/log/openbao
install -d -m 0700 /etc/hq-vault /var/lib/private/hq-vault-recovery
if [ ! -f /etc/openbao/tls.key ]; then
 openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 365 -subj '/CN=HQ Local Vault' -addext 'subjectAltName=IP:127.0.0.1,DNS:localhost' -keyout /etc/openbao/tls.key -out /etc/openbao/tls.crt 2>/dev/null
fi
chown root:hq-vault /etc/openbao/tls.key /etc/openbao/tls.crt
chmod 0640 /etc/openbao/tls.key
chmod 0644 /etc/openbao/tls.crt
cat > /etc/openbao/openbao.hcl <<'HCL'
ui = false
disable_mlock = true
api_addr = "https://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"
storage "raft" {
  path = "/var/lib/openbao"
  node_id = "hq-vault"
}
listener "tcp" {
  address = "127.0.0.1:8200"
  tls_cert_file = "/etc/openbao/tls.crt"
  tls_key_file = "/etc/openbao/tls.key"
  tls_min_version = "tls12"
}
audit "file" "local" {
  options { file_path = "/var/log/openbao/audit.jsonl" }
}
HCL
chown root:hq-vault /etc/openbao/openbao.hcl
chmod 0640 /etc/openbao/openbao.hcl
cat > /etc/systemd/system/hq-openbao.service <<'UNIT'
[Unit]
Description=HQ encrypted homelab credential vault
After=network-online.target
Wants=network-online.target
[Service]
User=hq-vault
Group=hq-vault
ExecStart=/usr/local/bin/bao server -config=/etc/openbao/openbao.hcl
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
PrivateDevices=true
ReadWritePaths=/var/lib/openbao /var/log/openbao
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
CapabilityBoundingSet=
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
LockPersonality=true
UMask=0077
MemorySwapMax=0
LimitCORE=0
[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now hq-openbao.service
