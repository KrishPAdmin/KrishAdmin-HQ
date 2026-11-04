# 3. Agents and operations

## Agent responsibilities

| Component | Job | Compute/tools |
|---|---|---|
| Concierge | Answer authorized Discord requests and submit requested tasks | NVIDIA-GPU coordinator; native and MCP tools in [capabilities](mcp.md) |
| Health | Interpret bounded host/API evidence | AMD-GPU by default, optional NVIDIA-GPU; no tools |
| Backup watch | Interpret backup evidence and missing coverage | AMD-GPU by default, optional NVIDIA-GPU; no tools; does not create backups |
| Incident triage | Analyze supplied observations and propose next steps | AMD-GPU by default, optional NVIDIA-GPU; no tools; cannot repair infrastructure |
| AMD-GPU analyst | Analyze HQ-collected documentation/evidence | AMD-GPU; no tools |
| Paperclip dispatcher | Intake/routing identity | Not a free-running infrastructure agent |

## Repetitive jobs

| Job | Schedule | Effect |
|---|---|---|
| Paperclip host observations | About every 5 minutes | Fixed local/approved SSH measurements |
| Hermes evidence refresh | About every 5 minutes, ordered after host collection | Copies bounded host evidence |
| Backup metadata exporter | About every 5 minutes | Root-owned exporter publishes sanitized metadata |
| Hermes monitor | About every 5 minutes, after evidence refresh | Records local samples and alert transitions; no model call |
| Paperclip backup-evidence review | Daily 09:00 America/New_York | Produces a specialist report; does not take backups |
| Full-backup maintenance | Prepared for 03:30 America/New_York; disabled | Would create backups and validate database restores; briefly pauses n8n |

The Paperclip review uses `skip_if_active`. An earlier report remaining In Review can prevent the next report from starting. Review and close completed reports deliberately; do not interpret missing duplicate tasks as a scheduler failure. Existing unrelated Paperclip routines are unchanged.

## Request a specialist report

```bash
python3 hq.py health
python3 hq.py backup
python3 hq.py triage --question 'Explain the current observation gaps'
python3 hq.py submit --kind health --request-id health-review-20261102-01 --question 'Review the current measurements'
python3 hq.py task-status --task KRI-317
```

`health`, `backup` and `triage` run analysis immediately. `submit` creates a durable Paperclip task. A stable request ID deduplicates retries. If the outcome is uncertain, reconcile the original task; do not change the request ID to force another submission. Reports return for review; accepting a report does not authorize infrastructure changes.

## Collect documentation for AMD-GPU

```bash
python3 hq.py research --url https://docs.python.org/3/tutorial/floatingpoint.html --question 'Explain binary rounding using this source'
```

Use a focused research question, optional search query and optional 1–3 public HTTPS URLs. HQ searches/reads sources; AMD-GPU synthesizes. See [MCP and research](mcp.md). Never move collection onto AMD-GPU.

## Change policy

Automatic actions are observations and local recordkeeping. The bot has no restart, delete, firewall, power or arbitrary shell tool. Maintenance scripts are separate operator commands. The operator previously approved the NVIDIA-GPU Ollama recovery and one n8n backup interruption; those completed actions do not automatically authorize future disruptive schedules.


See [the named team and expanded capabilities](capabilities.md) for model assignments, uploaded files, code/config review, draft artifacts, exact arithmetic, local knowledge and specialist task submission.

## Existing Discord-to-Paperclip bridge

Discord uses the native gateway, account mentions and enrolled-user checks. hq_task records a stable request ID and reserves it in local SQLite before creating an issue. The Discord watch is saved with the task record. A host timer polls for in_review/done/blocked/cancelled and posts a result update, then edits that message. Pending deliveries use a durable payload and nonce; uncertain sends reconcile against Discord history. Rate limits and transient errors back off. The notifier revalidates the requesting user before delivery. A completed report is not automatically a passed check. Do not replace this with content-only deduplication: repeated text can represent a separate intentional request. Planning changes does not create assignments; only returned issue IDs do.
