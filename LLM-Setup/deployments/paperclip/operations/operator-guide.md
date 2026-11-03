# KrishAdmin operations

Open https://paperclip.example.invalid/KRI/dashboard and create a task assigned to Local Coordinator.

- **Scan my network** runs bounded discovery on 192.0.2.0/24 and publishes JSON and a readable report. KRI-250 is the first 31-address inventory.
- **Run a system health check** collects authenticated GPU API checks plus HQ/NVIDIA-GPU CPU/load, memory, root disk, failed-service, container and GPU observations.
- **Diagnose my systems** collects the same fixed diagnostic evidence. It cannot execute arbitrary commands from a task.
- **Ask Codex to review this error** delegates workspace investigation and code work to the connected ChatGPT account. Supply the relevant redacted error and expected behavior. Proposed repairs return for review.

The Daily GPU health report routine now performs deterministic system checks. Host observations refresh every five minutes; stale or unavailable coverage is marked explicitly. Reports are measurements at a stated time. Review a result and mark its task Done when satisfied.

The local runtime can queue one Codex diagnosis when a task fails. It leaves the original task blocked and does not automatically replay the failed operation or apply remote repairs. Codex account and coordinator handoff were verified in KRI-258 and KRI-259/260.

Current coverage: HQ and NVIDIA-GPU host health, both GPU APIs. AMD-GPU SSH authentication is unavailable. The other discovered devices have discovery coverage only. Authenticated Proxmox guest/cluster/backups and NAS storage health require dedicated read-only API access.

## Add a Linux host

1. Download install-observer.sh from this task and review it. Run `sudo sh install-observer.sh` at the selected Linux/Proxmox host's trusted console. It installs a forced read-only probe under a dedicated observer account, with no sudo grant, no SSH forwarding and access restricted to HQ's source addresses.
2. Obtain and verify that host's SSH host-key fingerprint through its console. Add the verified host key to HQ's known_hosts.
3. Add the address to operations/targets.json on HQ with user paperclip-observer and key /home/operator/krishadmin-hq/deployments/paperclip/operations/keys/observer. Addresses are restricted to the authorized LAN and the existing AMD-GPU overlay endpoint.
4. Run `systemctl --user start paperclip-observations.service` on HQ, then create another health-check task to verify coverage.

The enrollment script contains only the public observer key; its private key stays on HQ. Linux host observation does not establish guest, storage-array or backup integrity.

The Codex workspace sandbox could not initialize a kernel namespace during QA; runtime-approved execution inside the existing server container succeeded. The dedicated workspace is not a guaranteed filesystem sandbox. Host Docker and SSH access are not mounted into the server.
