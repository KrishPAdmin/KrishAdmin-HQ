#!/usr/bin/env python3
"""Private work-file snapshots; application databases use their existing backups."""
import datetime
import hashlib
import json
import os
import tarfile
import tempfile
from pathlib import Path
from hub_store import HUB, AGENTS, AREAS

def main():
    os.umask(0o077)
    folder = HUB/'backups'; folder.mkdir(exist_ok=True)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    destination = folder/('agent-files-'+stamp+'.tar.gz')
    roots = [HUB/'agents'/name/area for name in AGENTS for area in AREAS]
    roots += [HUB/'agents'/name/'README.md' for name in AGENTS]
    roots += [HUB/'skills', HUB/'shared', HUB/'projects', HUB/'README.md', HUB/'migration.json', HUB/'hub']
    count = 0
    with tarfile.open(destination, 'w:gz') as archive:
        for root in roots:
            candidates = [root] if root.is_file() else root.rglob('*')
            for path in candidates:
                if path.is_symlink() or not path.is_file() or any(p in ('__pycache__','.git','node_modules','.venv') for p in path.relative_to(HUB).parts):continue
                before = path.stat()
                if before.st_nlink != 1:continue
                archive.add(path, arcname=str(path.relative_to(HUB)), recursive=False)
                after = path.stat()
                if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):
                    raise RuntimeError('File changed during snapshot; partial archive retained for diagnosis')
                count += 1
    # Verify archive bytes by extraction; do not run any restored code.
    with tempfile.TemporaryDirectory(prefix='hq-hub-restore-') as temporary:
        with tarfile.open(destination) as archive:archive.extractall(temporary, filter='data')
        assert sum(p.is_file() for p in Path(temporary).rglob('*')) == count
    receipt = {'archive': destination.name, 'files': count, 'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
               'extraction_check': 'passed', 'scope': 'Agent inbox/workspace/deliverables/archive/skills, shared files and projects. Runtime databases, credentials and vault backups remain separate. Local disk only; no off-host durability claimed.'}
    destination.with_suffix('.receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))

if __name__ == '__main__':main()
