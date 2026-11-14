"""Fixed read-only entry point for the host diagnostic service."""
import json
import sys
from homelab import snapshot

if __name__ == '__main__':
    try:
        print(json.dumps(snapshot()))
    except Exception:
        sys.exit('Homelab collection failed; no successful check claimed')
