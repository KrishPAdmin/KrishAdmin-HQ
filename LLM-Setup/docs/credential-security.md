# Local credential security for KrishAdmin-HQ

## Recommendation

For the strongest practical isolation in this lab, use a dedicated local secrets VM (OpenBao or a supported self-hosted Vault service) plus a small, restricted execution service. n8n should invoke named operations such as `get_proxmox_health` or `run_network_audit`; the execution service retrieves the required credential and contacts the device. The LLM receives filtered evidence, never the password or vault token. Put the secrets service on a management network, outside the n8n VM, with TLS, restrictive firewall rules and separate recovery access.

No system can guarantee secrecy after compromise of every machine authorized to use its credentials. Encryption at rest protects stored data, not a compromised running n8n instance or a privileged hypervisor administrator. A vault improves access control, auditability and separation; it does not remove the need for a protected initial machine identity.

## Options

| Option | Benefits | Limitations |
|---|---|---|
| Current n8n Credentials | Local encrypted database; simple; appropriate for scoped Ollama/API tokens | Host/n8n administrators can use credentials; workflows with credential access can misuse them |
| Local Vault with n8n native External Secrets | Central policies and rotation; secrets resolve in credential fields | Native integration requires n8n Enterprise; a compromised n8n instance can still use authorized secrets |
| OpenBao + restricted execution service | Device credentials stay outside n8n and the LLM; works without assuming an Enterprise secrets feature | Additional service to build, secure, monitor and recover; adapter integration is required |

OpenBao is not listed as a native n8n provider. Do not assume its compatibility with n8n's Vault integration without testing. Do not fetch passwords with ordinary HTTP nodes and pass them along as workflow item data: this can put secrets in execution results and prompts.

Official n8n availability/provider reference: https://docs.n8n.io/administer/manage-credentials/use-external-secret-stores
OpenBao AppRole: https://openbao.org/docs/auth/approle/
OpenBao audit devices: https://openbao.org/docs/audit/

## Store the NVIDIA-GPU Ollama token now

Open https://192.0.2.180 and go to Credentials -> Add credential -> Header Auth.

- Credential name: `KrishAdmin-HQ | nvidia-gpu API`
- Header name: `Authorization`
- Header value: `Bearer YOUR_TOKEN` (enter the actual token only inside the credential field)

Select that credential on the AI Router's `nvidia-gpu | Fast` HTTP node. Its URL is `https://192.0.2.181:11434/api/chat`.

For an Ollama-specific credential instead, use Base URL `https://192.0.2.181:11434` and API Key equal to the token alone. That credential is for Ollama nodes, while the existing router uses Header Auth on HTTP Request nodes.

The trusted public certificate must also be installed in n8n. Transfer only `/opt/homelab-fast-ai/tls/server.crt`; the private key stays on the GPU VM. Do not disable TLS checks. An alternative is the prepared SSH transfer helper and `deployments/n8n/connect-nvidia-gpu.py`, which imports the token directly into encrypted n8n storage and then removes its temporary incoming copy. Never send tokens through assistant chat, workflow JSON, prompts, source control or query strings.

## Device identities for authenticated analysis

- Proxmox: dedicated `krishadmin-audit@pve` account, privilege-separated API token, and PVEAuditor on only the required paths. Both user and token need appropriate ACLs; their effective privileges are intersected. Start with read-only cluster/VM/storage queries.
- UniFi: dedicated account or API key with the narrowest supported read permissions for your installed version. Read inventory, uplinks, port errors and events; keep configuration-changing credentials separate.
- Synology: dedicated monitoring account with only required DSM/API permissions; no access to unrelated shared files. Confirm API/version requirements before assigning privileges.
- Raspberry Pis: dedicated SSH user/key with fixed read-only commands and host-key verification. No blanket passwordless sudo.
- PiKVM/BMC: distinct monitoring and recovery credentials where supported. Power actions need explicit workflows and approval.

Prefer scoped API tokens or restricted SSH keys over personal administrator passwords. Never disable human MFA to make automation work.

Proxmox ACL reference: https://github.com/proxmox/pve-docs/blob/master/pveum.adoc

## Hardening order

1. Enable MFA for the n8n owner and keep recovery codes offline. Limit workflow editing to trusted administrators.
2. Trust an internal CA for n8n and device HTTPS; restrict management access to chosen admin endpoints. n8n currently binds only this LAN IP, but the VLAN is not yet an isolated management network.
3. Keep machine identities separate per backend and per read/change capability. Rotate credentials after suspected exposure.
4. Move long-lived device credentials to a dedicated secrets VM before adding powerful write access. Use scoped machine authentication and short-lived vault access tokens; device passwords themselves remain static unless the device supports rotation/dynamic identities.
5. Restrict the execution service to validated operations and targets; do not expose a generic secret-read, arbitrary URL, shell, or vault browser to the LLM.
6. Enable vault audit logging and separate protected log storage. Store unseal/recovery material off the n8n/vault hosts. Plan the manual-unseal versus local auto-unseal availability tradeoff.
7. Back up the encrypted credential database and its master encryption key with separate recovery controls. Test restoration on an isolated host.

## Current protection and remaining work

n8n encrypts credentials in PostgreSQL. Its `.env` contains the instance encryption key and database secrets in plaintext, protected by filesystem permissions inside a mode-0700 deployment directory. This is not encrypted host storage. The previously generated backup bundles the database, `.env` and TLS keys in protected but unencrypted files. Do not copy that archive to less-trusted storage as-is. Those existing backups have been retained rather than silently removed.

The new `scripts/maintenance/backup-n8n-encrypted.sh` streams each backup component through age encryption, using only a public recipient key on this VM. It will refuse to start until `config/backup-recipients.txt` exists. The corresponding private recovery key should be generated and stored on your trusted admin machine/offline, not here. This is prepared tooling, not a claim that encrypted backups are already scheduled or that the existing backup has been converted. Keep an independently protected offline copy of the n8n encryption key as part of recovery planning.

On your trusted admin machine, with age installed:

```bash
age-keygen -o krishadmin-hq-backup-key.txt
age-keygen -y krishadmin-hq-backup-key.txt > backup-recipients.txt
scp backup-recipients.txt krishadmin@192.0.2.180:/home/operator/krishadmin-hq/config/backup-recipients.txt
```

Keep `krishadmin-hq-backup-key.txt` offline and private. Only the PUBLIC recipient file is copied to the VM. Run encrypted backup on the VM:

```bash
sudo /home/operator/krishadmin-hq/scripts/maintenance/backup-n8n-encrypted.sh
```

The backup briefly pauses n8n for consistency and restarts it afterward. Decrypt and restore on an isolated recovery machine; verify credential decryption and a harmless workflow before relying on it. age documentation: https://github.com/FiloSottile/age

## First authenticated collector: Proxmox

These are preparation steps; no Proxmox credentials or permissions have been created by this task.

1. In Proxmox Datacenter -> Permissions -> Users, create a dedicated user `krishadmin-audit@pve`.
2. Add a user permission for that account with role `PVEAuditor` at `/` (or a narrower path if the requested API supports it), with propagation as needed.
3. Under API Tokens, create token `audit` for that user with **Privilege Separation enabled**. Store the token secret securely when Proxmox displays it.
4. Add a matching API-token permission for `krishadmin-audit@pve!audit` with `PVEAuditor`. With privilege separation, assigning only the user role is insufficient.
5. In n8n create a Header Auth credential named `KrishAdmin-HQ | Proxmox audit`. Name: `Authorization`. Value: `PVEAPIToken=krishadmin-audit@pve!audit=TOKEN_SECRET`.
6. Attach it to a fixed HTTP Request node, for example a GET to `https://PROXMOX_HOST:8006/api2/json/cluster/resources`. Trust the Proxmox CA and use the correct hostname; do not disable certificate validation.
7. Pass only the required fields (node/VM name, state, CPU/memory/storage measurements) to the AMD-GPU model. Avoid sending unnecessary configuration or logs that may contain secrets.

Keep any later change-capable token in a separate credential and separate workflow, with approvals for the actual action. The current network-audit CLI has no authenticated Proxmox collector; that is a separate integration to implement after the host address and credential are available.
