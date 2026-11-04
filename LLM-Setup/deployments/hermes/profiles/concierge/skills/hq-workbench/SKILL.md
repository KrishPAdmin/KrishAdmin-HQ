---
name: hq-workbench
description: Run repeatable system-check, upload-review and automation-design workflows with AMD-GPU analysis.
---

- mcp__workbench__check_system: enrolled target hq/nvidia-gpu/amd-gpu, one to three checks from overview/gpu/processes/services/storage. HQ gathers fixed diagnostics; AMD-GPU interprets them. Report unavailable checks and excerpt limits. CPU process activity does not establish GPU inference.
- mcp__workbench__review_file: doc_ file_id, question, code_review/config_review/summarize, offset. Reads a slice, runs supported syntax checks without executing code, then analyzes on AMD-GPU. Follow next_offset or explicitly state partial review.
- mcp__workbench__plan_automation: question and optional source/config text. Louis drafts on AMD-GPU. Include explicit inputs, idempotency, dry-run, validation and rollback. Use hq_draft to deliver a requested file. Never claim deployment, execution or scheduled runs.

For longer supplied text/file slices use hq_analyze, or explicitly delegate to Jessica. Qwen analysis and Louis use 32K model context; Jessica uses 64K. hq_analyze automatically selects Jessica when supplied evidence exceeds the ordinary review budget. Source slices are bounded at 50,000 UTF-8 bytes; paginate larger material. Report actual model/run receipts rather than inferring compute from a persona name.

Durable read-only tasks use hq_task and receive automatic Discord updates. The existing observation/monitor timers continue collecting independently. New recurring production jobs or repairs need a concrete, separately authorized operation; these tools do not expose arbitrary shell. Proposed responsibilities are not created Paperclip assignments.
