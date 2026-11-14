"""Imported by trusted host connectors, never mounted into model workspaces."""
import json,socket
def credential(name):
    if name not in {'pi-cluster','amd-gpu-ssh'}:raise PermissionError('Credential outside connector scope')
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(20);sock.connect('/run/hq-vault/connector.sock')
            sock.sendall(json.dumps({'name':name}).encode()+b'\n')
            with sock.makefile('rb') as f:result=json.loads(f.readline(16385))
        if not isinstance(result.get('value'),str) or not result['value']:raise ValueError()
        return result['value']
    except (OSError,ValueError):raise RuntimeError('HQ vault credential unavailable; check vault unlock and connector status') from None
