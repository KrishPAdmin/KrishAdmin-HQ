#!/usr/bin/env python3
"""
reverseProxy-run.py
Apply the generated Traefik manifests for a single service in order.

Usage
=====
    python3 reverseProxy-run.py <service-folder-name>

The script expects your manifests to live under:
    /home/krishadmin/reverse-proxy/<service-folder-name>/

It looks for *.yaml files, sorts them lexicographically (so 01-…, 02-…, 03-…),
and runs:  kubectl apply -f <file>   for each one.

If any step fails, the script aborts with the same exit-code as kubectl.
"""

import os
import sys
import subprocess
from pathlib import Path

BASE_DIR = Path("/home/krishadmin/reverse-proxy")

def die(msg: str, code: int = 1) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)

def main() -> None:
    # ----------------------------------------------------------------------
    # 1. Argument parsing
    # ----------------------------------------------------------------------
    if len(sys.argv) != 2:
        die("Usage: python3 reverseProxy-run.py <service-folder-name>")

    service = sys.argv[1].rstrip("/ ")
    target_dir = BASE_DIR / service

    if not target_dir.is_dir():
        die(f"{target_dir} does not exist or is not a directory")

    # ----------------------------------------------------------------------
    # 2. Locate YAML files in numeric order
    # ----------------------------------------------------------------------
    yaml_files = sorted(
        [f for f in target_dir.iterdir()
         if f.suffix in (".yml", ".yaml")],
        key=lambda p: p.name
    )

    if not yaml_files:
        die(f"No *.yaml files found in {target_dir}")

    # ----------------------------------------------------------------------
    # 3. Apply each manifest
    # ----------------------------------------------------------------------
    print(f"Applying manifests for {service} …\n")
    for f in yaml_files:
        print(f"→ kubectl apply -f {f}")
        result = subprocess.run(["kubectl", "apply", "-f", str(f)])
        if result.returncode != 0:
            die(f"kubectl failed on {f.name}", result.returncode)

    print("\n✅  All manifests applied successfully.")

if __name__ == "__main__":
    main()
