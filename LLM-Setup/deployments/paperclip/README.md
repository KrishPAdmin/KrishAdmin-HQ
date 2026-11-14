# KrishAdmin Paperclip pilot

Open **https://paperclip.example.invalid/KRI/dashboard** through the existing reverse proxy. The internal fallback is **https://192.0.2.180:8443**.

Sign in with your account `admin@example.invalid`, which has company access and
instance administrator privileges. The initial owner invitation has been revoked
after provisioning. The bootstrap operator `krishadmin@hq.internal` remains a
recovery account; its generated password is in `admin-credentials.json` (mode 600,
outside the agent mounts). Signup is currently enabled, but additional users need
company membership granted by an administrator. The HTTPS certificate is the
existing HQ certificate; clients must trust it to avoid a browser warning.

## Use it

1. Select **KrishAdmin Local AI Lab** at **https://192.0.2.180:8443**.
2. Create a task under **Cluster Operations**, assign **Local Coordinator**, and set **Todo**.
3. The coordinator plans up to four specialist steps. Independent tasks run on their respective backends; dependent tasks wait for real Paperclip blockers and receive completed teammate output plus JSON artifact contents.
4. New internal specialist tasks finish **Done** automatically. The coordinator resumes, combines their evidence, and puts the **parent** **In Review**. Review that result and mark it **Done**. Direct specialist assignments still require human review.
5. To revise completed work, create a follow-up task with the original task ID and requested changes. Existing execution plans are reused on retries to avoid duplicate work; changing an old parent to Todo does not discard its completed plan.

Examples:

- “Have NVIDIA-GPU and AMD-GPU each calculate the sum of squares from 1 to 20; compare their answers.” This runs actual local model inference on both backends.
- “Use Pi to collect current GPU API health and publish JSON and a report; have AMD-GPU analyze that evidence.”
- “Summarize the current task board and identify blocked work.” This can report state; it cannot repair arbitrary hosts.

| Agent | Backend | Actual capability |
|---|---|---|
| Local Coordinator | NVIDIA-GPU / qwen3.5:9b | Bounded multi-step planning, delegation and final synthesis |
| AMD-GPU Analyst | AMD-GPU / qwen2.5:72b-instruct-q8_0 | Analysis of supplied tasks and teammate evidence |
| NVIDIA-GPU Assistant | NVIDIA-GPU / qwen3.5:9b | Short reasoning, summaries, extraction and writing |
| Benjamin — Suits Implementation Engineer | NVIDIA-GPU / paperclip-qwen3.5:9b, Pi 0.74.0 | Actual file/shell tools in its worker; approved GPU API collector; downloadable artifacts |

The process runtime handles Paperclip API operations; text models cannot execute arbitrary tools. Pi has no host Docker socket or SSH keys, but does have network access and mounted inference credentials. It remains an internal trusted-task worker, not a sandbox for hostile inputs. Each Pi task has a separate workspace, so collecting and writing related files should be one step. JSON artifacts and result comments are shared with downstream agents.

### Scheduled work

Open **Routines**; both schedules use **America/New_York**:

- **Daily GPU health report**, 10:00: Pi collects the two configured GPU APIs, publishes JSON/report files, AMD-GPU analyzes the evidence, and the coordinator returns the report for review. Finish the parent review to permit the next scheduled report; `skip_if_active` prevents stacking unfinished reports.
- **Daily team digest**, 17:00: each specialist posts its last-24-hour task activity from live Paperclip records; the coordinator gathers the briefs and current board attention items. This observational digest completes automatically. It does not implement NetworkChuck’s second Q&A round.

Both support **Run now**, skip missed schedules, and avoid overlapping instances. Cases and Decisions are enabled. New hires require board approval; the current bounded coordinator does not implement autonomous hiring.

This adapts [NetworkChuck’s guide](https://github.com/theNetworkChuck/paperclip-guide) to the existing local-only team. The original pilot did not configure cloud subscriptions or broad host management. See the October operations update below for the current Codex, discovery and health capabilities. NAS/Proxmox authenticated access and autonomous host changes remain unconfigured.

## Agent customization

The coordinator and text specialists use Paperclip's built-in `process` adapter and
`/opt/hq-agents/local_agent.py`. Adapter settings are editable in Paperclip:

- Command: `python3`; arguments: `["/opt/hq-agents/local_agent.py"]`.
- `HQ_MODE`: `coordinator` or `specialist`.
- `HQ_DEPARTMENT=1`: enables the new team coordinator in `agents/department.py`.
- `agents/department.json`: coordinator identity and the existing specialist allowlist.
- `setup_department.py`: idempotently configures the existing team, flags and routines.
- `HQ_BACKEND`: `amd-gpu` or `nvidia-gpu`.
- `HQ_MODEL`: optional installed Ollama model override.
- `HQ_SYSTEM_PROMPT`: optional specialist instructions (system prompt).

For this custom process adapter, use `HQ_SYSTEM_PROMPT` to customize specialist
behavior; the generic Paperclip instructions editor is not consumed by this script.
Runtime code is bind-mounted read-only from `agents/`; edits apply to new runs.
`agents/targets.json` maps `amd-gpu` and `nvidia-gpu` to specialist IDs. Its optional `pi`
entry enables coordinator delegation for creating, editing, or testing workspace
files. Benjamin — Suits Implementation Engineer uses `agents/pi_bridge.py` to call the private worker; its
model/tool configuration lives under `pi-worker/`.

Text-runtime limits: one run per agent, one request per GPU across these pilot agents, 100 daily
runs per agent, 180-second GPU queue wait, 240-second inference timeout,
540-second process timeout, 8K context, 1,200 generated tokens, and at most 16,000
characters of task/history input. Timer-driven heartbeats are disabled; task
assignment/manual task wakes are enabled. Other GPU clients (n8n/OpenWebUI) are
not covered by this pilot's file locks. Pi shares the NVIDIA-GPU lock, allows at most 12
tool calls and 180 seconds of tool execution after queueing, and publishes at
most five files of up to 1 MiB each. Its dedicated Ollama model alias uses a
16K context window and disables thinking for tool calls. No automatic cross-GPU failover is configured.

## Deployment and maintenance

Run commands from this directory:

```bash
sudo docker compose ps
sudo docker compose logs --tail 50 server
sudo docker compose up -d
python3 -m unittest -v test_runtime.py test_department.py
python3 backup.py
```

Paperclip, PostgreSQL, and nginx images are digest-pinned. The Pi worker is locally
built with Pi package version 0.74.0; its Node base is also digest-pinned.
Paperclip image version: `2026.916.1`, source revision
`d554c4789ed3930f8a53ac9fdf6503b3187097da`. The `upstream/` checkout is a matching
read-only source reference; no upstream application code was modified.

Only nginx publishes a host port, bound to `192.0.2.180:8443`. PostgreSQL and the
Paperclip application are private to the Compose network. Application data is in
`data/`, PostgreSQL data in Docker volume `hq-paperclip_pgdata`. Services restart
unless explicitly stopped. The server runs as UID 1000 with no Docker socket or
host SSH keys mounted. First-party Paperclip telemetry is disabled.

Never run `docker compose down -v` on a deployment whose database you need.
For an upgrade, take a backup, test the replacement digest against a restored
database, and update the pin. Database migrations may prevent image-only rollback.
The proxy refreshes its upstream address through Docker DNS every 10 seconds,
so server container recreation does not require a proxy restart.

## Backup and recovery

`backup.py` writes `backups/<UTC timestamp>/database.dump` (pg_dump custom format)
and `instance.tar.gz` (configuration, application data, credentials and required
external GPU/TLS secrets, worker source/secrets/workspaces, backup utility, and runtime tests). The archive excludes
Paperclip-generated database backup files because `database.dump` already provides
the database snapshot. Files are private, but not encrypted. Keep an encrypted
off-host copy through your normal backup process. For a coordinated backup while
work is active, pause task intake and let agent runs finish before running it.

To restore, stop Paperclip/proxy, restore the archive into an isolated deployment
directory, place `external-secrets/` files at the referenced secret/TLS paths (or
adjust the mount paths), start PostgreSQL, and restore `database.dump` into a new
empty database using `pg_restore -U paperclip -d <new_database>`. Point DATABASE_URL
at that restored database, then start Paperclip and the proxy. Preserve `.env`
and the keys under `data/`; they are needed for auth and encrypted stored secrets.
Do not overwrite the live database as a restore test.

## Troubleshooting

- A comment on a parent that still has unresolved blockers now exits cleanly without inference; it is not an adapter error.
- Some failed process runs have a separate `executionBlocker`. Setting Todo alone does not remove it. Inspect the failed run, verify what completed, then use the task recovery flow to reconcile outcomes and retry. Do not blindly replay unknown side effects.
- Internal children complete without human clicks only when created by the configured coordinator with the internal-handoff marker. Older tasks and direct assignments retain their review boundary.
- Historical failed/cancelled run records remain visible for audit; current agent status and the latest run determine whether a problem is still active.

- GPU unreachable: the runtime records an error and attempts to mark the task
  Blocked. Check the endpoint from HQ; AMD-GPU uses ZeroTier, NVIDIA-GPU uses verified HTTPS.
- Failed execution: inspect the task's recovery panel and run log. Reconcile the
  failed attempt before retrying if Paperclip requests execution recovery. Clear
  the agent's error state after resolving the cause, then retry the task.
- Invalid input/too much context/output truncated: split the task and retry.
- No work after clicking an agent's standalone Run button: assign a Todo task;
  each write must be associated with a specific task run.
- A task's result is a model-generated proposal, not proof that infrastructure
  actions were performed.

## Validation

September 26 workflow repair: **21 runtime tests**, authenticated browser check, and live tasks:

- **KRI-17 → KRI-38/KRI-39:** real NVIDIA-GPU and AMD-GPU inference, automatic child completion and parent synthesis. Verified token counts: NVIDIA-GPU 317/115, AMD-GPU 481/120 (input/output).
- **KRI-35 → KRI-36/KRI-37:** Pi JSON/report artifacts, AMD-GPU reading actual JSON, automatic parent resumption.
- **KRI-26:** three specialist activity briefs collected into a completed daily digest.
- **KRI-19:** repaired failed execution and deterministic task-board reporting.
- **KRI-42:** final artifact-publication check after strengthening Pi workspace handling.

Evidence and browser screenshot: `validation/networkchuck-upgrade/`. Historical failures are preserved. Model prose is advisory and can be wrong; task state, runtime metrics and raw artifacts are the evidence. Task-board reports and daily briefs use API records directly to avoid invented task descriptions.

Earlier pilot checks:

- `python3 -m unittest -v test_runtime.py test_department.py`: **14 tests passed**, including review
  without reassignment, dependency completion, input bounds, GPU queue timeout,
  truncated responses, recent-history order, and optional Pi delegation.
- Runtime lifecycle evidence (local runtime/history reference; excluded from this source edition): KRI-7 delegated
  to NVIDIA-GPU child KRI-8; both initial runs succeeded. Human child approval/completion
  automatically resumed the parent, whose third run succeeded without inference.
  Both smoke tasks were reviewed and marked Done.
- Browser validation (local runtime/history reference; excluded from this source edition) and
  dashboard screenshot (local runtime/history reference; excluded from this source edition).
- NetworkChuck reference notes (local runtime/history reference; excluded from this source edition).
- Pi exact-file evidence (local runtime/history reference; excluded from this source edition): KRI-13 wrote, verified,
  and published the exact requested 13 bytes using real tools.
- Pi health-report evidence (local runtime/history reference; excluded from this source edition): KRI-14 delegated
  KRI-15, which collected both GPU APIs and published valid JSON and a report.
  Both runs succeeded; KRI-15 awaits your review. This checks API reachability,
  not GPU temperatures or host disk health.
- Cancellation evidence (local runtime/history reference; excluded from this source edition): cancelling KRI-16
  stopped the running tool process, with no late output or attachments.
- Timezone checks (local runtime/history reference; excluded from this source edition): HQ and NVIDIA-GPU use America/New_York
  with synchronized clocks; AMD-GPU SSH authentication still prevents its change.

## Before scaling

Measure completion quality, warm/cold latency and queue behavior with real tasks.
Then separate agent workers from the control plane, add a shared GPU scheduler
covering n8n and OpenWebUI, implement scoped tools for the desired workflows,
and add off-host backups/monitoring. The current Compose deployment is a single-HQ
internal pilot, not a highly available or multi-tenant deployment.

Official references: https://github.com/paperclipai/paperclip/blob/master/doc/DOCKER.md
and https://github.com/paperclipai/paperclip/blob/master/docs/adapters/process.md.

## October 24 operations update

Primary URL: **https://paperclip.example.invalid/KRI/dashboard**. DNS and the external reverse proxy already existed; this deployment now permits that hostname and uses it as the public/auth URL. Both hostname sign-in and the internal IP fallback were checked.

Assign **Local Coordinator** a task titled “Scan my network”, “Run a system health check”, “Diagnose my systems”, or “Ask Codex to review this error”. The first three route to fixed observational tools. Explicit Codex requests route to the account-backed engineer. Direct assignments to the named agents also work.

| Agent | Capability and limits |
|---|---|
| Network Discovery | TCP connect discovery on 192.0.2.0/24, ports 22, 53, 80, 443, 445, 8006, 8443, 11434. No UDP/vulnerability probes or user-supplied targets/commands. No reply is not proof of an offline host. |
| System Health Observer | Authenticated GPU API checks plus timestamped HQ and NVIDIA-GPU CPU/load, memory, root disk, failed-service and GPU observations. JSON and Markdown attachments. |
| System Diagnostics | Same fixed host/GPU evidence, including failed services and HQ container states; no arbitrary commands or host modifications. |
| Codex Escalation Engineer | ChatGPT account-backed workspace code/debugging. Live file creation and executable byte verification passed. No host SSH keys or host Docker socket are mounted. |

`operations/inventory.json` records the first 31 responding addresses. Identity is verified only for HQ and NVIDIA-GPU; port 8006 is a service hint, not verified Proxmox identity. Discovery artifacts are kept on the task. AMD-GPU API checks succeed, but AMD-GPU SSH authentication fails and its host health is explicitly unknown. Proxmox, NAS, switches and other discovered hosts need their own observer access before authenticated health claims are possible.

The existing Daily GPU health report routine now uses System Health Observer directly. Collection and Markdown rendering do not invoke a model. Coordinator aggregation of observational or Codex work also avoids an additional local inference request. Legacy coordinator-created GPU collection tasks use the same deterministic collector in Pi. Pi's general file tools remain available and passed a live write/assertion test.

Host observations refresh every five minutes using the user systemd timer `paperclip-observations.timer`, with lingering already enabled. The timer runs fixed, read-only commands on HQ and verified SSH commands on the configured hosts; neither task text nor model output controls commands. The application receives only a read-only snapshot mount. Snapshots older than ten minutes, or from the future, are flagged stale.

Codex login is stored in the private `data/codex-operator/` directory using the documented headless auth-cache provisioning method. No credentials are included in task prompts or reports. Local runtime failures can create one diagnostic Codex child per failed task, without copying environment values, raw logs or the task description. Escalation is idempotent, cannot recurse into Codex itself, and never automatically replays the failed operation. Proposed changes return for operator review. `codex_ready` and `escalate_failures` in `agents/department.json` control this behavior.

The live Codex run reported that kernel sandbox namespace creation was unavailable and runtime-approved fallback execution succeeded inside the existing container. The dedicated workspace is an organizational boundary, not a guaranteed filesystem sandbox. The shared server container still contains the pilot's inference credentials; do not assign it untrusted work.

### Add Linux observer coverage

`operations/install-observer.sh` is a self-contained enrollment script containing only a public key and a fixed read-only probe. Review and run it as root on a chosen Linux/Proxmox host. It creates a dedicated observer account with a forced probe command, no forwarding/PTY, a source-IP restriction, and no sudo grant. It is not a Synology or network-appliance installer.

Verify the target SSH host-key fingerprint through a trusted console and add it to the HQ user's known_hosts. Then add a target in `operations/targets.json`:

```json
"pve01": {
  "host": "192.0.2.50",
  "user": "paperclip-observer",
  "key": "/home/operator/krishadmin-hq/deployments/paperclip/operations/keys/observer"
}
```

The target loader permits only 192.0.2.0/24 and the already configured AMD-GPU overlay address, with at most 16 targets. Run `systemctl --user start paperclip-observations.service`, then inspect `operations/snapshots/host-health.json`. This probe observes the host OS; Proxmox guest/cluster/backup details and NAS storage health still require dedicated read-only API integration.

### QA, repairs and recovery

Evidence: `validation/operations-20261024/`, including browser checks, service checks, tests and a cancellation manifest. Key live tasks: KRI-250 (31-address discovery), KRI-252 (repaired routine), KRI-254 (Pi file/assertion), KRI-256/257 (deterministic coordinator handoff), KRI-258 (Codex account/byte assertion), KRI-259/260 (coordinator-to-Codex handoff). Review the evidence before marking report tasks Done.

59 queued/blocked tasks belonging to 20 superseded, read-only scheduled health-report families were cancelled with explanatory comments. Historical run failures were retained. One QA coordinator run was cancelled when it exposed unnecessary model synthesis; the corrected flow passed as KRI-256/257.

HQ's obsolete host `nginx.service` was disabled and its failed state cleared. It had failed since September because its old configuration bound missing address 192.0.2.21. Its config is preserved under `validation/operations-20261024/legacy-nginx/`. Paperclip, n8n and OpenWebUI container proxies all returned HTTP 200 after the change. Rollback of the enabled state is `sudo systemctl enable nginx.service`; starting it will still require resolving its obsolete address configuration.

Run `python3 -m unittest -v test_runtime.py test_department.py test_operations.py` for targeted QA. Run `python3 setup_operations.py` to reconcile existing agent configs; it does not copy account credentials or declare Codex ready without a prior successful test. The legacy setup script preserves operations targets and the repaired routine assignment.

Backups now include operations code/config/observer keys, Codex state, and the two user systemd units. Restore the units into the user's systemd directory, restore observation SSH files to their original paths, run `systemctl --user daemon-reload`, and enable the timer. Archives contain credentials and must remain private.

## Detailed decisions and compute receipts

Review requests now populate the existing Decisions card fields: task-specific title, concise findings, original request, missing work, compute used, evidence and the meaning of each choice. Expand **See more** in Decisions, or **Details** on a task's review card. Rich details are generated by `agents/review_details.py`; no upstream UI fork is required.

Accepting a result acknowledges only its stated scope; it does not authorize host changes or automatically rerun work. The existing confirmation flow still requires marking a task Done separately. Revision requests require an explanation. Network-only results explicitly say that authenticated host logs were not collected; requests mentioning logs are marked partially fulfilled with **Accept discovery only** / **Request log verification** choices.

Deterministic tools report HQ CPU/Python execution with no model, zero model tokens, measured collection time and run ID. Model-backed local work records the actual NVIDIA-GPU or AMD-GPU endpoint, model ID, tokens and duration. Pi distinguishes CPU tools from NVIDIA-GPU inference. Codex handoffs use native run receipts for cloud attribution and token usage, and mark exact model/hardware details unknown when not exposed. Coordinator receipts describe that step separately from its specialists.

The earlier deterministic collector footer incorrectly said NVIDIA-GPU inference and reported zero duration. The runtime no longer emits that footer. KRI-262/263 were corrected with an explicit operator notice and measured scan receipt: 32 responding addresses, 19.78 seconds, HQ CPU/Python, no model inference, and no host-log verification. Original comment text and the audit trail are retained in `validation/decision-details/`.

Fourteen pending generic review cards were enriched without changing their IDs, recipients, statuses or outcomes. The installed API has no interaction-edit route, so `enrich_pending_reviews.py` performs a guarded, presentation-only update, stores before snapshots and writes an operator audit event. It never changes governed tool/secret approvals, resolved cards or resolver policies. The KRI-261 review card, previously superseded by an operator documentation comment, was restored through the standard API.

QA: `python3 -m unittest -v test_runtime.py test_department.py test_operations.py test_review_details.py`. Live QA KRI-264 verifies a detailed decision and a structured execution receipt in the downloadable observations JSON. Browser evidence is in `validation/decision-details/`.

## Native Control Center and governed integrations (2026-10-30)

The native sidebar now includes [Control Center](https://paperclip.example.invalid/KRI/control-center), implemented outside the upstream checkout. It provides local-agent settings, pause/resume, external sharing policy, Proxmox and restricted Linux observers, per-agent read grants, access reviews, cloud/MCP setup links and audit history. See [the operator guide](control-center/OPERATOR-GUIDE.md) for exact scope and setup.

External Codex execution now explicitly uses the CLI adapter with agents/codex_guard.py. The ACP default bypassed a custom CLI command in initial QA; it is no longer used by this agent. Human approval of an exact task packet precedes dispatch to the isolated worker. A configured account cache is not a verified live call. The synthetic QA gate KRI-299 is pending approval; no outbound model call was approved during QA.

Local NVIDIA-GPU/AMD-GPU agents can opt into read-only MCP through the native gateway and its access/approval policy. KRI-298 verified an actual executable synthetic stdio transport; the bundled metadata-only fixture initially failed and was replaced for QA. The fixture is now disabled and temporary permissions restored. Proxmox token setup and personal cloud OAuth were deferred; those authenticated connections have not been verified.

Targeted validation: Python suites including test_control_center.py (45 tests), control-center/core.test.js (5 tests), browser persistence/navigation, scoped API rejection checks, live health/MCP receipts, worker isolation and synthetic worker execution. Evidence is in validation/control-center/.
