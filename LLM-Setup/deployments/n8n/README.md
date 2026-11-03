# KrishAdmin-HQ

Installed on KrishAdmin-HQ (192.0.2.180). Open https://192.0.2.180 and create the initial owner account promptly. The local self-signed certificate is tls/server.crt; its SHA-256 fingerprint can be checked with `openssl x509 -in tls/server.crt -noout -fingerprint -sha256`. It expires after one year. Replace it with your internal CA certificate when naming is decided. Never distribute tls/server.key.

## Services

Docker Compose project: homelab-n8n. n8n 2.39.8, PostgreSQL 18 with a dedicated non-superuser application role, external task runners, and nginx HTTPS proxy. Image digests are recorded in images.lock.txt after installation. Docker starts at boot; containers restart unless explicitly stopped.

Only HTTPS on the LAN IP and n8n on host loopback are published. PostgreSQL and the runner broker are not published. UTC is the current timezone. Telemetry, templates and community packages are disabled. Workflow execution payload retention is disabled initially to reduce sensitive-data retention; diagnostic metadata and container logs may still exist. Egress is not firewall-blocked: workflows can access LAN services and the internet, but no cloud model or secrets provider is configured.

## Operations

Run from /home/operator/n8n:

- Status: `sudo docker compose ps`
- Logs: `sudo docker compose logs --tail 100 n8n runners`
- Start: `sudo docker compose up -d`
- Stop: `sudo docker compose stop`
- Backup: `sudo ./backup.sh` (briefly stops the application for a consistent backup)

Do not run `docker compose down -v`: that removes persistent data.

The .env file contains generated database, encryption and runner secrets; it is mode 0600 inside a mode 0700 directory. It is excluded from Git. Docker administrators and the host account can access these secrets. Never share expanded `docker compose config` output or paste .env into chat. Maintain a protected offline copy of recovery secrets separately from database backups.

## Backup and recovery

backup.sh captures the database and n8n data volume with the application stopped, plus configuration, local secrets and TLS files. Backups contain credentials and private keys and must be encrypted before leaving protected local storage. Local backups alone do not protect against loss of this VM. No remote backup destination is configured yet.

Restore on an isolated host first: restore deployment files and their restrictive permissions, start PostgreSQL alone, restore database.dump using pg_restore as postgres into a clean n8n database, restore n8n-data.tar into the project n8n_data volume preserving ownership, then start the stack with the original .env encryption key. Validate account login, credential decryption and a harmless workflow before production use. A complete application restore test is still required after owner setup and a first workflow exist.

## Model integration plan

- Fast text generation: nvidia-gpu VM at 192.0.2.181, initially unconfigured. Setup script: /home/operator/setup-nvidia-gpu-ollama.sh. It supports Ubuntu 24.04/26.04 and defaults to qwen3:4b on an 8 GB GPU or qwen3:8b on a 16 GB GPU, with think:false requested for fast generation.
- Heavy reasoning: dual AMD-GPU Ollama endpoint; verify its current address and authentication before use.
- n8n credentials hold the API token; prompts and workflow JSON must not contain it.
- Choose the endpoint explicitly in each workflow. No routing or GPU credentials are configured yet.
- A model may propose an action; fixed workflows validate targets and enforce approval before changes. Do not expose arbitrary shell commands or unrestricted authenticated HTTP requests to the model.


## Trusting the GPU endpoint after its setup

Transfer only the GPU VM public certificate (`/opt/homelab-fast-ai/tls/server.crt`) to this host through SSH. Add it as a read-only mount in the n8n service and set `NODE_EXTRA_CA_CERTS` to that container path, then recreate n8n. Do not disable TLS verification. Create an Ollama credential with base URL `https://192.0.2.181:11434` and its API token. The token should be entered directly into n8n, not sent through chat. This integration is pending GPU VM setup and certificate transfer.

GPU installer reference sources:
- https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html
- https://docs.ollama.com/docker
- https://ubuntu.com/server/docs/how-to/graphics/install-nvidia-drivers/

The GPU installer has passed Bash syntax validation and its help-path check on this gateway; it has not been executed on the GPU VM. It downloads packages and models from the internet; inference remains local. It restarts Docker, and refuses to proceed if unrelated containers are running. Certificates last one year and need renewal/replacement. It does not configure Proxmox GPU passthrough.


## Active starter automation

Workflow: KrishAdmin-HQ | Service Health
Editor: https://192.0.2.180/workflow/homelabHealth001
Source: workflows/n8n-readiness-monitor.json

Runs every minute and can also be triggered manually. It requests the internal n8n readiness endpoint with a 10-second timeout, records timestamp/status/health, and marks the execution as failed if the response is unhealthy. Results are retained in n8n execution history for this workflow, with instance pruning set to seven days. No external messages are sent and no infrastructure changes are made. This is a self-check, not an independent uptime monitor: it cannot run while n8n is stopped. The GPU API was reachable and returned expected HTTP 401 without credentials; authenticated model inference is not yet connected to n8n. The temporary connectivity probe skipped certificate verification and is not used by the workflow. Import its certificate through a trusted channel before configuring a model credential.


## KrishAdmin-HQ AI routing

Branded landing page: https://192.0.2.180/hq/
AI workflow: https://192.0.2.180/workflow/krishHqAiRouter01
Host name: KrishAdmin-HQ (the IP remains 192.0.2.180; LAN DNS registration is separate).

For manual execution, edit the Example request node, set prompt and tier, and click Execute Workflow. tier=reasoning uses qwen2.5:72b-instruct-q8_0 at http://198.51.100.202:11434 over ZeroTier; tier=fast uses the NVIDIA-GPU Ollama HTTPS endpoint. The HTTP URL is carried inside the encrypted VPN, not a public endpoint. The AMD-GPU credential is stored encrypted in n8n. The router returns answer, model, completion status, generated-token count and elapsed seconds. It generates text only and does not act on infrastructure. It does not automatically retry or fail over to another GPU. Input is limited to 12000 characters. Successful/manual/error payload retention is disabled for this workflow; results remain visible during manual execution.

A real AMD-GPU execution passed: 92 generated tokens, approximately 63.7 seconds including any model loading/prompt processing. This is one smoke test, not a throughput benchmark. The system prompt labels the assistant KrishAdmin-HQ and prohibits claiming actions it did not perform.

NVIDIA-GPU status: connection pending token and public certificate transfer from 192.0.2.181. Run `python3 connect-nvidia-gpu.py` on this host after both incoming files exist. This verifies the HTTPS certificate and token, imports the credential, installs TLS trust in n8n, detects qwen3:4b or qwen3:8b, and removes the transferred plaintext token after successful setup. Test tier=fast afterward. Never copy the GPU server's private TLS key. No inference claims have been made for the NVIDIA-GPU branch yet.

The landing page is a local navigation page; n8n's editor retains its standard interface. The workflow and hostname carry KrishAdmin-HQ naming.


## Backup repair, 2026-11-02

`backup.sh` now delegates to `backup.py`. It locks against overlapping runs, stops only previously running n8n/proxy/runner services, writes a consistent database dump and data/configuration archives, then restarts exactly that service set even on failure. The owner-approved run created `backups/20261102T222514Z` and restored service health. Database restore into an isolated networkless PostgreSQL container passed (139 public tables), as did archive integrity. See that directory's private `restore-validation.json`. Full application login, credential-decryption and workflow recovery remain untested. There is no recurring full-backup schedule or off-host copy yet.
