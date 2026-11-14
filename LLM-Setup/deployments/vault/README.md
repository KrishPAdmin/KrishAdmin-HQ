# HQ credential vault

Deployed OpenBao 2.7.2. Operator guide: ../hermes/docs/agent-secret-storage-plan.md.

Source files contain no credentials. Installed root-owned runtime: /usr/local/lib/hq-vault. CLI: /usr/local/sbin/hq-vault. TLS/config: /etc/openbao. Encrypted database: /var/lib/openbao. Encrypted bootstrap credentials: /etc/credstore.encrypted/hq-vault-*.

initialize.py is one-time enrollment code, not a recovery command; its original migration input files have been removed. Do not rerun it against the initialized vault. install-host.sh provisions the initial service; preserve the separately installed unlock/connector/runtime/backup units when rebuilding. The deployed units are copied into systemd/ for disaster-recovery configuration and use the operator guide; the scripts alone do not replace independent key custody.

The selected unattended host-key mode trusts the HQ administrator. Snapshot restore and vault service restart passed. Full host reboot and off-host recovery storage have not been tested/configured.

Private enrollment: `sudo hq-vault enroll SERVICE-NAME`. Safe catalog: `sudo hq-vault catalog`. See ../hermes/docs/benjamin-server-operations.md. Install enrollment.py alongside vault_common.py. The connector now requires systemd socket activation via hq-vault-connector.socket; retain both the socket and service units. No secret values should be committed to either repository.
