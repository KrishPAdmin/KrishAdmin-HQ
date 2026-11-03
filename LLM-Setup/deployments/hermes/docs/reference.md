# 10. Command and file reference

Run from `/home/operator/krishadmin-hq/deployments/hermes` unless a command contains an absolute path.

## Operator CLI

| Command | Purpose | Model / mutation |
|---|---|---|
| `python3 hq.py status` | Current bounded status JSON | No model; observations only |
| `python3 hq.py alerts` | Current fixed-rule findings and recent changes | No model; observations only |
| `python3 hq.py history --limit 20` | Locally retained alert changes | No model; file read only |
| `python3 hq.py doctor` | Local service/configuration diagnostics | No model; read-only checks |
| `python3 hq.py report` | Readable Markdown status | No model; stdout |
| `python3 hq.py report --output PATH` | Save a new private report | Creates a file; refuses overwrite |
| `python3 hq.py guide --section index` | Read a documentation chapter | Local file read only |
| `python3 hq.py health` | Health interpretation | AMD-GPU by default; optional NVIDIA-GPU |
| `python3 hq.py backup` | Backup evidence interpretation | AMD-GPU by default; does not create backups |
| `python3 hq.py triage --question TEXT` | Evidence-based triage | AMD-GPU by default; cannot repair systems |
| `python3 hq.py research --url URL --question TEXT` | Approved HQ source fetch → AMD-GPU analysis | Network fetch on HQ only |
| `python3 hq.py team` | List named specialists and model assignments | No inference |
| `python3 hq.py team --agent louis --kind code_review --question TEXT --text-file FILE` | Delegate a bounded review | Fixed specialist model; no execution |
| `python3 hq.py analyze --kind plan --question TEXT --text TEXT` | Analyze supplied evidence | AMD-GPU; no tools |
| `python3 hq.py files` | List cached Discord uploads | Read-only |
| `python3 hq.py files --file-id ID --file-limit 3000` | Read an upload slice | Read-only; inspect next_offset |
| `python3 hq.py knowledge --query TEXT` | Search the maintained local guide | No model |
| `python3 hq.py compute` | Recent relay/GPU-residency receipts | No model; not host utilization |
| `python3 hq.py calculate --expression "0.1+0.2"` | Bounded decimal arithmetic | HQ; no model or arbitrary code |
| `python3 hq.py submit --kind health --request-id ID --question TEXT` | Durable specialist task | Creates a read-only Paperclip task |
| `python3 hq.py task-status --task KRI-NNN` | Query a bridge-created task | Read-only |

Guide sections: `index`, `quickstart`, `architecture`, `operations`, `monitoring`, `discord`, `backups`, `security`, `troubleshooting`, `recovery`, `reference`, `acceptance`, `capabilities`.

## Services

| Name | Owner / location |
|---|---|
| `hq-hermes` | Compose project in this directory |
| `paperclip-observations.*` | HQ user systemd units; source collector belongs to Paperclip |
| `hq-hermes-evidence.*` | HQ user units; ordered evidence refresh |
| `hq-hermes-monitor.*` | HQ user units; local observation history |
| `hq-backup-observations.*` | System units; root-owned metadata exporter |
| `hq-backup-maintenance.*` | Prepared user units; not enabled without recurring-interruption approval |

## Deployment files

| Path | Purpose |
|---|---|
| `broker.py` | Authenticated collection, inference relay, task intake and research |
| `health_rules.py` | Deterministic assessment and default thresholds |
| `worker.py` | Optional fast Hermes workers and direct tool-free AMD-GPU analyst |
| `team.py`, `team_worker.py` | Fixed named roles/models and specialist service |
| `capabilities.py` | Bounded task prompts and decimal arithmetic |
| `file_service.py` | Restricted upload extraction and syntax validation |
| `setup_team_paperclip.py` | Register the named team and reporting hierarchy |
| `plugin/` | Ten concierge tools |
| `monitor.py` | Bounded local history writer |
| `doctor.py` | Local diagnostics |
| `reporting.py` | Deterministic Markdown report rendering |
| `hq_client.py`, `hq.py` | Credential-safe operator client and CLI |
| `backup_observer.py` | Sanitized root-owned backup metadata exporter source |
| `refresh_evidence.py` | Copies source host observations |
| `backup.py` | Hermes archive and extraction/SQLite validation |
| `verify_database_backup.py` | Isolated PostgreSQL restore check |
| `backup_maintenance.py` | Prepared full-backup orchestration |
| `enroll_amd_gpu_observer.py` | Interactive one-time restricted observer enrollment |
| `enroll_discord.py`, `rotate_discord_token.py` | Discord enrollment / credential replacement |
| `compose.yaml`, `prepare.py`, `release.json` | Installed services, preparation source and version pin |
| `config/paperclip.json`, `config/routines.json` | Registered local task identities and routine IDs |
| `config/research-origins.json` | Explicit public-document origin allowlist |
| `state/monitor.json` | Private bounded alert/sample history |
| `state/tasks.db` | Durable task reservations and Discord result subscriptions |
| `state/audit.jsonl` | Collection/inference/task metadata receipts; not prompts |
| `profiles/concierge/gateway_state.json` | Discord gateway state |
| `profiles/concierge/state/gateway.heartbeat` | Native gateway heartbeat |
| `validation/` | Operator test and recovery evidence |

## Validation commands

```bash
python3 -m unittest -v test_enrollment.py test_boundaries.py test_observations.py test_monitoring.py test_capabilities.py
python3 ../n8n/test_backup.py
python3 hq.py doctor
```

The boundary suite includes live authenticated/anonymous policy checks against the local broker. Run it with the broker available. The native model/tool-loop validation is `check_concierge.py`; use its documented container invocation in the acceptance evidence rather than executing it in a host environment without Hermes dependencies.


See [the named team and expanded capabilities](capabilities.md) for model assignments, uploaded files, code/config review, draft artifacts, exact arithmetic, local knowledge and specialist task submission.

Task result delivery: `notify_tasks.py`, `task_updates.py`, and `systemd/hq-hermes-task-notifications.{service,timer}`. See [Discord operation](discord.md#automatic-paperclip-result-updates) for state, retries and recovery.
