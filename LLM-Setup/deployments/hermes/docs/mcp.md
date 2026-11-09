# Internet research, MCP tools and long-context work

2026-11-09: The native tool list now also includes `hq_workspace` (individual OAuth and verified one-to-one DM only). The two local MCP server tool lists remain the same. Research can fetch candidate primary URLs when searches are insufficient, preserves context around relevant excerpts, performs a separate source-review pass, and delivers completed simple specialist research without a coordinator rewrite. See [repair validation](repair-2026-11-09.md) and [Workspace enrollment](workspace.md).

## 1. Architecture and routing

Discord connects to Hermes on HQ. Donna uses NVIDIA-GPU for fast tool selection and short replies. Substantive ordinary research, analysis, file review and checker interpretation use AMD-GPU. Jessica's Mixtral supports a 65,536-token context; Qwen 72B analysis and Louis's coder model use 32,768. Harvey retains 8,192. Named Rachel requests retain her NVIDIA-GPU model.

Web collection, uploads, MCP servers, SSH transports and GitHub credentials remain on HQ. AMD-GPU receives text for inference, without executable tools or outbound research. Nothing is newly exposed to incoming public internet connections. The two MCP servers use local stdio subprocesses in the isolated concierge container and call the authenticated HQ broker. There are no runtime package downloads or third-party MCP account credentials.

Long conversation history is compacted before the 64K coordinator window fills. Compaction uses Jessica's AMD-GPU model through a tool-free auxiliary route. Summaries are lossy; original local session history remains, but important exact source material should be read again. Upload contents are no longer automatically inserted wholesale into the conversation. The old 100,000-character broker rejection has been replaced with a bounded 600,000-byte transport ceiling; this is not a promise of an unlimited model context.

## 2. Tools

| Server/tool | What it does | Compute |
|---|---|---|
| research / search | Public search, provider outcomes, relevance warning | HQ, no model |
| research / read_page | HTTPS text/semantic metadata, optional sandboxed browser, find, pagination, hashes/time | HQ, no model |
| research / weather | Open-Meteo current modeled conditions and 3-day forecast | HQ, no model |
| workbench / check_system | 1–3 fixed checks followed by interpretation | HQ collection → AMD-GPU |
| workbench / review_file | Extract a slice, syntax-check supported files, review | HQ reader → AMD-GPU |
| workbench / plan_automation | Louis drafts an automation and verification steps, saved as Markdown | AMD-GPU |
| native hq_diagnostics | One fixed check plus AMD-GPU interpretation; bundle several with workbench | HQ → AMD-GPU |
| native hq_research | Read sources, assess coverage, follow up automatically and synthesize a cited brief | HQ → AMD-GPU |
| native hq_analyze | Code/config/document analysis; large input routes to Jessica | AMD-GPU 32K or 64K |

Hermes exposes MCP names as `mcp__research__search`, etc. Resource/prompt utility tools are disabled because these servers expose only the listed operations. The broker accepts exactly those names; an arbitrary filesystem, terminal or remote MCP tool cannot become available by appearing in a prompt. GitHub remains exclusively behind owner-authenticated `hq_github`.

## 3. Copyable Discord prompts

Mention the bot account in the enrolled private channel; ordinary messages still receive no reply.

- `@KrishAdmin-HQ-LLM What is the current weather in Toronto, Canada? Include the timestamp and source.`
- `@KrishAdmin-HQ-LLM Research asyncio TaskGroup exception handling from current Python documentation. Use AMD-GPU to synthesize the findings and cite sources.`
- `@KrishAdmin-HQ-LLM Read https://docs.python.org/3/library/asyncio-task.html, find ExceptionGroup, and explain the relevant section.`
- `@KrishAdmin-HQ-LLM Run the AMD-GPU checker with GPU and processes checks, then analyze the evidence on AMD-GPU. Separate CPU activity from GPU inference evidence.`
- Attach a Python/config/document file to: `@KrishAdmin-HQ-LLM Review this file using AMD-GPU, run supported syntax checks, and tell me the exact coverage.`
- `@KrishAdmin-HQ-LLM Jessica, review the attached long architecture document using your 64K AMD-GPU context. Identify contradictions and state any pages or text not reviewed.`
- `@KrishAdmin-HQ-LLM Louis, draft an idempotent disk-space checker with dry-run, validation and rollback. Give me a downloadable script; do not deploy it.`
- `@KrishAdmin-HQ-LLM Show the actual latest compute receipts.`

Assignments mentioned in a plan are proposals. Only a returned Paperclip issue identifier proves a task was created. A status of in_review means awaiting review, not automatically passed.

## 4. File support and coverage

Supported: UTF-8 text/code/config/CSV, text PDFs, DOCX, XLSX, up to 5 MiB per upload. Supported syntax checks: Python, JSON, TOML and YAML. Code, spreadsheet formulas and macros are not executed. Images, scanned PDFs, archives, audio and video do not have OCR/transcription support here.

Uploads pass through the native authorized Discord attachment downloader to the cache, then appear as `doc_...` IDs. The reader accepts no arbitrary paths or symlinks. Extracted text is limited to 100,000 characters, PDF extraction to 100 pages. Read slices and follow `next_offset`; the larger analysis route accepts at most 50,000 UTF-8 bytes per source slice. Large Unicode text may require smaller character slices. Files posted in this shared private channel should be treated as visible to its authorized users.

## 5. Repeatable operations

The workbench provides repeatable, fixed workflows; existing evidence and monitor timers continue collecting automatically. `hq_task` provides durable Paperclip execution, deduplication and result notifications. The toolset can draft new scripts/configs and run supported syntax checks, but does not execute arbitrary uploaded code or enable new recurring service interruptions. Full application restores, arbitrary browser interactions and unattended infrastructure repairs are not implied by this setup.

## 6. Failure handling and verification

Search providers can rate-limit, challenge or return irrelevant results. Review provider attempts and relevance_warning, refine the subject, or provide a direct primary URL. `read_page` exposes download truncation and next_offset. Private/loopback/link-local destinations, credential-bearing URLs and non-HTTPS fetching are blocked with DNS-pinned connections and redirect revalidation. Use render=true for JavaScript pages. Authenticated pages, paywalls and bot challenges may still need another permitted source; no claim of universal browsing is made.

Current weather is modeled data, not guaranteed station observation. Report the resolved location and data timestamp; a fresh HTTP response alone does not prove fresh forecast data.

If a long prompt fails, inspect the returned model/context receipt and gateway compaction logs. Do not delete the conversation as the first repair. Source pagination remains necessary even with larger windows. Large AMD-GPU models share the accelerator queue, so concurrent requests can wait; busy/timeouts are failures, not successful handoffs.

Operator checks: `python3 hq.py doctor`, `python3 hq.py compute`, `python3 -m unittest discover -p 'test_*.py' -q`. Native integration checks run inside concierge using `validation/check_cloud_workflows.py` with discovery, weather, research, subscriber, file, checker or automation. They send no Discord messages; the file case uses a synthetic native attachment event, not an actual user upload. Runtime receipts stay local and are excluded from both GitHub exports.

## 7. Configuration, update and rollback

Maintain `prepare.py`, `mcp_server.py`, `web_research.py`, `broker.py`, `plugin/attachments.py`, profile config/SOUL and skills together. `prepare.py` preserves enrollment and installs the maintained MCP/compaction settings. Run tests, restart affected workers, then use `restart_gateway.py` for the native offline/online notices. A new mount needs compose recreation plus the planned-restart marker. Never publish access/, sessions, uploads, generated receipts or credentials.

Restore the prior reviewed source/config snapshot to roll back, preserving enrollment and secrets. Disabling MCP servers alone does not undo broker or context changes; verify the model route and current tool list after restart.

References: [Hermes MCP configuration](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp/), [MCP stdio transport](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports), [Ollama context length](https://docs.ollama.com/context-length), [Open-Meteo API](https://open-meteo.com/en/docs).

## 8. Research depth and dynamic pages

The original subscriber-count failure was real: the reader limited downloads to 300 KB and removed script data containing the channel header. The reader now permits 8 MiB for YouTube pages and 2 MiB for other readable sources, extracts semantic HTML/JSON-LD, and reads YouTube's primary channel header separately from recommended channels. It reports public subscriber counts as approximate, never as an exact private total. Channel layouts can change; missing header data must stay missing rather than being substituted with another channel's count.

`hq_research` checks the collected excerpts using AMD-GPU, then runs up to two focused follow-up searches on HQ if the answer is missing. It reassesses the evidence and returns supported, partial or no-source status. The final answer should state what was found, cite sources and disclose remaining gaps. For partial results the coordinator can use additional search/read calls, without asking permission for ordinary research. Search-provider rate limits and relevance limitations still apply. Search snippets are discovery, not authoritative evidence. Research is bounded; absence from its results does not establish nonexistence.

`mcp__research__read_page` accepts `render=true`. Thin script-based pages also trigger rendering automatically. A fresh Playwright Chromium instance runs on HQ as a non-root user with Chromium sandboxing, read-only filesystem, no credentials or host files, and only an internal Docker network. HTTPS GET resources pass through `render-fetch`, which pins validated public DNS addresses and rechecks every redirect. The browser cannot directly contact public or private networks. Website POSTs, WebSockets, service workers, images/media/fonts, downloads and persistent login state are disabled. The relay exposes no user-selected headers or cookies.

Browser limits: one render at a time, 45-second browser deadline, 64 requests, 2 MiB per resource, 16 MiB aggregate, and 80,000 characters of DOM text. The reader returns slices up to 8,000 characters. Busy, blocked, oversized or unavailable resources may leave a page incomplete. `browser_receipt` records rendered URL/time, DOM hash, request/byte counts, blocked requests and truncation. `body_sha256` covers fetched HTML; the separate DOM hash covers rendered text. If rendering fails, `render_error` is explicit and the HTML evidence remains available. There is no CAPTCHA, login or paywall bypass.

Deploy or update the renderer with `docker compose up -d --build renderer render-fetch broker` after regenerating compose using `prepare.py`. `Dockerfile.research` pins the Playwright image by digest and `config/browser-package-lock.json` pins the SDK. `config/browser-seccomp.json` derives from Playwright's v1.62.1 profile, with chroot allowed for Chromium's unprivileged user namespace while container capabilities stay empty. Do not replace this with --no-sandbox or a privileged container. The renderer exposes no host port. Doctor checks service health and its internal-only network; live rendering validation is also required after browser updates.

Try: `@KrishAdmin-HQ-LLM What is the latest Linus Tech Tips subscriber count? Use the official channel, include its rounded public count and timestamp, and link the source.` You do not need a special research prompt for ordinary factual questions.

References: [YouTube public subscriber-count semantics](https://developers.google.com/youtube/data/reference/rest/v3/channels#statistics.subscriberCount), [Playwright Docker sandbox guidance](https://playwright.dev/docs/docker), [upstream seccomp profile](https://github.com/microsoft/playwright/blob/v1.62.1/utils/docker/seccomp_profile.json).
