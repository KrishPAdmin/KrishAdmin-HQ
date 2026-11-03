# 1. Quick start

## On the gateway VM

Open a terminal on **hq-gateway**, then:

```bash
cd /home/operator/krishadmin-hq/deployments/hermes
python3 hq.py status
python3 hq.py alerts
python3 hq.py doctor
```

`status` gives live API observations plus timestamped host/backup measurements. `alerts` applies fixed rules, without a model. `doctor` checks service state, timers, Discord heartbeat, internal network membership and credential file permissions. Its exit code is 0 when all implemented checks pass and 1 when attention is needed. A pass is not a full security or recovery audit.

## In Discord

Use **#krishadmin-hq-llm** in **Dev server**. Paste one of these as an ordinary message:

```text
<@900000000000000001> show current lab status
<@900000000000000001> show active warnings and recent changes
<@900000000000000001> submit a read-only health review to Paperclip
```

The mention must identify the bot account, not the similarly named role. `/status` is the Hermes gateway/session status; it is not the homelab measurements report.

## History and a report to keep

```bash
python3 hq.py history --limit 20
python3 hq.py report
python3 hq.py report --output /home/operator/lab-report.md
python3 hq.py guide --section troubleshooting
```

Report export creates a new mode-0600 file and refuses to overwrite an existing file. Choose a new filename for another report. Reports contain internal system measurements and addresses; review them before sharing.

## What needs your input next

1. Reset the Discord token that appeared in chat and install its replacement locally; see [Discord](discord.md).
2. Decide whether to enable the prepared 03:30 America/New_York nightly backups.
3. Identify a NAS/server, folder, and offline encryption-key custodian for off-host backups.
4. Arrange an isolated full application-recovery drill.


## Named specialists and uploads

Attach a supported document/code file with a bot mention and ask Louis to review it. Ask Jessica for major decisions, Harvey for plans, Mike for quick implementation, Rachel for source research, or Donna for coordination. See [capabilities](capabilities.md) for file limits and examples. `python3 hq.py team` lists the actual roster; `python3 hq.py compute` shows execution receipts.
