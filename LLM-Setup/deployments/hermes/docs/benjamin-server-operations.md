# Benjamin — Suits Server Operations Engineer

Benjamin owns new server operations requests, infrastructure investigations and the homelab credential catalog. Harvey manages priorities; Donna routes requests; Louis supervises coding implementation. Existing scheduled jobs keep their current runners. Assign a server request with `hq_task action=submit kind=server_ops agent=benjamin`. Coding still uses `kind=coding`.

## Enroll a password or API token

In a private SSH terminal on HQ, run:

```bash
sudo hq-vault enroll my-service
```

Enter the service, its purpose, endpoint (no credentials or URL query), account username, and authentication type (`password` or `api-token`). Enter and confirm the secret at the hidden prompt. Descriptions are visible to Benjamin; put secret values only in the hidden field. Never put them in command arguments, Discord, Paperclip or GitHub.

The command stores the value and metadata in encrypted OpenBao KV, preserves metadata during subsequent secret updates, uses version checks to avoid concurrent overwrites, and atomically refreshes a directory containing only allowlisted non-secret fields. This catalog lives at `/var/lib/hq-vault-catalog/services.json`; secrets remain in `/var/lib/openbao`, outside the Codex directory. Root-owned operator tooling writes the vault. Benjamin can read the catalog and use fixed connectors, but cannot retrieve raw vault values or write arbitrary vault entries.

Then tell him: **Benjamin, use `homelab/my-service` for [purpose]. Check whether its connector is ready.**

A new entry is stored securely but does not create a connector automatically. Its catalog entry says connector setup required. Existing Pi-cluster/monitoring, AMD-GPU SSH and two GPU API entries are connected. GPU API credentials also remain available to the existing trusted inference runtime; this is not a guarantee that arbitrary worker code cannot access those runtime tokens.

## Actual operations

Inside Benjamin's worker:

```bash
python3 /opt/worker/server_ops.py catalog
python3 /opt/worker/server_ops.py status
python3 /opt/worker/server_ops.py homelab
python3 /opt/worker/server_ops.py diagnostics --target amd-gpu --check gpu
```

`homelab` reads all three Pi hosts, Swarm nodes/services and Uptime Kuma. Diagnostics permit hq/nvidia-gpu/amd-gpu and overview/gpu/processes/services/storage only. The dedicated Benjamin identity can call only this fixed route. No arbitrary command, vault retrieval, task creation or inference endpoint is granted by that identity. The host connectors authenticate internally and return observations. Tool and model execution remains on HQ; AMD-GPU is compute-only except for owner-authorized fixed diagnostics.

Server writes need an implemented operation and authorization covering its effect. Existing owner-facing Pi deployment/restart tools remain separate; Benjamin's new connector is read-only. Do not claim that assigning ownership grants unrestricted host administration.

## Security and recovery

Unattended startup uses host-protected systemd encrypted credentials, as selected by the owner. This trusts the HQ host administrator and does not protect against a fully compromised host or unlocked disk. The connector socket is created by systemd socket activation, outside the vault service mount namespace, so AppArmor-protected user collectors can connect without disabling their hardening. Only root and the trusted host account can use it; it is not mounted into model containers.

GitHub receives source, templates, documentation and tests only. Vault databases, encrypted unlock material, audit logs, credentials, private service catalogs and runtime state are excluded. Encrypted vault snapshots are a separate backup, requiring independent recovery-key custody. A source snapshot is not a full disaster-recovery backup.
