#!/usr/bin/env python3
"""
reverseProxy-create.py  (v3)

* Generates Service/Endpoints, optional ServersTransport,
  and IngressRoute manifests for each service in CSV_SERVICES.
* Correctly indents the `services:` list in 03-ingressroute.yaml
  so kubectl can parse it.

Output directory layout
-----------------------
/home/krishadmin/reverse-proxy/<service>/
    ├── 01-service-endpoints.yaml
    ├── 02-transport.yaml   (only for HTTPS back-ends)
    └── 03-ingressroute.yaml
"""

import csv
from pathlib import Path
import textwrap

# --------------------------------------------------------------------------- #
# 1.  Service list                                                            #
# --------------------------------------------------------------------------- #
CSV_SERVICES = """\
Name,Source,Protocol,IP,Port
#FILL IN THIS SECTION WITH YOUR REQUIRED PROXIES
"""

# --------------------------------------------------------------------------- #
# 2.  Globals                                                                 #
# --------------------------------------------------------------------------- #
BASE_DIR      = Path("/home/krishadmin/reverse-proxy")
NAMESPACE     = "external"
ENTRYPOINT    = "websecure"
CERT_RESOLVER = "cloudflare"

# --------------------------------------------------------------------------- #
# 3.  YAML helpers                                                            #
# --------------------------------------------------------------------------- #
def service_endpoints_yaml(name: str, proto: str, ip: str, tgt: str) -> str:
    return textwrap.dedent(f"""\
        # 1) Service & Endpoints
        apiVersion: v1
        kind: Service
        metadata:
          name: {name}
          namespace: {NAMESPACE}
        spec:
          clusterIP: None
          ports:
            - name: {proto}
              port: 80
              targetPort: {tgt}

        ---
        apiVersion: v1
        kind: Endpoints
        metadata:
          name: {name}
          namespace: {NAMESPACE}
        subsets:
          - addresses:
              - ip: {ip}
            ports:
              - port: {tgt}
                name: {proto}
        """).rstrip() + "\n"


def transport_yaml(name: str) -> str:
    return textwrap.dedent(f"""\
        # 2) Transport (skip self-signed cert)
        apiVersion: traefik.io/v1alpha1
        kind: ServersTransport
        metadata:
          name: {name}-transport
          namespace: {NAMESPACE}
        spec:
          insecureSkipVerify: true
        """).rstrip() + "\n"


def ingressroute_yaml(name: str, host: str, proto: str) -> str:
    # Build the list under `services:` first -------------------------------
    svc_lines = [
        f"- name: {name}",
        "  port: 80",
        f"  scheme: {proto}",
    ]
    if proto == "https":
        svc_lines.append(f"  serversTransport: {name}-transport")

    # Indent the whole list exactly 8 spaces (two levels) ------------------
    svc_block = textwrap.indent("\n".join(svc_lines), " " * 8)

    # Full IngressRoute ----------------------------------------------------
    return f"""# 3) IngressRoute (TLS termination + ACME)
apiVersion: traefik.io/v1alpha1
kind: IngressRoute
metadata:
  name: {name}
  namespace: {NAMESPACE}
spec:
  entryPoints:
    - {ENTRYPOINT}
  routes:
    - match: Host(`{host}`)
      kind: Rule
      services:
{svc_block}
  tls:
    certResolver: {CERT_RESOLVER}
""".rstrip() + "\n"


# --------------------------------------------------------------------------- #
# 4.  Main generator                                                          #
# --------------------------------------------------------------------------- #
def main() -> None:
    reader = csv.DictReader(CSV_SERVICES.strip().splitlines())
    for row in reader:
        name   = row["Name"].strip()
        host   = row["Source"].strip()
        proto  = row["Protocol"].strip().lower()
        ip     = row["IP"].strip()
        target = row["Port"].strip()

        outdir = BASE_DIR / name
        outdir.mkdir(parents=True, exist_ok=True)

        # 01-service-endpoints.yaml
        (outdir / "01-service-endpoints.yaml").write_text(
            service_endpoints_yaml(name, proto, ip, target)
        )

        # 02-transport.yaml (HTTPS only)
        if proto == "https":
            (outdir / "02-transport.yaml").write_text(
                transport_yaml(name)
            )

        # 03-ingressroute.yaml
        (outdir / "03-ingressroute.yaml").write_text(
            ingressroute_yaml(name, host, proto)
        )

        print(f"✓  Wrote manifests for {name}")


if __name__ == "__main__":
    main()
