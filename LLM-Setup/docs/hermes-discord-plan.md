# Hermes workers and private Discord integration

Prepared 2026-11-02. Status: proposed; awaiting owner's direction before installation or configuration changes.

## Evidence and limits

Read-only inspection found the gateway at 192.0.2.180 with ZeroTier address 198.51.100.21. Its actual hostname is hq-gateway despite some documents using KrishAdmin-HQ. It has about 12 GiB available RAM and 64 GiB free root storage at inspection time. This supports a pilot of CPU-side agent services; GPU inference remains on the existing GPU machines and capacity must be measured under load.

Paperclip server, database, Pi worker and Codex worker report healthy container status. n8n and its database also report healthy. The five-minute Paperclip observation timer is active. These observations do not establish end-to-end application or remote device health.

No hermes command, standard ~/.hermes home, matching top-level /opt installation, or Hermes system service was found. This is not an exhaustive search of other hosts.

The newer Paperclip README documents NVIDIA-GPU qwen3.5:9b and AMD-GPU qwen2.5:72b-instruct-q8_0 integration, bounded workers, existing routines, and a Control Center for governed access. The operator guide says authenticated Proxmox setup was deferred and Linux access requires observer enrollment. Older inventory/n8n notes are partly stale. Verify current configuration and actual authenticated access during implementation; do not treat documentation as a live connection test.

No service configuration was changed during discovery. This plan is the only new artifact.

## Architecture

Discord -> Hermes concierge -> scoped local task bridge -> Paperclip tasks -> Hermes specialist workers -> fixed local operations -> evidence and result.

Paperclip stays the task ledger and approval interface. Reuse n8n for existing deterministic workflows. Each recurring job has exactly one scheduler: prefer the current Paperclip routine for agent work and existing n8n schedules for established workflows. Disable equivalent Hermes schedules unless a documented requirement needs one.

Use Hermes's native Discord integration with one bot token owned by the concierge gateway. Specialists run as separate profiles with separate memory and working directories. Profiles separate state, not operating-system privileges: apply container/user separation and narrow mounts independently. A Paperclip process adapter and a scoped bridge are implementation work; compatibility is not yet verified.

The Discord-facing process should have no management credentials, host Docker socket, broad SSH access, or unrestricted host terminal. Expose only the intended task submission/status/report operations. Workers access systems through fixed operations with validated targets and scoped identities. Do not rely on a skill's written instructions as an authorization mechanism.

## Initial agents

| Profile | Responsibility | Initial operations |
| --- | --- | --- |
| hq-concierge | Understand requests, submit tasks and report progress | Scoped Paperclip submit/status/result tools |
| lab-health | Summarize current service, host and GPU evidence | Read existing observations, approved health probes |
| backup-watch | Detect missing/failed backups and capacity issues | Read backup metadata and storage health; no deletion |
| incident-triage | Collect evidence and propose a repair | Bounded log/health reads on enrolled systems |
| maintenance | Execute specifically authorized repairs | Add after read-only pilot passes; exact named operations |

Start with the concierge and lab-health end to end; enable backup-watch and incident-triage when their real data sources are enrolled. Do not present unenrolled systems as monitored.

## Skills and access tools

Create a versioned local skill collection, validating each skill against the installed Hermes release:

- hq-inventory: approved systems, identifiers, dependencies and supported observations.
- paperclip-tasks: submit/status/evidence with task-scoped credentials and bounded output.
- lab-health: use the current observation pipeline and report timestamp/staleness.
- gpu-health: NVIDIA-GPU/AMD-GPU availability, installed models and measured inference checks.
- proxmox-observe: cluster/node/guest/storage evidence only where the adapter and token support it.
- linux-observe: restricted SSH probe and bounded diagnostic output on enrolled hosts.
- backup-status: actual job metadata, freshness and restore-test evidence.
- n8n-operations: specific workflow status and explicitly permitted workflow triggers.
- incident-report: evidence, uncertainty, proposed action and verification steps.
- approved-maintenance: later, operation-specific execution and verification with durable approval records.

Add Synology, UniFi and PiKVM/BMC skills only after confirming versions, interfaces, credentials and requested scope. The current adapters do not already provide those capabilities.

Credentials stay in protected local stores, with references in skill configuration. Never embed credentials in skills, prompts, source control, reports or Discord messages. Reuse the existing credential stores where appropriate; a new secrets platform is a separate decision, not a prerequisite for read-only work.

## Discord

Proposed bot name: KrishAdmin HQ. Proposed channels: #hq-commands, #hq-alerts and #hq-reports. Existing channels can be reused.

Connect through the outbound Discord Gateway; no new public inbound listener or router port-forward is needed for that connection. Start with numeric owner ID authorization, the intended server/channel restrictions, mentions required, DMs disabled, no bot-to-bot triggers, and no channel-history backfill. Verify effective authorization for messages, threads, slash commands and interactive controls against the pinned version. Channel restriction alone must not grant all members access.

Use the native adapter and native skill commands where supported; custom command/routing behavior must be implemented and tested before being advertised. Give the bot only necessary channel permissions. Enable Message Content Intent required by the current Hermes adapter; additional privileged intents only if the selected features require them.

Discord is an external service even for a private server. Default outbound content: minimal redacted status, task ID and local evidence link. Keep raw logs and infrastructure change approvals in Paperclip initially. Confirm the owner's desired sharing and approval policy before enabling richer output or Discord-based approvals. A local link may require LAN/VPN access.

Owner-dependent setup: create or select a Discord Developer application, invite the bot, and enter its token directly into a protected local secret file/setup flow. Collect server ID, channel IDs and owner user ID as non-secret configuration. Do not request the token in chat.

## Delivery sequence

1. Reconcile inventory with live configuration, inspect existing grants/routines, and capture baseline and recovery information. Confirm first jobs and access policy with the owner.
2. Select and pin a Hermes release, review its actual configuration schema and tool controls, and install an isolated pilot with restart supervision and resource limits.
3. Verify a local model's tool-calling behavior using a harmless real tool. Start with the documented NVIDIA-GPU model; test AMD-GPU for larger analyses. No automatic cloud fallback. Coordinate GPU concurrency with the existing workers; current Paperclip locks do not cover all clients.
4. Implement the scoped Paperclip bridge, separate profiles and first skills. Reuse observation collectors and enroll only selected hosts. Run manual read-only tasks through the complete path.
5. Configure the Discord application and gateway, verify restrictions, and test an authorized request from Discord through Paperclip to evidence and back.
6. Enable selected schedules in America/New_York with overlap prevention, deduplication, bounded retries, timeouts, alert cooldowns and durable run identifiers. Preserve existing working routines.
7. Verify backup/restore and service recovery, document operational commands and limits, then consider specifically preauthorized maintenance operations.

Each task records requester, target, operation, evidence timestamp, model/backend when used, result and verification. Report unavailable or stale evidence explicitly. Treat logs, attachments and service responses as untrusted input.

## Acceptance criteria

- Authorized Discord requests produce the correct task, actual evidence and a traceable result.
- Other users/channels/servers and disabled DM paths cannot invoke operations; test threads and interactive commands too.
- Repeated delivery/restart cannot duplicate a submitted task or repeat a completed side effect.
- Each job has one active scheduling owner; missed and overlapping jobs follow the documented policy.
- Endpoint failures and stale observations are reported honestly with bounded retries.
- Secret canaries do not appear in prompts, Discord output, application logs or ordinary reports.
- Agent processes cannot access unrelated credentials, host administration or unrestricted remote commands.
- GPU contention, context limits, queue wait and model failures are measured with existing services running.
- A bot crash and reconnect recover cleanly; boot persistence is tested in an agreed maintenance window.
- A protected backup restores into an isolated test instance without connecting a second copy of the production bot or enabling duplicate schedules.
- Stop/disable procedures and release rollback are documented and exercised where safe. State migrations require a compatible restore strategy.

A bot running on this VM cannot independently report a total VM or network outage. If that coverage is wanted, add a small independent monitor on another existing host.

## Decisions needed

1. Approve the overall design and nominate the first three repetitive jobs and target systems.
2. Choose initial authority: read-only automation with per-action maintenance approval (recommended), or name exact preauthorized repair actions.
3. Confirm local-only inference (recommended starting point), or specify permitted cloud use and budget.
4. Identify the Discord server/channels/owner IDs, whether a bot application exists, and whether minimal summaries with local approval links are acceptable.

## References

- Existing deployment: ../deployments/paperclip/README.md
- Existing access policy: ../deployments/paperclip/control-center/OPERATOR-GUIDE.md
- Local credential practices: credential-security.md
- Hermes profiles: https://hermes-agent.nousresearch.com/docs/user-guide/profiles
- Hermes Discord: https://hermes-agent.nousresearch.com/docs/user-guide/messaging/discord
- Discord Gateway: https://docs.discord.com/developers/events/gateway

Upstream documentation reflects the current published docs. Verify every used option against the selected release before deployment.

## Implementation update, 2026-11-02

Owner approved the design, read-only automation and local compute. Network research must run on HQ or NVIDIA-GPU, never AMD-GPU. Pilot implementation and current blockers are recorded in [the deployment runbook](../deployments/hermes/README.md). NVIDIA-GPU GPU recovery needs the requested owner approval; Discord account enrollment remains pending. AMD-GPU uses a tool-free Ollama analyst because the installed model advertises a smaller context than current Hermes requires.
