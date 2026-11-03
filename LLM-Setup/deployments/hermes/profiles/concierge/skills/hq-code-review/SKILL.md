---
name: hq-code-review
description: Review uploaded code and configuration using Louis on AMD-GPU and fixed syntax checks on HQ.
---

For uploaded files, use hq_files list/read and validate where supported (Python, JSON, YAML, TOML). Delegate code_review or config_review to Louis with hq_team. For general AMD-GPU review use hq_analyze. Identify confirmed bugs, assumptions, concrete fixes and validation steps. Report file hashes and reviewed ranges; follow next_offset for additional chunks and never claim complete coverage from a slice. Syntax checking is not execution or unit testing. Save requested corrected files with hq_draft; do not deploy them.
