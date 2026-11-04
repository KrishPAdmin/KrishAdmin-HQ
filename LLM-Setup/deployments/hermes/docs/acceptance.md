# 11. Acceptance and remaining work

## Verified on 2026-11-02

- Private Discord bot connects, `/status` replies and a normal mention returns a model-backed lab report.
- NVIDIA-GPU GPU initialization recovered after the explicitly approved Ollama container restart. Broker receipts confirm positive model GPU memory residency.
- AMD-GPU inference API is reachable; source collection remains on HQ. A real approved documentation fetch followed by AMD-GPU analysis completed with no analyst tools.
- The restricted AMD-GPU observer was enrolled by the operator; HQ, NVIDIA-GPU and AMD-GPU now provide basic host measurements.
- Fresh Paperclip and n8n full local database backups restored into isolated networkless temporary PostgreSQL containers. Archive integrity passed. Temporary containers were removed.
- Hermes configuration/state archive extraction, credential roundtrip and SQLite integrity passed.
- The monitoring rules, history behavior, CLI reports and diagnostics are tested. These results are basic operational checks, not complete system certification.

## Evidence to consult

| File | Evidence |
|---|---|
| `../validation/status-after-amd-gpu-enrollment.json` | Successful host/API coverage |
| `../validation/research-live.json` | HQ source collection → tool-free AMD-GPU analysis |
| `../validation/gpu-inference-receipts.json` | Post-recovery GPU memory receipts |
| `../profiles/concierge/concierge-validation.json` | Native status tool loop |
| `../profiles/concierge/concierge-validation-task.json` | Native task submission loop |
| `../profiles/concierge/concierge-validation-alerts.json` | Native alerts tool loop, created during this feature acceptance run |
| `../validation/doctor-after-features.json` | Latest local diagnostic result |
| `../validation/operator-report-20261102.md` | Example readable report |
| `../validation/feature-acceptance.json` | Final feature acceptance summary |
| `../validation/backup-restore.json` | Latest Hermes archive validation |
| `../../paperclip/backups/20261102T222443Z/restore-validation.json` | Paperclip database restore and archive validation |
| `../../n8n/backups/20261102T222514Z/restore-validation.json` | n8n database restore and archive validation; root-only |

## Operator decisions still required

| Item | Why it remains open | Next step |
|---|---|---|
| Discord token rotation | Original token appeared in setup chat | Reset in Developer Portal; run local replacement helper |
| Nightly full-backup schedule | Recurring n8n interruption has not been explicitly approved | Approve prepared 03:30 America/New_York schedule or choose a window |
| Off-host encrypted backups | Destination and public encryption recipient are not supplied | Identify host/share/path, credential method and offline key custody |
| Retention | No automatic deletion policy selected | Set retention after measuring backup growth and destination capacity |
| Full recovery | Database restores do not establish complete application usability | Test restored login, credentials, workflows, attachments and boot in isolation |
| Live negative Discord tests | Configuration/policy checks are not a full adversarial platform exercise | Test unauthorized user/channel and DMs without broadening permissions |
| Additional systems | Proxmox, Synology, UniFi and PiKVM/BMC identities/credentials are not enrolled here | Add scoped access only for the chosen systems and operations |

## Feature choices made while the operator was away

Added local fixed-rule monitoring, bounded history, read-only diagnostics, report export and a maintained reference guide. Default thresholds and retention counts are explicit in the monitoring chapter. No new automatic Discord messages, repair tools, destructive actions, recurring application interruptions or cloud fallback were enabled. Existing explicit approvals and network boundaries remain in force.

## Suits team and file capabilities — 2026-11-03 UTC

All six named specialists completed real inference with their pinned models. Jessica, Harvey and Louis used AMD-GPU; Mike, Rachel and Donna used NVIDIA-GPU. The default health route also used AMD-GPU. Harvey’s sample warm request took 2.305 s versus Jessica’s 4.747 s; cold loads and different response lengths limit this comparison. These are execution checks, not a model-quality ranking.

Louis completed Paperclip task KRI-319 with actual AMD-GPU evidence and left it in review. A native Hermes coordinator loop validated a cached Python upload, delegated review to Louis and saved a corrected draft. Separate extraction checks passed for text PDF, DOCX and XLSX, with formula text unexecuted. The calculator returned exact decimal results without inference.

The regression suite passes 49 Hermes tests and 2 n8n backup tests. See `validation/suits-acceptance.json`, `team-benchmark-live.json`, `suits-paperclip-result.json`, `file-formats-live.json`, `discord-friend-access.json`, and the concierge’s `concierge-validation-files.json` / `concierge-validation-team.json`. Current service and observation checks are in `validation/doctor-after-suits.json`.

A real user-upload-and-download exchange in Discord remains to be checked; the successful file test used a known cached fixture and the real coordinator tools. Research now supports public search, readable HTTPS sources and weather; see [MCP workflows](mcp.md) for current validation and limits. Code/configuration drafts are review artifacts; no arbitrary code execution or automatic deployment is enabled. Existing token-rotation, off-host-backup, full-recovery and recurring-backup decisions above remain open.


## Task follow-ups and process interpretation repair — 2026-11-03 UTC

- Corrected all bridge-generated task URLs to `/KRI/issues/IDENTIFIER`; a signed-in browser opened KRI-320 successfully.
- KRI-320's result update was delivered and read back through Discord's API. It distinguishes review status, partial health observations, and the actual AMD-GPU Qwen 72B execution receipt (93.382 seconds). Subsequent polls retained one message with no delivery errors.
- Tested requester authorization, durable subscriptions, no messages before completion, edit-in-place status changes, interrupted-send reconciliation, stable-nonce retries and later permission removal. Native Hermes session-context capture was tested without submitting a test task.
- Installed and exercised one-second CPU process sampling on AMD-GPU. Replayed the user's exact SSH/top-five request through the real concierge model and tool loop: it used `hq_diagnostics` directly and did not equate CPU usage with GPU inference.
- Mention-only behavior remains verified for owner/friend; plain and role-only mentions, unlisted users and unrelated channels are rejected.
- Receipts: `validation/task-and-process-repair.json`, `validation/task-notification-live.json`, `validation/task-link-browser.json`, `validation/amd-gpu-process-sample.json`, and `profiles/concierge/validation-process-request.json`.

The managed research regression also passed: the real concierge called Jessica → HQ source search/fetch → Rachel, returned the fetched specification citations and disclosed excerpt limits. The corrected short tool-call handling cannot silently substitute a roster for delegation. See `profiles/concierge/validation-managed-research.json` and `validation/managed-research-receipts.json`.

## Internet/MCP and long-context acceptance (2026-11-03 local time)

The maintained test suite passes 96 checks. Native Hermes exposes two MCP servers with six tools alongside the eleven native tools. Toronto weather, public research, AMD-GPU checker/automation execution and native attachment-fixture review completed. Actual syntax validation ran for the Python fixture; binary documents correctly skip unsupported syntax validation. Jessica recovered all three markers from a 12,369-token input at a 65,536-token allocation. Native compaction processed 26,769 tokens on AMD-GPU and reduced 157 KB of synthetic history to about 66 KB. Both receipts reported the entire loaded allocation in VRAM. Ordinary file analysis used a 32,768-token allocation. AMD-GPU inference-container network metadata remains internal; no external research requests were executed there.

These checks do not establish perfect model answers, maximum-window accuracy, arbitrary code execution, or a real post-update user attachment exchange. Current limits and repeatable validation commands are in [the MCP runbook](mcp.md).
