---
name: hq-health
description: Inspect local lab health and backup coverage using the restricted HQ observation tool.
---

Call hq_status for fresh evidence. Report snapshot age and each missing observation explicitly. API reachability is not hardware health. Backup metadata is not a restore test. Never label the whole lab healthy. Keep detailed logs local. For a durable report, submit a health, backup or triage task through hq_task.

Report GPU API reachability separately from host telemetry; missing AMD-GPU host telemetry is not an inference API outage. Loaded model memory does not prove active inference. Distinguish database restore passed from full application recovery not tested.

For warnings and recent changes use hq_status with view alerts. Report current assessment.alerts separately from setup_items and dated history. Historical resolved events are not current incidents.
