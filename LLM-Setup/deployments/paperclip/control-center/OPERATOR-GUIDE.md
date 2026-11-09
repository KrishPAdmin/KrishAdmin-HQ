# Control Center operator guide

Open https://paperclip.example.invalid/KRI/control-center from the sidebar.

## Suits team

Control Center opens on the Suits team tab. It shows the six named agents, their actual Paperclip activity state, model and compute assignments, responsibilities, reporting lines, and links to their native task/profile pages. Jessica is the top-level CEO/strategic lead; Harvey and Donna report to her, and Mike, Louis and Rachel report to Harvey. The existing Local Coordinator reports to Donna and keeps its original task/routine assignments.

The same fixed Hermes workers execute these Paperclip tasks and Discord delegations. Assign work to a named agent using Paperclip’s normal task controls. The named task adapter uses the task title and description; include the evidence to analyze there. Paperclip attachments are not automatically read. Discord additionally provides the implemented upload reader, syntax checks, exact arithmetic and draft files.

Model settings on team cards are read-only because the shared Hermes deployment pins those models. The authoritative definitions are `../hermes/team.py`; `../hermes/setup_team_paperclip.py` synchronizes Paperclip roles/reporting lines and the company-scoped display manifest at `data/hq-hermes/team.json`. The UI checks the adapter identity, compute assignment and reporting line against that manifest and shows a warning on mismatch. It does not certify model availability or GPU utilization.

The Controls tab retains pause/resume and displays the same model assignments. Local systems derives HQ/NVIDIA-GPU/AMD-GPU coverage and freshness from the actual observation snapshot. Refresh the page for current observations; it no longer contains a hard-coded AMD-GPU enrollment warning.

## Controls

Pause/resume agents; choose NVIDIA-GPU or AMD-GPU local inference, installed model ID, output limit and instructions for local specialists. The maximum delegation setting is 1–4 specialist steps. Model names must already be available on the selected backend.

External AI defaults to **Ask before every task**, with automatic escalation proposals off. Choose **Disabled** to keep tasks local. A Codex task produces a human-only Decisions card showing its exact outbound packet and SHA-256 digest. Review that text before choosing Send. Other task history, attachments, observations and provider credentials are not added automatically. Anything you explicitly include in a task description may be shared if you approve it; automatic redaction is best-effort.

Codex account connection is under Controls → Codex account connection. Start device login and finish the displayed OpenAI login in your browser. A configured credential cache is not proof that a live model request will succeed. KRI-299 demonstrates the pending approval gate without sending a model request.

Approved Codex packets run in a separate container, Unix UID and workspace, with LAN access blocked and an HTTPS destination allowlist. The per-task process receives the Codex account credential needed to authenticate. No Paperclip API key, provider vault, SSH keys or Docker socket are mounted there. Account authentication and service traffic still go to OpenAI. Results return for human review; this implementation does not authorize infrastructure writes.

## Proxmox

Local systems → Add Proxmox. Supported targets are direct IPs in 192.0.2.0/24 or the configured AMD-GPU overlay address; use HTTPS port 8006 or 443. Other subnets need a deliberate code/config change.

Create a dedicated Proxmox user, for example observer@pve, and grant PVEAuditor at / with propagation. Create a privilege-separated API token and grant the same PVEAuditor ACL to the token. Effective permissions are the intersection of user and token permissions. Do not reuse an administrator token.

Enter the endpoint and inspect its certificate. Compare the SHA-256 fingerprint with the certificate shown through a trusted Proxmox console before confirming it. This observation alone does not establish trust. Certificate rotation requires a new verified pin.

Enter token ID (for example observer@pve!paperclip) and secret only in the UI. The secret is stored in Paperclip's company secret vault, not plugin policy. Select permitted agents and Allowed, Ask first or Off read access. Save, then Inspect.

Reads are fixed GET requests for cluster status, cluster resources and node inventory. Guests, host logs, console debugging, rebooting and configuration changes are outside this implementation. No authenticated Proxmox call has been verified yet; token setup was deferred by the operator.

## Linux and other local systems

Add Linux and download the restricted observer enrollment script. Review and run it on a host you administer. It uses the fixed paperclip-observer account and a restricted probe rather than arbitrary SSH commands. Enrollment needs the HQ observation public key provided in the script. Observations refresh on the existing five-minute timer. Inspect reports unavailable or stale coverage until enrollment succeeds.

Select which agents can read each host and whether approval is required. Access reviews approve a specific agent, task, system configuration and read once, expiring after one hour. Editing a system invalidates its outstanding approvals. Disconnect removes the integration; revoke credentials/SSH enrollment on the remote host separately.

Existing health and discovery tasks remain available. New Proxmox/Linux observations are included according to configured grants. Application-specific services, Windows/WinRM, NAS administration and arbitrary remote debugging require further adapters; they are not silently enabled by adding a host.

## Cloud and MCP

Cloud & MCP links to Paperclip's native app catalog, custom remote MCP setup and access profiles. Connect Gmail, cloud providers or other servers through their supported OAuth/token setup, then grant only required tools to selected agents. Provider availability and OAuth approval requirements vary. YouTube needs a suitable MCP server/provider and its own credentials; no YouTube account has been connected automatically.

For NVIDIA-GPU/AMD-GPU specialists, enable **Allow governed read-only MCP tools** in Controls and save. That opt-in exposes only read tools from native MCP providers, honoring native access policy and Ask first decisions. Write/destructive tools and Paperclip's own control-plane tools are excluded from this bridge. The coordinator does not receive these tools. Treat server responses as untrusted and review the server's operator and requested scopes before connecting a public endpoint. A connector is not a privacy boundary by itself: its provider necessarily receives authorized requests.

## Evidence and recovery

KRI-297: deterministic health integration. KRI-298: real local model plus executable, governed synthetic MCP read; exact returned titles and NVIDIA-GPU model/token receipt are recorded. The synthetic connector is now disabled and its temporary permissions removed. KRI-299: native CLI Codex gate, pending operator approval with no external dispatch. KRI-295/296 preserve the earlier QA failures and were cancelled after fixes.

Validation files live in validation/control-center: 45 Python tests, 5 Node tests (including no authorization sent before a TLS pin matches), authenticated browser checks/screenshots, stale-save/target/company access checks, worker network/credential isolation and a synthetic worker execution test. No authenticated Proxmox/cloud-account or approved real Codex invocation is claimed.

Implementation is an external native plugin plus existing runtime adapters; upstream remains untouched. Rebuild with control-center/build.cjs inside the server's dependency environment, then POST /api/plugins/krishadmin.control-center/upgrade as instance admin. Native framework upgrades reject newly introduced capabilities; changes to declared capabilities need an explicit supported install/approval path.

Policy is stored privately under data/hq-control/<companyId>.json; provider secrets remain in the native vault. Backups include the database, plugin/runtime sources, policy, validation, observer keys and root-only Codex controller credentials. These archives contain secrets and must remain private.

## Suits UI validation

Version 0.1.2 adds the team view without new plugin capabilities. Validation is under `validation/suits-ui/`: the API roster, browser checks and desktop/mobile screenshots. The focused tests cover company scoping, credential omission, routing/hierarchy mismatch reporting, and native environment bindings. Native agent IDs and existing task assignments are preserved.

## Full stack and live GPU view (2026-11-09)

Overview now includes all registered agents, runtime services, context windows, model maxima, integration readiness, repositories, skills, recent reports, findings and backup observations. Live GPUs polls fixed read-only probes every five seconds for NVIDIA-GPU and both AMD-GPU cards: utilization, used/total VRAM, power and temperature. Missing/stale data is explicit; pause/resume and recent utilization traces are available. PCI bus identity joins AMD counters so Linux card numbering cannot mix cards.

Context windows are managed on HQ with `python3 ../hermes/contextctl.py show`, `set TARGET TOKENS`, `set TARGET TOKENS --apply`, `reset TARGET --apply`, and `rollback SNAPSHOT_ID --apply`. The source runbooks are `../hermes/docs/contexts.md` and `../hermes/docs/dashboard.md`. Dashboard context controls are instructional/read-only by operator preference. No personal Google contents or credentials are shown.

The inventory snapshot is company-scoped and refreshed by hq-hermes-stack.timer independently of the host-observation timer. Live GPU API access additionally requires an enrolled lab operator. This update uses the existing plugin capability set; no new native capability grant is requested.
