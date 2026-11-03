# 14. Owner-only GitHub workflow

The Discord owner (enrollment `owner_id`, currently `900000000000000004`) can inspect `KrishPAdmin/KrishAdmin-HQ` and `KrishPAdmin/KrishAdmin-HQ-Private`, review bounded text files and prepare code changes. The friend's lab access does not include GitHub reads or writes. This uses the gateway's existing GitHub CLI authentication; credentials are never given to a model or mounted into model containers.

## Use it

Mention the bot account in the main private channel:

```text
@KrishAdmin-HQ-LLM Show my connected GitHub repositories using hq_github.
@KrishAdmin-HQ-LLM List the files under LLM-Setup in KrishPAdmin/KrishAdmin-HQ-Private.
@KrishAdmin-HQ-LLM Read LLM-Setup/README.md in KrishPAdmin/KrishAdmin-HQ-Private and summarize it.
@KrishAdmin-HQ-LLM Read LLM-Setup/deployments/hermes/team.py in my private repo. Have Louis review it, then prepare a small proposed improvement. Show the diff and checks before publishing.
```

The returned proposal includes its ID, digest, base commit, changed files, diff and checks. To publish that exact proposal, send a new mention message containing the returned instruction:

```text
@KrishAdmin-HQ-LLM github push PROPOSAL_ID DIGEST_PREFIX
```

Use the actual values returned by the bot. The service independently reads that Discord message and requires the owner to supply this proposal-specific instruction. Text found in a repository, attachment or model response cannot grant approval. A general “push it” does not confirm an exact diff.

Publication creates a new `hq-bot/…` branch. The default branch is unchanged. Open the returned branch link and use GitHub's compare/pull-request UI when ready. Bot-side merging, force pushing, branch deletion and modifications to workflows are not implemented. The separate initial repository publication performed by the operator is not restricted to this bot branch workflow.

## Implemented limits

- Reads: two enrolled repositories, default-branch tree and regular UTF-8 files up to 100 KB. Slices are at most 12,000 characters and disclose unread content. Directory listings cap at 200 entries; use a narrower prefix.
- Changes: `LLM-Setup/` only, 1–8 files, at most 100 KB total and a 16,000-character review diff. Existing files need the blob SHA from a fresh read. No symlinks, submodules, deletions or credential/runtime paths.
- Checks: secret-material screening, exact known local credential screening, Python AST parsing and JSON parsing. Other text gets content checks only. No downloaded code, scripts, builds or unit tests execute. Repository CI may run after a pushed branch according to the repository's own settings.
- Public writes additionally reject private network addresses and the installation's hardware names. Use generic `amd-gpu` and `nvidia-gpu` descriptions.
- Proposals expire after 24 hours. A changed default-branch commit requires a fresh proposal. Partial Git-object creation is not publication; the new branch ref is created last. An ambiguous branch-create response is reconciled by its exact commit before retrying.

## Authorization and operation

`hq_github` reads the caller's real Hermes session, rejects non-owners before opening a socket and signs the request with a private origin key. `github_service.py` verifies the signature, timestamp, one-use nonce, enrolled channel and independently fetched Discord author/account mention. Requests use recent owner messages; claims such as “I am krishadmin” have no effect. Owner/friend conversation sessions are separated in both channels and threads. GitHub operations themselves are restricted to the enrolled main channel.

Responses are ordinary messages visible to members of that private channel. Owner-only command authorization is not private-message delivery. Do not request sensitive repository excerpts in a channel whose members should not see them.

The host service uses a private mode-0600 Unix socket. Only the concierge mounts that socket and the origin signing key. Specialist models have neither GitHub authentication nor this socket. GitHub CLI calls use fixed endpoints and structured stdin, with no model-controlled shell command. Repository allowlists and write scope are enforced by the service. Its existing CLI credential has broader account permissions than the tool exposes; this is application enforcement, not a separately issued least-privilege GitHub App token.

```bash
systemctl --user status hq-hermes-github.service
python3 hq.py doctor
python3 -m unittest test_github -v
```

Private durable proposals and replay records live in `state/github/operations.db`; metadata audit is `state/github/audit.jsonl`. Neither is published. Never delete a pending proposal just to retry an uncertain push. Repository reads and updates happen on HQ; AMD-GPU remains inference-only for model workflows.

The write implementation follows GitHub's [tree](https://docs.github.com/en/rest/git/trees), [commit](https://docs.github.com/en/rest/git/commits) and [reference](https://docs.github.com/en/rest/git/refs) APIs. The full project reference starts at [the guide index](index.md).
