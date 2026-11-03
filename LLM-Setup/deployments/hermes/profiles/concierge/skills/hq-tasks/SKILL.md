---
name: hq-tasks
description: Submit read-only health, backup and incident-triage tasks to local Paperclip and check their status.
---

Use optional agent jessica, harvey, mike, louis, rachel or donna for a named specialist. Use hq_task with action submit and kind health, backup, triage, code_review, config_review, automation, plan, summarize, compare or research. A stable idempotency key is supplied by the runtime. On an uncertain submission outcome, stop and reconcile the existing Paperclip task; do not invent a fresh request to bypass deduplication. Return the real task identifier and local link. Task acceptance does not approve infrastructure changes.

Copy the returned `/KRI/issues/IDENTIFIER` URL exactly. When `discord_updates` is true, explain that a follow-up will arrive automatically in the private channel when execution finishes, awaits review or is blocked. Do not ask the user to poll. The follow-up is edited when results/status change. `in_review` does not mean passed; only describe check outcomes supported by evidence. Separate pre-inference snapshots from the task's actual execution receipt.
