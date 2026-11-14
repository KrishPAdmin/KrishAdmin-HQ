#!/usr/bin/env python3
"""Benjamin's fixed HQ operations client. Never returns vault secret values."""
import argparse
import json
from pathlib import Path
import urllib.request

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['catalog', 'status', 'diagnostics', 'homelab'])
    parser.add_argument('--target', choices=['hq', 'nvidia-gpu', 'amd-gpu'])
    parser.add_argument('--check', choices=['overview', 'gpu', 'processes', 'services', 'storage'], default='overview')
    args = parser.parse_args()
    body = {'action': args.action}
    if args.action == 'diagnostics':
        if not args.target:
            parser.error('--target is required')
        body.update(target=args.target, check=args.check)
    token = Path('/run/secrets/benjamin-ops').read_text().strip()
    request = urllib.request.Request('http://hq-hermes-broker:8080/server-ops',
        data=json.dumps(body).encode(), headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
    # No redirects: this identity must never be forwarded to another endpoint.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            raise RuntimeError('Redirect refused')
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with client.open(request, timeout=110) as response:
        raw = response.read(2000001)
    if len(raw) > 2000000:
        raise RuntimeError('Output exceeded limit')
    print(json.dumps(json.loads(raw), indent=2))

if __name__ == '__main__':
    try:
        main()
    except Exception:
        raise SystemExit('Server operation failed; no successful action is claimed. Check HQ connector availability.')
