# 7. Security and access

## Credential locations, not credential values

| Purpose | Location |
|---|---|
| Discord bot token | `access/discord-token` |
| Separate broker identities | `access/` |
| NVIDIA-GPU API token | `/home/operator/krishadmin-hq/secrets/nvidia-gpu-api.txt` |
| AMD-GPU API token | `/home/operator/krishadmin-hq/secrets/amd-gpu-api.txt` |
| NVIDIA-GPU trusted public certificate | `/home/operator/krishadmin-hq/secrets/nvidia-gpu-server.crt` |
| NVIDIA-GPU restricted observer private key | `../paperclip/operations/keys/observer` |
| AMD-GPU SSH password | `../paperclip/operations/keys/amd-gpu-password` (0600) |
| NVIDIA-GPU observation SSH key | `/home/operator/.ssh/krishadmin-hq-nvidia-gpu` |
| Original AMD-GPU SSH key, previously rejected | `/home/operator/.ssh/krishadmin-hq-amd-gpu` |

The AMD-GPU API token is not its Linux password. The AMD-GPU SSH password is now saved privately on HQ at the path above, as explicitly requested by the operator. SSH/sudo passwords entered during enrollment remain in the local authentication interaction, not in task prompts. Do not print key files, `.env`, authorization headers or expanded Compose configuration into support chats.

## AMD-GPU diagnostics authentication

The operator switched AMD-GPU collection to password authentication as krishadmin. The private credential is supplied locally through SSH_ASKPASS, with public-key authentication disabled and strict host-key verification enabled. No password is passed to models or in process arguments. The account is not server-restricted; the HQ host collector enforces a fixed command allowlist. Routine commands use no sudo, and no browsing/research runs on AMD-GPU. See [diagnostics](diagnostics.md) for exact scope. The older observer key is no longer used for AMD-GPU collection.

## Container boundaries

Agent containers use a non-root UID, read-only root filesystem, dropped capabilities and an internal network. The broker holds model credentials. The analyst and six named specialist identities cannot collect sources, submit tasks, switch models or provide tool schemas/transcripts. Their only permitted path is evidence-only inference through the broker. Discord egress is host-allowlisted. Credentials remain outside model prompts.

The gateway operator can administer Docker and use sudo; the host itself is a trust boundary. These controls do not promise safety after host administrator compromise. Local backups also contain credential copies. Global AMD-GPU egress restrictions and whole-network device hardening are not claimed by this deployment.

## Sharing evidence

Use `hq.py report` for a bounded report. It deliberately includes internal system names and measurements, so review it before external sharing. It does not include credentials, raw logs or chat history. Keep complete logs and archives local. Rotate the Discord credential exposed during enrollment.

## Shared Discord files

The owner and explicitly allowed friend share access to this channel’s supported bot tools, cached uploads and drafts. This is not a per-user private document store. File extraction runs in a separate restricted container without model credentials; uploads are read-only there, limited to 5 MiB and parsed without executing code, macros or formulas. Extracted text and model evidence are separately bounded. User-supplied instructions inside documents are treated as untrusted content.
