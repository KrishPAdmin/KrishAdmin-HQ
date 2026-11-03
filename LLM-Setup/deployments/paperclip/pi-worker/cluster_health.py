#!/usr/bin/env python3
"""Read-only checks of the two configured GPU APIs; never prints credentials."""
from concurrent.futures import ThreadPoolExecutor
import datetime
import json
from pathlib import Path
import ssl
import time
import urllib.error
import urllib.request

TARGETS = {
    "amd-gpu": {"url": "http://198.51.100.202:11434", "token": "/run/secrets/amd-gpu-token"},
    "nvidia-gpu": {"url": "https://192.0.2.181:11434", "token": "/run/secrets/nvidia-gpu-token", "ca": "/run/secrets/nvidia-gpu-ca.crt"},
}


def inspect(name):
    cfg = TARGETS[name]
    result = {"system": name, "endpoint": cfg["url"], "checks": {}}
    try:
        token = Path(cfg["token"]).read_text().strip()
        context = ssl.create_default_context(cafile=cfg["ca"]) if cfg.get("ca") else None
    except (OSError, ssl.SSLError) as error:
        result["setup_error"] = type(error).__name__
        return result
    for label, path in (("available_models", "/api/tags"), ("loaded_models", "/api/ps")):
        started = time.monotonic()
        try:
            req = urllib.request.Request(cfg["url"] + path, headers={"Authorization": "Bearer " + token})
            with urllib.request.urlopen(req, context=context, timeout=8) as response:
                data = json.load(response)
                result["checks"][label] = {
                    "http_status": response.status,
                    "seconds": round(time.monotonic() - started, 3),
                    "models": [{key: model[key] for key in ("name", "size", "size_vram", "context_length") if key in model}
                               for model in data.get("models", [])],
                }
        except urllib.error.HTTPError as error:
            result["checks"][label] = {"http_status": error.code, "error": "API request rejected"}
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as error:
            result["checks"][label] = {"error": type(error).__name__}
    return result


def main():
    with ThreadPoolExecutor(max_workers=2) as pool:
        systems = list(pool.map(inspect, TARGETS))
    result = {
        "checked_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "scope": "Authenticated read-only Ollama API reachability and model residency",
        "limitations": "Does not establish GPU temperatures, ECC/driver health, host disk health, or inference quality. No host changes or generation requests performed.",
        "systems": systems,
    }
    print(json.dumps(result, indent=2))
    return 0 if all(all("error" not in value for value in system.get("checks", {}).values())
                    and len(system.get("checks", {})) == 2 for system in systems) else 1


if __name__ == "__main__":
    raise SystemExit(main())
