# 9. Recovery, rollback and updates

## Recovery principles

Use an isolated recovery environment first. Never run two gateways with the production Discord token. Keep restored schedulers and application workflows disabled until validation. Do not use `docker compose down -v` as a troubleshooting shortcut; it removes data volumes.

## Recover the Hermes deployment

1. Choose a private archive under `backups/` and compare its hash with the corresponding saved validation receipt. If the receipt is unavailable, do not claim the archive is verified.
2. Extract into a separate protected directory using safe tar extraction. Check the image/revision in `release.json`, configuration, file permissions and all external mount paths.
3. Restore external prerequisites separately: Paperclip, its broker network, observation keys/target configuration, GPU API credentials and trusted NVIDIA-GPU certificate. The Hermes archive is not a backup of the entire HQ VM.
4. Keep Discord disabled and schedules stopped. Check restored SQLite databases and configuration before starting the broker/workers in an isolated Compose project with nonconflicting names/ports.
5. Run status and diagnostic checks against the recovery environment. Do not let a recovery test submit tasks into production Paperclip.
6. During an approved cutover, stop the old gateway before enabling its replacement token/session. Verify `/status`, a normal bot mention, and both inference paths.
7. Reinstall the root-owned sanitized backup exporter and system timer, then the user observation/monitor units. Verify each timer and source timestamp.

`backup.py` currently checks isolated extraction, credential roundtrip and SQLite integrity. It does not perform steps 3–7 automatically. Full restored-service and VM boot testing remain outstanding.

## Recover Paperclip or n8n

Use their deployment-specific archives and PostgreSQL versions. Restore into new isolated storage. Preserve the required original encryption/configuration keys so credentials can be decrypted. Keep outbound workflow execution disabled. Validate database tables, login, credential decryption, attachments/files and a harmless workflow before cutover.

`verify_database_backup.py` performs the database portion in a networkless temporary container. It is designed to avoid production mutation; it is not a production restore command.

## Update procedure

1. Record the current `release.json`, active services and `hq.py doctor` output.
2. Create and validate a private backup in an approved interruption window.
3. Test the new pinned release separately. Check profile/config compatibility and the nine-tool allowlist. Keep AMD-GPU tool restrictions and Discord channel/user restrictions intact.
4. Run the policy, enrollment, observation and monitoring tests, plus native status/alert tool-loop checks.
5. Deploy during an approved window and verify both service health and a normal Discord reply.
6. If rollback is needed, use the matching prior code, image, configuration and database snapshot. Do not assume a newer database schema can be safely used with an older runtime.

No automatic upstream updater or package-upgrade schedule was added.

## Preserve state and evidence

- Hermes: `access/`, `config/`, `state/`, `profiles/`, `plugin/`, `docs/`, `systemd/`, deployment code and Compose file.
- HQ user units: `~/.config/systemd/user/` entries for observations, evidence and monitor. Hermes archives its evidence/monitor units under `systemd-user/`; Paperclip archives its observation units.
- Root exporter: `/usr/local/libexec/hq-backup-observer.py`, `/etc/systemd/system/hq-backup-observations.*`.
- Paperclip observer identities/configuration: `../paperclip/operations/` and relevant HQ SSH trust files.
- External secrets: the credential references in [security](security.md).

The observation/history files can be regenerated. Task deduplication state, credential identities and application databases must be preserved for a faithful recovery.


See [the named team and expanded capabilities](capabilities.md) for model assignments, uploaded files, code/config review, draft artifacts, exact arithmetic, local knowledge and specialist task submission.
