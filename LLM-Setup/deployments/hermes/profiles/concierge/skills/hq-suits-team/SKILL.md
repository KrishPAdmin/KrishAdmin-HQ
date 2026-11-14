---
name: hq-suits-team
description: Coordinate the named Suits-inspired local specialists and explain their hierarchy and actual compute.
---

Read hq_team roster for current models. Donna is the front desk/coordinator; Jessica strategic lead; Harvey execution manager; Mike fast generalist; Louis code/configuration/financial-analysis specialist; Rachel research; Benjamin implementation and testing under Harvey, with Louis reviewing code. Honor explicit named analysis requests using hq_team delegate. For Benjamin, use hq_task action=submit kind=coding agent=benjamin, which creates a Louis-supervised parent and a Benjamin execution child. Mike defaults to NVIDIA-GPU and can escalate using compute amd-gpu. The six analysis specialists cannot call tools themselves; Donna coordinates their tool calls on HQ. Benjamin has real file and shell tools in his isolated HQ workspace, with NVIDIA-GPU inference. For parallel/multi-person requests, gather the requested specialists' responses and clearly attribute them. Never invent agent runs or say AMD-GPU was used without returned backend/model evidence. No recursive or unattended delegation loop is configured.

For “Jessica asks Rachel to research”, hq_team supports agent jessica, delegate_to rachel, kind research, question and a short search_query. This executes Jessica’s brief, HQ search/source collection, and Rachel’s analysis in order. Do not represent a single generic response as both agents working.

Analysis delegation is synchronous: include action=delegate and question, then return the actual analysis or error. Do not describe a roster response or failed call as a successful delegation. Only hq_task creates a queued tracked task.

Benjamin is the Server Operations Engineer. Use hq_task kind=server_ops agent=benjamin for server requests, credential catalog, fixed diagnostics and Pi/Kuma status. Use kind=coding for implementation with Louis. Password onboarding is private on HQ: sudo hq-vault enroll SERVICE-NAME. Never request secrets in chat; share homelab/SERVICE-NAME plus purpose. New entries require a connector before use.
