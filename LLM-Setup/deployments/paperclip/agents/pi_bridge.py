#!/usr/bin/env python3
"""Forward only the current run identity to the isolated Pi worker."""
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.request


def main():
    keys = ('PAPERCLIP_AGENT_ID', 'PAPERCLIP_COMPANY_ID', 'PAPERCLIP_RUN_ID', 'PAPERCLIP_API_KEY')
    payload = {k: os.environ[k] for k in keys}
    req = urllib.request.Request('http://pi-worker:8080/run', data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json',
                 'Authorization': 'Bearer ' + Path('/run/secrets/pi-bridge-token').read_text().strip()})
    try:
        with urllib.request.urlopen(req, timeout=440) as response:
            result = json.load(response)
        for summary in result.get('summaries', []):
            print(json.dumps(summary), flush=True)
        print(json.dumps({'event': 'pi_worker_finished', 'ok': bool(result.get('ok'))}), flush=True)
        return 0 if result.get('ok') else 1
    except urllib.error.HTTPError as error:
        print(json.dumps({'event': 'pi_worker_failed', 'http_status': error.code}), flush=True)
    except Exception:
        print(json.dumps({'event': 'pi_worker_failed', 'error': 'Private worker unavailable'}), flush=True)
    return 1

if __name__ == '__main__':
    sys.exit(main())
