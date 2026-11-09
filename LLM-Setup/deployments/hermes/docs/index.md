# KrishAdmin HQ reference guide

This is the documentation outline and entry point for the installed Hermes/Discord system. Updated 2026-11-03. Start with the quick start; use the other chapters when needed. The deployment directory is `/home/operator/krishadmin-hq/deployments/hermes`.

2026-11-09 repair: NVIDIA-GPU moved to native CDI GPU access; inference verifies residency before evaluating a user prompt. Read [personal Google Workspace](workspace.md), [skills review](skills-review.md), and [repair validation](repair-2026-11-09.md) for new capabilities and outstanding enrollment.

## Guide outline

| Chapter | What you will find |
|---|---|
| [1. Quick start](quickstart.md) | Daily commands, Discord examples, saving a report |
| [2. Architecture](architecture.md) | Components, connections, compute placement and data flow |
| [3. Agents and operations](operations.md) | Agent responsibilities, repetitive jobs, approvals and task lifecycle |
| [4. Monitoring](monitoring.md) | Warning thresholds, change history and interpretation |
| [5. Discord](discord.md) | Copyable prompts, model routing, task updates, channel access and connection checks |
| [6. Backups](backups.md) | What is backed up, validation, schedules and storage gaps |
| [7. Security and access](security.md) | Credential locations, AMD-GPU observer access and network boundaries |
| [8. Troubleshooting](troubleshooting.md) | Symptom → check → next action |
| [9. Recovery and updates](recovery.md) | Isolated restore, rollback and safe update procedure |
| [10. Command and file reference](reference.md) | CLI commands, services, paths and evidence files |
| [11. Acceptance and remaining work](acceptance.md) | What was verified and what still needs a decision |
| [12. Suits team and expanded capabilities](capabilities.md) | Named agents/models, coding, files, research, drafts and arithmetic |

| [15. Internet, MCP and long-context work](mcp.md) | Search, weather, checkers, upload workflows, AMD-GPU context and limitations |

## Find the right action

- Something looks wrong: run `python3 hq.py doctor`, then read [troubleshooting](troubleshooting.md).
- Want the latest measurements: run `python3 hq.py status` or ask the Discord bot.
- Want only current warnings: run `python3 hq.py alerts`.
- Want to see changes: run `python3 hq.py history`.
- Need a durable specialist report: submit a read-only Paperclip task; see [operations](operations.md).
- Need to restore or modify a service: use the relevant maintenance chapter and obtain any outstanding approval first.

## Current operating assumptions

Read-only observations and local history run automatically. Models may analyze supplied evidence and create requested read-only tasks. Infrastructure repairs, power actions and arbitrary remote commands are not bot tools. Automatic Discord task-result follow-ups and planned-restart notices are configured; unsolicited recurring health-alert messages are not configured. The recurring full-backup job is prepared but remains disabled pending approval for its n8n interruption. Token replacement and off-host storage require operator input.

Historical setup notes are preserved in the setup archive (local runtime/history reference; excluded from this source edition). They contain superseded intermediate states; this guide and live diagnostics take precedence.

- [13. Fixed host and SSH diagnostics](diagnostics.md) — GPU drivers, CPU/memory, processes, services, storage and authentication.

- [14. Owner-only GitHub](github.md) — repository reads, code proposals, exact owner confirmation and new review branches.

- [Individual Google accounts](workspace.md) — private Gmail/Calendar access, OAuth and confirmations.
- [Skills review](skills-review.md) — selected public skills and MCP candidates.
- [Herdr with local AI](herdr.md) — recommended terminal layout and existing HQ CLI workflows.
- [November 9 repair record](repair-2026-11-09.md) — GPU repair, integrations, evidence and remaining limits.

- [Context windows and controls](contexts.md) — complete runtime table, CLI changes and rollback.
- [Full stack and live GPU dashboard](dashboard.md) — current telemetry, inventory and readiness.
