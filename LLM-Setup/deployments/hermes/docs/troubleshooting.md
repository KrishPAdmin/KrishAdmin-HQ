# 8. Troubleshooting

Start on HQ:

```bash
cd /home/operator/krishadmin-hq/deployments/hermes
python3 hq.py doctor
python3 hq.py alerts
```

## Discord does not answer

1. Send a fresh `<@900000000000000001> show current lab status` message in the configured private channel. Select the bot account, not its role. Plain messages and role mentions do not trigger replies. Both allowed users can mention the account.
2. Try `/status`. If it replies but a model request fails, inspect broker/GPU status. `/status` itself does not use the model.
3. Check `docker compose ps` and the `discord_gateway` diagnostic. A fresh heartbeat plus connected state is expected.
4. For HTTP 403/code 50001, inspect the bot member's View Channel permission and category overrides. Do not grant Administrator to work around a channel permission issue.
5. For HTTP 401, use the current application's Bot token. Use the rotation helper after a reset; do not paste credentials into chat.

Gateway state is in `profiles/concierge/gateway_state.json`. Logs are in `profiles/concierge/logs/`; they may contain private message content. Review locally and redact before sharing.

## AMD-GPU API works but host telemetry is unavailable

These use separate credentials. The API token cannot authenticate SSH. AMD-GPU currently uses password authentication as `krishadmin`, with credentials confined to the HQ collector and a fixed client-side command allowlist. NVIDIA-GPU retains the forced-command `paperclip-observer` key. The target configuration is `../paperclip/operations/targets.json`; see diagnostics.md. Do not revert AMD-GPU to the historical key transport.

If enrollment was lost during rebuild, inspect the maintained password transport and probe deployment from HQ. The AMD-GPU account itself is not server-side restricted. If the SSH host key changed, verify its fingerprint through a trusted console rather than disabling verification.

A password reset must happen from a root/authorized sudo session on AMD-GPU or its recovery console. Gateway sudo authority does not confer administrator access to AMD-GPU.

## Snapshot or backup metadata is stale

```bash
systemctl --user status paperclip-observations.service hq-hermes-evidence.service hq-hermes-monitor.service
systemctl --user list-timers
systemctl status hq-backup-observations.service
```

For a read-only refresh:

```bash
sudo systemctl start hq-backup-observations.service
systemctl --user start hq-hermes-monitor.service
```

The monitor's dependencies refresh host observations before sampling. Do not change timestamps to hide staleness. Future-dated snapshots are also invalid. The backup exporter reads protected archive metadata; it does not give agents archive access.

## GPU unavailable or CPU fallback

A model loaded with zero GPU residency triggers a critical alert, and the broker refuses to report successful GPU inference. An unloaded model alone is not an error. The earlier NVIDIA-GPU failure was a stale container GPU initialization; an approved restart of `homelab-fast-ollama` restored it. Do not assume every future failure has the same cause or automatically restart the entire Docker host.

On 2026-11-09 this recurred: host `nvidia-smi` worked, container NVML failed, and two Discord completions showed zero VRAM. The managed NVIDIA-GPU Ollama container now uses `--device nvidia.com/gpu=all` (native CDI) instead of the legacy GPU hook. It passed container GPU checks after a systemd daemon reload. The migration script is `../../scripts/gpu/migrate-nvidia-gpu-cdi.py`; it preserves the image and model volume and retains the prior stopped container for rollback. Do not run the broad provisioning script to repair this service.

The relay first loads an unloaded model without the user prompt and requires GPU residency before generation. GPU verification failures return an operational HTTP 503, not malformed-request HTTP 400, and emit denied receipts rather than successful inference records. Creating a new chat cannot repair container GPU access.

Inspect host/container GPU evidence and active workloads, then propose the narrowest repair. Service interruptions, driver changes and reboots need separate approval. Do not redirect research execution to AMD-GPU or silently use cloud inference.

## Backup present but not verified

“Present”, “fresh”, “database restore passed” and “application recovery tested” are different facts. Run the isolated database verifier in [backups](backups.md). It will not start restored applications. Untested application recovery is not evidence of a failed backup. Failed verification needs inspection before production use.

If the disk warning fires, inspect capacity and decide retention. Neither the monitor nor the prepared maintenance job automatically deletes backups.

## Paperclip task missing, duplicated or stuck In Review

Reuse the original submission request ID. Query `hq.py task-status --task KRI-NNN`; reconcile ambiguous submissions in Paperclip instead of creating a new ID. A report awaiting review is not an infrastructure repair request. The daily backup-review routine skips while an earlier run remains active; review and close completed reports when appropriate.

## Doctor reports attention immediately after restart

Containers may report `health=starting` before their first successful health check. Wait for the startup interval and rerun the doctor. If attention persists, inspect the named service. Do not repeatedly restart a healthy service to clear an expected startup state.

## History is empty

The monitor records changes, not duplicate healthy messages. No events can be normal. `hq.py history` includes the most recent collection time/status; `state/monitor.json` also contains bounded samples. A failed collection never proves earlier problems have recovered.
