# KrishAdmin HQ — Hermes and Discord

Private Discord access to local agents, bounded homelab observations, Paperclip tasks and HQ-collected research using NVIDIA-GPU/AMD-GPU compute.

**Start here: [Documentation outline and reference guide](docs/index.md).**

## Daily commands

```bash
cd /home/operator/krishadmin-hq/deployments/hermes
python3 hq.py status
python3 hq.py alerts
python3 hq.py doctor
python3 hq.py history
python3 hq.py report
python3 hq.py guide --section quickstart
```

In #krishadmin-hq-llm, send `<@900000000000000001> show current lab status` or ask for active warnings and recent changes. Mention the account, not its role.

## Suits team and files

Jessica, Harvey, Mike, Louis, Rachel and Donna are live local specialists with fixed model assignments. See [team, models, uploaded files and skills](docs/capabilities.md). Specialist analysis now uses AMD-GPU by default; the Discord coordinator uses NVIDIA-GPU.

## Reference

- [Quick start](docs/quickstart.md)
- [Architecture and compute boundaries](docs/architecture.md)
- [Agents, repetitive jobs and approvals](docs/operations.md)
- [Monitoring thresholds and history](docs/monitoring.md)
- [Discord setup and token replacement](docs/discord.md)
- [Backups and validation](docs/backups.md)
- [Security and credential locations](docs/security.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Recovery and updates](docs/recovery.md)
- [Commands, services and files](docs/reference.md)
- [Verified evidence and outstanding decisions](docs/acceptance.md)

Read-only monitoring is active. Nightly full-backup maintenance is prepared but awaits recurring-interruption approval. Off-host storage, token rotation and full application recovery remain operator follow-ups. The setup archive (local runtime/history reference; excluded from this source edition) preserves historical intermediate states; use the current guide and live diagnostics for operation.
