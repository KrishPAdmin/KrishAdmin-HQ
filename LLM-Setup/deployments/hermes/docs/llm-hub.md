# KrishAdmin LLM Hub

This is the central home for Suits agent files, custom skills and relocated agent runtime storage.

```
agents/
  jessica/   harvey/   louis/   mike/   rachel/   donna/   benjamin/
    inbox/         Drop files here for this person.
    workspace/     Working files and disposable-container Python checks.
    deliverables/  Saved reviews, artifacts and execution receipts.
    archive/       Completed material you choose to retain.
    skills/        Your agent-specific reference instructions.
    runtime/       Managed private profiles; not a drop-off folder.
skills/
  hermes/          Existing Hermes skills, including the HQ custom skills.
  operator/        Custom HQ operator skill, with the original path linked here.
shared/uploads/    Existing Discord uploads and drafts.
projects/          Shared project documents you organize manually.
runtime/           Relocated Hermes state and Paperclip files/artifacts.
backups/           Private local snapshots and verification receipts.
```

## Drop-off and review

Put a document in `agents/louis/inbox/example.py`, then tell Donna in your owner DM:

> Have Louis review `inbox/example.py` from his Hub folder and save his findings.

The owner-only `hq_hub` tool lists, reads, reviews and creates working files. It supports text/code/config, text PDFs, DOCX and XLSX up to 5 MiB. Read/review returns bounded slices; follow `next_offset` for more content. Scripts and document macros do not execute during review. Inbox originals are not overwritten. The six specialists receive requested file evidence through HQ; they do not gain arbitrary host shell access. Benjamin can read named files from his inbox during tracked coding/server tasks. Merely dropping a file does not schedule work.

From an HQ terminal:

```bash
./hub list --agent louis
./hub read --agent louis --path inbox/example.py
./hub review --agent louis --path inbox/example.py --question 'Find concrete bugs and save a review.'
./hub sandbox --agent louis --path workspace/check.py
```

Use the full `/home/operator/KrishAdmin-LLM-Hub/hub` path when outside this directory. Engineering checks currently run Python in a pinned disposable container. Only that agent's workspace is mounted, with no network, credentials, Docker socket or other agent folders. CPU, memory, process count, output, per-file size and runtime are limited. Workspace changes persist. This is container isolation, not a separate virtual machine or a total disk quota. Arbitrary package installation and remote deployment are not enabled by this route.

Each named specialist response is saved in its `deliverables` folder. Benjamin's published artifacts are also mirrored there in task/run folders; full working projects remain under his `workspace`. Existing scheduled background jobs keep their current runners.

## Skills, storage and backup

Existing profiles, workspaces and custom skills were moved, not discarded. `migration.json` lists the canonical paths and compatibility links. New writes through the old paths land here. Platform-managed Codex/plugin skill caches remain managed by their applications; the custom HQ operator skill lives under this Hub.

A daily local file snapshot runs at approximately 04:35 local time and validates extraction. It includes agent working areas, shared files, skills and projects. It excludes managed runtime databases and vault data, which retain their separate backup processes. No automatic deletion/retention policy is configured. Local snapshots protect against accidental changes but not loss of the HQ disk; they are not an off-host backup.

The PostgreSQL Docker volume, OpenBao database, unlock material and protected external account authentication remain in their existing protected system storage. This folder organization does not weaken vault permissions. Use `sudo hq-vault enroll SERVICE-NAME` for credentials, never agent inboxes. Hub files, conversations and runtime contents are never automatically published to GitHub; only reviewed source/setup documentation goes into the source backup.
