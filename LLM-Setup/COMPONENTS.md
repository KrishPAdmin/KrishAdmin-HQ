# Included components and exclusions

The source manifest lists the selected deployment sources with output hashes. Both editions contain the full maintained Hermes tool plugin, six named worker definitions, profile instructions and HQ skills, GitHub proposal service, Discord enrollment/restart/task-notification helpers, fixed diagnostic probes, Paperclip adapters and Control Center UI source, n8n workflow exports, gateway configuration, tests and operational documentation.

The private edition also retains detailed installation inventory, hardware notes and historical setup documentation. The public edition generalizes host identifiers, GPU names, addresses, domains, Discord IDs and local installation bindings. Both are source snapshots requiring environment-specific provisioning.

Excluded from both editions:

- `.env` values, API/bot tokens, GitHub authentication, passwords, SSH private keys, TLS keys, auth cookies, invitation tokens and credential stores.
- Private conversations, bot session state, uploaded documents, drafts, proposal databases and task/runtime databases.
- Backups, raw logs, unreviewed API dumps, generated runtime evidence and screenshots containing private state.
- Vendored upstream repositories, dependency environments, node_modules, build bundles and caches. Build the UI from its source using the documented deployment dependencies.

`.env.example` files list required environment variables without secret values. Some installed provider configuration fields are replaced with explicit local-secret placeholders. Restore/re-enroll secrets locally and verify permissions before starting a service. No live system was reconfigured by producing these editions.

The Hermes source also includes two local stdio MCP servers, public search/page/weather collection, bounded native Discord attachment handoff, fixed workbench workflows, and long-context routing/compaction. See the [MCP runbook](deployments/hermes/docs/mcp.md).
