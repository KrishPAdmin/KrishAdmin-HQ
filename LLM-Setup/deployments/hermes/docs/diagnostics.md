# 13. Fixed host and SSH diagnostic checks

## Use from Discord

Mention the bot account, then ask:

- “Check the NVIDIA-GPU GPU driver, VRAM and temperature.”
- “Check AMD-GPU ROCm and GPU utilization.”
- “Show the top CPU and memory processes on AMD-GPU.”
- “Check HQ disk space, inode usage and failed services.”

The coordinator uses `hq_diagnostics` with a fixed target/check. It may pass a short evidence summary to Jessica, Harvey or Louis for interpretation. Collection itself uses no model. The native assistant cannot run arbitrary SSH commands.

| Check | Collected evidence |
|---|---|
| `overview` | Uptime/load, memory/swap and a one-second vmstat sample |
| `gpu` | NVIDIA/AMD SMI observations, driver versions, temperatures, GPU utilization and VRAM |
| `processes` | Top 40 processes by CPU and memory, with names but no full command lines or environments |
| `services` | Failed systemd units and state of fixed Ollama/Docker/SSH unit names |
| `storage` | Local filesystem space/inodes and block-device inventory |

The GPU flags follow [NVIDIA’s SMI reference](https://docs.nvidia.com/deploy/nvidia-smi/) and [AMD’s ROCm SMI reference](https://rocm.docs.amd.com/projects/rocm_smi_lib/en/docs-6.1.0/python_usage.html). Installed software may expose different fields. Missing binaries/permissions are reported as unavailable coverage; they do not establish hardware failure.

`htop` is interactive, so the bot returns bounded process tables instead. The process checker now samples `/proc` CPU tick changes over approximately one second: 100% means one logical CPU. It excludes its own checker process and ranks only processes present in both snapshots. PID reuse is rejected; very short-lived or unreadable processes can be missed. RSS is resident memory, not unique memory. This replaces the old `ps` lifetime-average ranking.

CPU usage and a `llama-server` process do not establish GPU inference. Use a fresh `gpu` check for current GPU utilization, and an actual model execution receipt to establish a specific model run. A sleeping state describes the final sampling instant; it does not mean the process was idle throughout the interval. Never reuse an earlier loaded-model listing as current evidence. The bot should perform supported SSH checks directly without first claiming SSH is unavailable.

These checks do not kill processes, change clocks, reset GPUs, restart services, install drivers, fetch websites, scan networks or read unfiltered logs.

## Local CLI and Paperclip

```bash
python3 hq.py diagnostics --target nvidia-gpu --check gpu
python3 hq.py diagnostics --target amd-gpu --check processes
python3 hq.py diagnostics --target hq --check storage
```

Paperclip has three deterministic agents under Harvey: **HQ Host Checker**, **NVIDIA-GPU GPU Checker**, and **AMD-GPU GPU Checker**. Assign a task to one to collect all five checks for its fixed host and attach a JSON evidence report. These checkers use CPU/SSH collection, not GPU inference, and ignore shell commands supplied in task text.

## Authentication and boundaries

HQ collects its own local measurements. NVIDIA-GPU uses the `paperclip-observer` account and a source-restricted, forced-command SSH key. AMD-GPU uses the operator-selected `krishadmin` account with password authentication, public-key authentication explicitly disabled, and strict host-key verification. The AMD-GPU password is encrypted in OpenBao as `amd-gpu-ssh`. `ssh_access.py` retrieves it through the host-only vault connector and supplies it through SSH_ASKPASS; it is absent from process arguments, model prompts, reports and logs. Existing AMD-GPU observer keys are not used by the current collector.

AMD-GPU’s account is an administrator account, not a server-restricted observer account. The HQ collector enforces the named command allowlist. Routine diagnostics run without sudo; the one-time probe installation used authorized sudo. Credentials stay on HQ, outside the agent containers. Never describe this as a global AMD-GPU outbound firewall: the workflow executes fixed local checks and performs no browsing/research from AMD-GPU.

The host service `hq-hermes-diagnostics.service` listens on a mode-0600 Unix socket, authenticates its private broker credential, permits two concurrent requests, and rejects arbitrary host addresses, arguments and extra request fields. Commands have time/output limits. The broker mounts only that socket directory, not the SSH credentials. Unprivileged model workers remain inference-only.

## Maintenance and evidence

- Source: `../paperclip/operations/diagnostics_probe.py` and the existing `host_probe.py` dispatcher.
- Host transport/service: `diagnostics_service.py`, `../paperclip/operations/ssh_access.py`.
- Live evidence: `validation/diagnostics-matrix.json` and per-host/per-check JSON files.
- Private metadata receipts: `state/diagnostics/audit.jsonl`; broker receipts: `state/audit.jsonl`.
- Basic five-minute AMD-GPU telemetry now uses the same password authentication; it remains separate from on-demand diagnostics.

Verify a host fingerprint through a trusted console if it changes. Rotate the locally saved password when the remote account password changes. Private backups contain the credential file and must remain private.
