# KrishAdmin-HQ local network audit

This tool collects IPv4 network evidence on KrishAdmin-HQ and asks your dual-AMD-GPU Ollama model to interpret it over ZeroTier. It uses no OpenAI service, OpenAI token, or cloud inference. The local Ollama bearer token authenticates to your own GPU server and does not incur an API fee.

## Run

```bash
cd /home/operator/krishadmin-hq
./scripts/network/run-network-audit.sh --plan
./scripts/network/run-network-audit.sh
```

The approved scope is exactly `192.0.2.0/24`. The AMD-GPU address `198.51.100.202:11434` is an inference destination, not a scan target. Configuration is in `config/network-audit.json`; it contains only a reference to the existing local token file, not the token value.

A standard run discovers hosts, checks the configured TCP ports, samples ICMP latency/loss, inspects selected HTTP and TLS endpoints without login, records local routing/DNS/link/listener state, compares against the previous comparable run, and generates an evidence-linked AMD-GPU interpretation. Standard TCP scanning does not require sudo. Raw results and reports are stored privately under `reports/network/<timestamp>/`; `reports/network/latest/report.md` points to the most recent complete report.

## More coverage

```bash
# All 65535 TCP ports on discovered/known hosts; can take a long time
./scripts/network/run-network-audit.sh --profile full-tcp

# Include hosts that do not answer discovery probes
./scripts/network/run-network-audit.sh --scan-all-addresses

# Add light service-identification probes
./scripts/network/run-network-audit.sh --service-detection

# Add selected UDP checks; root privileges needed, reports will be root-owned
sudo ./scripts/network/run-network-audit.sh --udp

# Collect evidence without running the model
./scripts/network/run-network-audit.sh --no-ai

# Re-run analysis on existing evidence without repeating network probes
./scripts/network/run-network-audit.sh --analyze-existing reports/network/TIMESTAMP/evidence.json

# Limit a troubleshooting run to specific addresses within the approved VLAN
./scripts/network/run-network-audit.sh --targets 192.0.2.180 192.0.2.181
```

`--profile full-tcp --scan-all-addresses` combines all TCP ports and all addresses and may take hours. Scan and host timeouts limit execution; review warnings and XML before assuming complete coverage. Excluded addresses in config are not probed. The script rejects out-of-scope/public/IPv6 targets and concurrent audits. It uses argument lists rather than shell-interpolated commands. IPv6 assessment is not implemented.

## What this cannot prove

Unauthenticated network checks do not establish firmware patch state, firewall correctness, VLAN isolation, cluster quorum, backup recoverability, storage health, configuration quality or compromise. Devices may sleep or filter probes. An open port is not itself a vulnerability. UDP `open|filtered` is not confirmed open. A TLS failure by IP may be a private CA or hostname mismatch. Five pings are a short sample, not a long-term stability measurement.

No NSE vulnerability scripts, exploitation, password guessing, SNMP community guessing, network changes, restarts, or model-proposed shell execution are included. Selected HTTP checks use HEAD, never follow redirects, and send no credentials. The model never receives login credentials. Network banners and names are untrusted data; schema and evidence-ID validation reduce, but cannot eliminate, model mistakes.

## Reports

- `report.md`: inventory, findings, changes, model interpretation and limitations.
- `evidence.json`: normalized observations with stable within-run evidence IDs.
- `analysis.json`: model output, status and timing; analysis failures do not erase collected evidence.
- `raw/`: Nmap XML, command outcomes and before/after local snapshots.

Exit status 0 means collection/analysis completed without recorded command warnings, not that the network is secure. Exit 2 means partial collection or failed/partial analysis. Exit 1 means invalid configuration or another setup error. Reports can contain sensitive network inventory; they are not published on the public landing page. No unattended schedule or report deletion is installed.

For authenticated checks, first configure least-privilege credentials following `docs/credential-security.md`. Device-specific collectors are a next step; this audit does not automatically log into devices.

## n8n integration approach

Keep the network scanner outside n8n's generic code/command nodes. A dedicated execution service should expose a fixed `run_network_audit` action using this approved config, a single-job lock, job status, and a redacted report. n8n can schedule/request that action with a narrow service credential and then use the local AI router. Do not mount the Docker socket or grant arbitrary root shell execution to the model. This service has not been deployed yet; run the provided CLI now.

References: https://nmap.org/book/man-host-discovery.html ; https://nmap.org/book/man-port-scanning-techniques.html ; https://docs.ollama.com/api/chat

## Initial validated run

The standard baseline completed for 192.0.2.0/24 with 34 selected hosts, 102 confirmed open TCP ports and no collection-command warnings. All five local AMD-GPU interpretation batches passed response-shape and evidence-reference validation. Eight scope/parsing/baseline tests passed. This does not mean every address, TCP port or UDP service was tested; use the coverage options above for deeper scans. No authenticated device checks are configured yet.
