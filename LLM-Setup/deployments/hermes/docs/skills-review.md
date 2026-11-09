# Skills and public MCP review — 2026-11-09

Reviewed the [agentic-skills topic](https://github.com/topics/agentic-skills) and the [PM Skills collection](https://github.com/phuryn/pm-skills), including its sprint-plan instructions at revision `9af7bfd0bc47fdad43c2eaa7a43cd13918e7aaef`. Topic membership and popularity do not establish code safety. No bulk installer or downloaded executable was run.

| Workflow | Installed implementation | Boundary |
|---|---|---|
| Project status digest | New hq-project-status skill + hq_github project_status | Two enrolled repositories; owner authorization; bounded issues/PRs/CI/commits |
| Sprint/change planning | Expanded existing hq-planning skill; Harvey/Jessica | Proposed priorities, dependencies and acceptance checks; no invented capacity or automatic assignments |
| Personal inbox and calendar | New hq-workspace skill + host connector | Individual OAuth; one-to-one DMs; local previews and separate exact confirmation for every write |
| Research briefs/source checking | Existing hq-research and research MCP | HQ search/read/render; source timestamps and citations; AMD-GPU synthesis; no account cookies or private network fetching |
| Code/config review and automation drafts | Existing Louis/file/workbench workflows | Bounded uploads, syntax validation, saved drafts; uploaded code is not executed |

These are maintained local instructions tied to implemented tools. The planning extension uses general sprint-planning concepts from the reviewed PM Skills material without its assumptions about team velocity or automatic commitment.

[MicrosoftDocs Agent-Skills](https://github.com/MicrosoftDocs/Agent-Skills) is a possible later addition for Microsoft/Azure work. No Azure workflow is currently requested or enrolled, so it was not installed. Generic terminal, browser-account, auto-send, auto-merge and infrastructure-mutating packs were not enabled.

The existing research and workbench MCP servers run as local stdio processes inside the concierge. They collect validated public internet sources through HQ and expose no incoming public endpoint. Gmail/Calendar uses the authenticated host connector to bind each request and confirmation to an independently verified Discord user. Connecting a generic remote MCP server would not supply that identity boundary by itself.

Future expansion should add one reviewed tool/provider at a time, pin executable versions, define account/repository scope and verify real output. New repositories can extend the server allowlist after owner enrollment; new users must be enrolled and authorize their own Google account separately.

## Public MCP candidates reviewed

- [GitHub's official MCP server](https://github.com/github/github-mcp-server) covers repositories, issues, PRs and workflows. The current host integration already meets the two-repository request and enforces the existing Discord identity/confirmation checks. A future replacement should preserve those checks and use narrowly scoped GitHub credentials.
- [Microsoft Learn MCP](https://learn.microsoft.com/en-us/training/support/mcp) is a public, unauthenticated documentation search/read service at `https://learn.microsoft.com/api/mcp`. It is a reasonable optional addition for Microsoft documentation work; it was not enabled for this Linux/Hermes repair.

Neither candidate is advertised as installed. Public web research remains available through the existing validated HQ research tools.
