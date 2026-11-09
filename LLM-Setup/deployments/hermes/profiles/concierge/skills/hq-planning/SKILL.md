---
name: hq-planning
description: Use Jessica and Harvey for strategic decisions, implementation plans and incident escalation.
---

Use Jessica for major architecture, risk and resource decisions; use Harvey for concise execution plans and delegation. Provide evidence and constraints, then request options, recommendation, validation and rollback. Human approval still governs production changes. Do not confuse a model decision with a completed infrastructure change. Use hq_status view compute to show actual GPU receipts when asked.

For a requested sprint or project plan, collect current repository status through hq_github project_status when the caller is the enrolled owner. Distinguish the observed backlog from suggested work. Ask for available time or deadline when it affects scope; do not invent velocity, capacity, estimates or committed owners. Have Harvey sequence the proposed work by dependencies, identify acceptance checks and blockers, and give Jessica the material tradeoffs. Save a requested Markdown plan with hq_draft. Creating a plan does not schedule calendar events or create Paperclip assignments; use their respective tools only when requested.
