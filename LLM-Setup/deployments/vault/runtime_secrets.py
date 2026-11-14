"""Materialize only GPU service tokens into volatile host storage for fixed mounts."""
import os
from pathlib import Path
from vault_common import api,login,read_secret
DEST=Path('/run/hq-vault-runtime')
def hydrate():
    os.umask(0o077);DEST.mkdir(mode=0o711,exist_ok=True);os.chmod(DEST,0o711)
    token=login('runtime')
    try:values={name:read_secret(name,token) for name in ['nvidia-gpu-api','amd-gpu-api']}
    finally:api('auth/token/revoke-self',{},token)
    for name,value in values.items():
        p=DEST/name
        # Preserve inode for existing read-only file bind mounts on rotation.
        with p.open('w') as f:f.write(value+'\n')
        os.chown(p,1000,1000);os.chmod(p,0o400)
    return len(values)
def prepare():
    DEST.mkdir(mode=0o711,exist_ok=True);os.chmod(DEST,0o711)
    for name in ['nvidia-gpu-api','amd-gpu-api']:
        p=DEST/name
        if not p.exists():p.touch(mode=0o400)
        os.chown(p,1000,1000);os.chmod(p,0o400)
if __name__=='__main__':
    import sys
    if '--prepare' in sys.argv:prepare()
    else:print('GPU runtime credentials loaded:',hydrate())
