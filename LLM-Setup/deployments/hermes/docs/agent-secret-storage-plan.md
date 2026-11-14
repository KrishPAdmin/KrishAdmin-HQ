# Credential storage for the Suits team

Status: deployed on HQ on 2026-11-13. The four selected credentials were migrated through private local processes; no values were printed or sent to a model. The owner confirmed the initial scope: homelab services and API tokens. Personal vault access and website logins are outside this scope.

## Original recommendation

Use a dedicated OpenBao secrets service on a separate trusted VM when available. Keep its encrypted storage under /var/lib/openbao and configuration under /etc/openbao on that VM. Neither belongs under .codex, an agent workspace, a source repository, or a general file-tool mount. A service on HQ is a simpler alternative but shares HQ's administrator-compromise boundary.

For integrations already supported by Paperclip, its existing encrypted secret store is a useful immediate option. Its control-center Proxmox connector resolves a secret reference internally and returns observations. It is not currently a universal password broker for all Hermes tools. A new OpenBao integration still requires connector work; installing a vault alone will not connect the agents.

## Observed current state

- Some existing credentials are already outside Codex under the HQ deployment tree. The inspected secrets directory has mode 0700, and the AMD-GPU password file has mode 0600. File permissions alone do not encrypt those values.
- Paperclip has a local encrypted secret provider. Its server can access its decryption key; it shares that server's trust boundary.
- The existing Proxmox connector checks permitted agents before resolving a credential and making fixed requests.
- The existing AMD-GPU collector receives its password locally and sends bounded observations to the models. Preserve password authentication as currently selected by the owner.
- Existing backup documentation states that archives contain credential copies. Migration must account for those copies.
- No OpenBao/Vault/Bitwarden/1Password/Infisical CLI was found, nor an obvious dedicated vault container. No TPM device was visible on HQ. This is not an inventory of every machine on the network.

## How agents would use credentials

1. An agent requests an operation, such as reading a service's health, through a connector.
2. The connector authenticates the actual runtime/task identity and checks the allowed service, destination and operation. A persona name supplied by a model is not authentication.
3. A dedicated connector identity obtains only that service's credential from OpenBao over verified TLS.
4. The connector authenticates to the target service and returns bounded, credential-free results.
5. Record the requesting agent/task, operation, target, time and result. Enable vault auditing without raw secret logging.

Do not expose a general get_password tool. Do not mount the vault or its administrator token into Benjamin's coding workspace. For builds needing authenticated APIs, prefer a dedicated proxy/connector outside generated code; if a process must receive a credential, use a narrowly scoped, short-lived credential and recognize that process can read it. Redaction alone does not make arbitrary credential-bearing code safe.

## Proposed access policy

| Team role | Default access |
|---|---|
| Jessica, Harvey, Louis | Sanitized evidence and review; no general secret retrieval |
| Donna | Invoke explicitly authorized connectors and coordinate results |
| Rachel | Public research; authenticated source access only if explicitly configured |
| Mike and Benjamin | Project-scoped development/test integrations; no shared production administrator password |
| Human operator | Vault administration, enrollment, revocation and recovery |

Use per-connector identities and separate development/production permissions. Preserve verified requesting-agent identity through shared orchestration. Use API tokens or service accounts instead of personal administrator passwords where supported. Keep existing password-only integrations working through fixed connectors.

## Storage, recovery and availability

Configure encrypted persistent storage, verified TLS, restrictive OS access, disabled process swap or encrypted swap, and no access from ordinary model containers. Choose an unlock method explicitly: operator unsealing after restart, or auto-unsealing through a separately protected KMS/HSM. Do not keep all unseal material next to the vault data or in the agent's files. An unattended connector still needs a protected bootstrap identity; a vault does not remove this requirement.

Maintain encrypted backups and separately held recovery material. Test a restore before retiring the previous storage. A single vault VM creates an availability dependency: when it is sealed or unavailable, protected operations should fail clearly, without falling back to plaintext credentials or broad administrator access.

No vault protects secrets already released to a compromised client, nor guarantees protection against an administrator able to inspect its running process memory. A separate VM reduces shared exposure but does not eliminate hypervisor or privileged administration risk.

## Migration and acceptance

1. Select the first service and confirm which agents and actions need access.
2. Provision the vault and recovery method; use a dummy credential first.
3. Implement a narrow connector and test allowed/denied identities, destination restrictions, expired access, and unavailable vault behavior.
4. Confirm dummy values never appear in prompts, logs, artifacts, shell history or the coding workspace.
5. Enroll the real credential through a private administrative interface, not chat or a command-line argument.
6. Verify the existing authenticated operation through the new connector, with a rollback path.
7. Migrate other integrations individually. Remove obsolete plaintext copies after validation, review historical backups, and rotate affected credentials where appropriate. Retain recoverability deliberately.

## Primary references

- OpenBao security model: https://github.com/openbao/openbao/blob/main/website/content/docs/internals/security.mdx
- OpenBao policies: https://openbao.org/docs/concepts/policies/
- OpenBao audit logging: https://openbao.org/docs/audit/
- OpenBao persistent storage: https://openbao.org/docs/configuration/storage/raft/
- OpenBao seal configuration: https://openbao.org/docs/configuration/seal/
- OpenBao installation hardening: https://openbao.org/docs/install/
- Bitwarden Secrets Manager is an alternative with machine-account access: https://bitwarden.com/help/secrets-manager-overview/ and https://bitwarden.com/help/machine-accounts/


## Deployed result

OpenBao 2.7.2 runs under its own hq-vault Unix account, with encrypted Raft data in /var/lib/openbao and TLS on loopback only. The release SHA-256 and upstream GPG signature were verified. Audit logging is enabled; raw secret logging is not. The vault service has process swap disabled and no core dumps.

The owner selected unattended startup using protected local credentials. Recovery and AppRole bootstrap identities are stored encrypted under /etc/credstore.encrypted/hq-vault-*, using systemd's host credential key. No TPM is visible on HQ. The host key is on unencrypted media: this protects against copying the credential files alone, not full-disk theft or HQ administrator compromise. This is a same-host deployment, not a separate security VM.

Migrated entries: pi-cluster, amd-gpu-ssh, nvidia-gpu-api and amd-gpu-api. The old .codex/secrets/.passwords file and the three selected plaintext HQ credential files were removed after live login tests and an isolated snapshot restore. Existing historical backups may retain earlier copies; those archives were not erased. Other application/OAuth credentials were not part of this four-entry migration.

The host-only connector socket accepts only pi-cluster and amd-gpu-ssh from the trusted host account. It is not mounted into agent containers. Its vault role cannot retrieve GPU API tokens. A separate runtime role loads only GPU API tokens into volatile /run/hq-vault-runtime files for the existing fixed Docker mounts. Models receive observations rather than passwords. The existing host account has sudo and remains a trust boundary; these controls do not isolate a malicious process running as that account.

Vault restart automatically unlocks and refreshes volatile credentials; this was tested with a service restart. Full host reboot was not performed. At boot, mount placeholders are prepared before Docker; if unlocking fails, authenticated operations fail rather than using the deleted plaintext source files. The unlock unit retries on failure.

Daily encrypted vault snapshots run at approximately 04:15 America/New_York under hq-vault-backup.timer, without stopping applications. They are stored root-only under /var/backups/hq-vault. No off-host destination is configured and automatic retention pruning is not enabled. Paperclip's backup now includes a separate encrypted vault snapshot and omits the migrated plaintext GPU tokens and AMD-GPU password. Other preexisting application backup contents still include secrets and require private handling.

The operator command is /usr/local/sbin/hq-vault. It supports status, list (names only), put (hidden password prompt), unlock, and snapshot. It deliberately has no plaintext get command. Adding a vault entry does not grant agent access automatically: add a fixed connector and a narrowly scoped policy for the desired operation.

Examples:

    sudo hq-vault status
    sudo hq-vault list
    sudo hq-vault put my-service
    sudo systemctl restart hq-vault-unlock.service
    sudo hq-vault snapshot --output /path/to/new-encrypted.snap

Recovery requires an encrypted snapshot plus independently preserved recovery material. The encrypted unseal credential cannot be decrypted on a replacement host without the original systemd host key. Export a recovery share through a private operator procedure to offline storage; never put it in chat, source control or an agent workspace. Snapshot restore was tested in an isolated temporary instance, all four values were compared in memory, and the temporary instance/data were removed.

Verification: live SSH to all three Pi hosts and AMD-GPU; authenticated Uptime Kuma query returning 27 monitors; GPU API reads through the updated Paperclip container mounts; denied cross-role secret access; encrypted snapshot restore; unattended vault service restart. No remote password rotation was performed.
