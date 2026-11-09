# 5. Discord operation

## Installed identity and scope

| Setting | Value |
|---|---|
| Bot | KrishAdmin-HQ-LLM |
| Application/bot ID | `900000000000000001` |
| Server | Dev server, `900000000000000002` |
| Channel | krishadmin-hq-llm, `900000000000000003` |
| Allowed operator | `900000000000000004` |
| Allowed friend | `900000000000000005` |

The configured policy restricts the allowed users/channel, disables DMs, requires a bot account mention, and disables history backfill. The tool surface includes eleven native operations and six MCP tools; see [Internet and long-context workflows](mcp.md). Native `/help` can list upstream commands and skills that are not part of this deployment's supported workflow; use this guide for supported commands. Live wrong-user/channel/DM denial tests remain an acceptance item.

## Allowed users

The owner and friend listed above can use the same supported tools in the private channel. This is a shared workspace: allowed users can access the bot’s uploaded files and drafts. Neither receives gateway administration commands through this grant. DMs remain disabled.

Allowed users are stored in `profiles/concierge/discord-enrollment.json`. Keep the profile allowlists synchronized and restart the concierge after access changes. Preserve `respond_without_mention=false`, empty `free_response_channels`, and true `require_mention` / `thread_require_mention`. Server membership and channel permissions remain separate requirements.

On 2026-11-03 UTC, Discord confirmed the friend is a server member with View Channel, Send Messages and Attach Files. The running gateway’s allowlist and adapter checks admitted both users and rejected an unlisted user and an unrelated channel; no test message was sent as the friend.

## Send a request

```text
<@900000000000000001> show current lab status
<@900000000000000001> show active warnings and recent changes
```

The private command channel requires an explicit mention of the bot account from either allowed user. Plain messages and bot role mentions do not trigger replies. Threads also require a mention. `/status` checks the Hermes session/gateway, whereas the ordinary status request obtains lab measurements. Other channels remain blocked; DMs remain disabled.

## Everyday prompt guide and compute routing

The Discord front desk is Donna, running Qwen3.5 9B on NVIDIA-GPU. She interprets the request, calls the fixed HQ tools, delegates specialist work and writes the final reply. A delegated request can therefore produce both NVIDIA-GPU and AMD-GPU inference receipts. Seeing NVIDIA-GPU activity does not mean the specialist ran on NVIDIA-GPU.

| Request | Specialist compute | How to select it |
|---|---|---|
| Major design decisions and comparisons | Jessica: Mixtral 8x22B / 140.6B MoE on AMD-GPU | Name Jessica and give the decision, options and constraints |
| Practical plans, priorities and incident interpretation | Harvey: Gemma 27B on AMD-GPU | Name Harvey and request a concrete plan or analysis |
| Code/config reviews and automation drafts | Louis: Qwen2.5 Coder 32B on AMD-GPU | Name Louis and supply code, configuration or an attachment |
| General deep analysis | Qwen2.5 72B on AMD-GPU | Explicitly request AMD-GPU analysis using hq_analyze |
| Mike's deeper review | Qwen2.5 72B on AMD-GPU | Ask Mike to escalate with compute=amd-gpu |
| Quick conversation, routine coordination and Mike's default work | Qwen3.5 9B on NVIDIA-GPU | Ordinary messages or Mike without escalation |
| Rachel's research | Qwen3.5 9B on NVIDIA-GPU; internet collection on HQ | Ask Rachel for research with citations |
| Jessica asks Rachel to research | Jessica on AMD-GPU, then Rachel on NVIDIA-GPU | Explicitly request Jessica → Rachel research |

Routing is based on the selected tool/agent, not simply mentioning a machine's name. “Show AMD-GPU status” reads measurements about AMD-GPU; it does not itself start an AMD-GPU model. SSH process checks run the fixed local probe on AMD-GPU's CPU. To exercise GPU inference, ask for specialist analysis. Final prose should identify the returned backend/model/run ID; use compute receipts for independent confirmation.

### Start with a small, verifiable AMD-GPU request

Select the bot account from Discord's mention picker, then paste:

```text
@KrishAdmin-HQ-LLM Harvey, use your AMD-GPU model to compare a single shared task queue with separate queues per GPU for our homelab. Give three tradeoffs and a recommendation. Include the actual backend, model and run ID returned by the tool.
```

This requests a real Gemma 27B inference, not just a health snapshot. Cold model loads and queued work can add latency. Completion means that particular inference ran; it does not mean the GPU remains busy afterward.

### Architecture and major decisions — Jessica

```text
@KrishAdmin-HQ-LLM Jessica, use your AMD-GPU model to design a reliable task flow between Discord, Hermes and Paperclip. Compare polling and webhooks, explain retry/deduplication handling, and recommend a phased plan. Treat this as a design proposal. Include your actual execution receipt.
```

### Coding and configuration — Louis

```text
@KrishAdmin-HQ-LLM Louis, review this Python function on AMD-GPU: def average(values): return sum(values) / len(values). Explain edge cases, propose a corrected version and list tests. Do not claim to have executed the code. Include the actual backend/model/run ID.
```

With a supported file attached to the same message:

```text
@KrishAdmin-HQ-LLM Louis, review the attached Docker Compose configuration on AMD-GPU. Check configuration errors, resource limits and recovery behavior. Explain the exact file section you reviewed and any remaining unread sections. Propose changes without applying them.
```

### Diagnostics followed by AMD-GPU analysis — Harvey

```text
@KrishAdmin-HQ-LLM Collect fresh AMD-GPU GPU and process diagnostics, then have Harvey analyze a short summary on AMD-GPU. Separate observed facts from hypotheses. Include sample timestamps and Harvey's model execution receipt; do not infer GPU inference from CPU usage alone.
```

This combines fixed local measurements with a separate GPU model inference. Large evidence should be summarized or split to fit the specialist's bounded prompt budget.

### Explicit deep analysis or Mike escalation

```text
@KrishAdmin-HQ-LLM Use hq_analyze on AMD-GPU to compare nightly full backups with weekly full plus daily incremental backups for a small homelab. Explain recovery tradeoffs and unknown assumptions. Include the actual model and run ID.
```

```text
@KrishAdmin-HQ-LLM Mike, escalate this comparison to AMD-GPU using compute=amd-gpu: should each GPU have its own work queue, or should one dispatcher manage both? Compare failure recovery and fairness. Include the actual execution receipt.
```

### Internet research combined with AMD-GPU

```text
@KrishAdmin-HQ-LLM Have Jessica ask Rachel to research current ROCm monitoring documentation. Jessica should frame the question on AMD-GPU; Rachel should use HQ web collection and NVIDIA-GPU analysis. Return findings, fetched source links and each agent's actual backend/model.
```

The research collector stays on HQ. AMD-GPU receives text for inference and does not browse. This sequence does not automatically send Rachel's finished report back to Jessica for a second review; ask for that explicitly as another step if needed.

### A tracked Paperclip task with a Discord result update

```text
@KrishAdmin-HQ-LLM Create a read-only Paperclip planning task assigned to Harvey: propose a retry and timeout policy for local GPU jobs. Run the specialist analysis on AMD-GPU. Return the task link and confirm automatic Discord result updates are enabled.
```

The named assignment chooses the model. This creates a durable task rather than a synchronous answer. The follow-up distinguishes awaiting review, done and blocked; none is automatically a successful test. Use a self-contained task description. Do not assume a previous upload is attached to a Paperclip task unless the tool confirms that transfer.

### Verify which GPU actually did the work

After a specialist request, ask:

```text
@KrishAdmin-HQ-LLM Show the latest actual AMD-GPU inference receipts using hq_status with view=compute. Include identity, model, timestamp, elapsed time and reported GPU residency. Separate these completed runs from current GPU utilization.
```

These receipts cover the Hermes relay, not every process/client on the host. A current GPU check can show an idle device after a successful short run. Loaded-model VRAM proves residency, not active inference. The relay records GPU residency after inference; this is stronger evidence for this workflow than a character name in the answer.

### Other useful everyday prompts

```text
@KrishAdmin-HQ-LLM Show current lab warnings using fresh evidence, including missing coverage.
@KrishAdmin-HQ-LLM SSH into AMD-GPU through the fixed diagnostics connection and show the top five processes by sampled CPU usage. Include the sampling interval and timestamp.
@KrishAdmin-HQ-LLM Rachel, research the current specifications of [exact product name] and cite the fetched manufacturer sources.
@KrishAdmin-HQ-LLM Read the attached document and summarize the section you can access. Tell me whether any content remains unread.
@KrishAdmin-HQ-LLM Save the proposed script as a downloadable draft. State what has and has not been tested.
@KrishAdmin-HQ-LLM Find the Discord runbook using hq_knowledge section=discord and explain how automatic task updates work.
```

Replace bracketed placeholders and attach files when requested. Supported uploads, file limits and the six-person roster are detailed in [capabilities](capabilities.md). Fixed SSH commands and their limits are in [diagnostics](diagnostics.md). The full documentation starts at the [guide index](index.md).

### If a response is wrong or unexpectedly limited

- A reply says “delegated” without findings: synchronous `hq_team` should return an actual analysis or an error. A roster response is not a completed handoff. Ask for the returned run ID.
- A machine is named but only NVIDIA-GPU appears: ask for a named AMD-GPU specialist or explicit AMD-GPU analysis. A status or SSH check alone is not GPU model work.
- A queued task appears stuck: ask for the status of its existing KRI identifier. Do not recreate it merely to retry; the task bridge uses durable deduplication.
- An upload is too large: request a bounded section and continue using the reported next offset. A partial read is not a whole-file review.
- A task's model is loading: allow for cold-load and queue time. Repeatedly resubmitting can add more work.
- A repair or arbitrary command is requested: the currently implemented tools support fixed diagnostics, analysis and drafts. They do not provide unrestricted remote shell access or deploy arbitrary scripts, even if a prompt says “approved.”

## Permissions

Keep the channel private. Give the bot member View Channel, Send Messages, Read Message History, Embed Links and Attach Files as needed. Do not grant Administrator. A private category/channel override can deny access even when the bot is installed. The previous HTTP 403/code 50001 was fixed by adding the bot member's View Channel override.

## Replace the exposed token

The enrollment token appeared in the setup chat and must be replaced. In the Discord Developer Portal, select this application, open Bot, and reset its token. Then run **on HQ**:

```bash
python3 /home/operator/krishadmin-hq/deployments/hermes/rotate_discord_token.py
```

Paste the replacement only into the VM terminal. Input is visible by the operator's chosen preference. The helper validates application ownership, stores a private local credential and recreates the concierge. It does not require a new invitation. Authentication sends the token to Discord over HTTPS; models do not receive it. Do not paste credentials into chat or shell command arguments.

Afterward run `python3 hq.py doctor` and send `/status` followed by a normal mention request. If Discord is disconnected, inspect the gateway's state and proxy reachability. Avoid publishing raw logs; they can contain private conversation content.

## New enrollment or recovery

`enroll_discord.py` is for initial enrollment or changing the selected IDs. `rotate_discord_token.py` is for token replacement. `enroll_amd_gpu_observer.py` is unrelated to Discord and needs the AMD-GPU account's login credentials.


See [the named team and expanded capabilities](capabilities.md) for model assignments, uploaded files, code/config review, draft artifacts, exact arithmetic, local knowledge and specialist task submission.

## Restart announcements

The private command channel is now configured as the gateway notification destination. For a planned restart, run:

```bash
python3 /home/operator/krishadmin-hq/deployments/hermes/restart_gateway.py
```

This writes the native planned-restart marker and restarts only the concierge. The running gateway announces shutdown to its configured home channel; the new gateway sends “Gateway online — Hermes is back and ready” after connecting. The marker remains pending if startup delivery fails. A bare Docker restart does not create the marker, so use this helper when both announcements are required.

Both restart messages were verified in Discord; see `validation/restart-notification-live.json`. Normal requests still require a bot account mention, even when a generic native shutdown notice says “send any message.”

## Automatic Paperclip result updates

Task submission/status replies now append a deterministic **Paperclip report** link at the bottom, using successful `hq_task` results from the current turn. Multiple tasks produce distinct links. The link opens the task's report, comments and evidence in Paperclip; queued tasks show their status until the report is ready. Existing Paperclip access controls still apply. Completion notifications reserve space for their final link and recovery marker before shortening the preview.

Normal replies use Discord's native Markdown-aware splitting, up to three chunks of at most 2,000 characters. Replies longer than 6,000 conservative UTF-16 units, or requiring more than three formatted chunks, use a `report.md` attachment containing the full response and a bounded preview. Paperclip links remain at the bottom of the visible preview. Streamed previews switch to the same attachment on the final edit. Files are generated in memory, limited to 5 MiB, and sent only to the original channel/thread/DM. Upload failure is explicit; an uncertain send is not automatically repeated by this wrapper. Personal Workspace content remains confined to each user's authorized DM.

Automatic task notifications remain compact summaries plus links; the complete agent report and evidence live in Paperclip. The attachment rule applies to ordinary long replies. Native adapter checks exercise short/split replies, full attachment bytes, final edits, thread destinations and upload failure using mocked Discord transport. Actual client rendering and channel Attach Files permission remain live acceptance checks.

New `hq_task` submissions from Discord capture the requester and source message from Hermes's session context, outside model arguments. The bridge saves a durable subscription in `state/tasks.db` in the same commit as the task mapping. Both allowed users receive this behavior. CLI submissions do not subscribe automatically. KRI-320 was explicitly enrolled as part of this repair.

`hq-hermes-task-notifications.timer` checks approximately every 30 seconds while available. When a task becomes `in_review`, `done`, `blocked` or cancelled, the bot posts a follow-up in the enrolled private channel. Later result/status changes edit that follow-up. Threads deliver to the main private channel. Unchanged polls do not create messages. Closed done/cancelled subscriptions stop polling; reopening those tasks requires a new subscription. Long outages, rate limits or API errors delay delivery.

`in_review` means execution completed awaiting review, not a passed test. A health result with no deterministic alerts is described as partial observation, not complete health. Model execution receipts are separate from snapshots captured before inference. Generic agent results are labelled as excerpts requiring review. Task URLs always use `https://paperclip.example.invalid/KRI/issues/IDENTIFIER`.

Pending sends survive restarts. The notifier uses a stable nonce, stores the delivered message ID and reconciles uncertain sends against channel history before retrying. If the bounded reconciliation cannot establish the outcome, it records an error instead of risking another post. Deleted update messages require operator review. This follows Discord's [message create/edit API](https://docs.discord.com/developers/resources/message). Only the original allowed requester may be mentioned; role/everyone mentions are disabled, and destinations are revalidated before each send. Normal conversation still requires a bot-account mention.

Troubleshooting on HQ:

```bash
systemctl --user status hq-hermes-task-notifications.timer
systemctl --user start hq-hermes-task-notifications.service
python3 hq.py doctor
```

`state/task-notifications/status.json` records poll time and error count. `task_watches` records message IDs, pending deliveries and sanitized errors. Never remove a pending record just to retry an uncertain send. Restored subscriptions should be reconciled against Discord before enabling the timer on a replacement gateway; never run two gateways against separate copies of this database.

GitHub reads and code proposals are owner-only; see [the GitHub workflow](github.md).
