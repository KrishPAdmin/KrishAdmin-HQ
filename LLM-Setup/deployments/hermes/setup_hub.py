#!/usr/bin/env python3
"""One-time same-filesystem relocation. Quiesce writers before applying."""
import datetime
import json
import os
from pathlib import Path
from hub_store import HUB, AGENTS, AREAS

ROOT = Path(__file__).resolve().parent

def main():
    os.umask(0o077)
    HUB.mkdir(mode=0o700, exist_ok=True)
    for name in AGENTS:
        for area in (*AREAS, 'runtime'):
            (HUB / 'agents' / name / area).mkdir(parents=True, exist_ok=True, mode=0o700)
    for folder in ('skills','shared','projects','runtime','backups'):
        (HUB / folder).mkdir(exist_ok=True, mode=0o700)
    mappings = [
        (ROOT/'profiles/concierge/skills', HUB/'skills/hermes'),
        (ROOT/'profiles/concierge/cache/documents', HUB/'shared/uploads'),
        (Path.home()/'.codex/skills/hq-operations', HUB/'skills/operator/hq-operations'),
        (ROOT/'profiles/concierge', HUB/'agents/donna/runtime/concierge'),
        (ROOT/'state', HUB/'runtime/hermes/state'),
        (ROOT/'observations', HUB/'runtime/hermes/observations'),
        (ROOT.parent/'paperclip/data', HUB/'runtime/paperclip'),
        (ROOT.parent/'paperclip/worker-workspaces', HUB/'agents/benjamin/workspace'),
        (ROOT.parent/'paperclip/operations/snapshots', HUB/'runtime/paperclip-observations'),
    ]
    mappings += [(ROOT/'profiles'/name, HUB/'agents'/name/'runtime/hermes') for name in AGENTS if name != 'benjamin']
    mappings += [(ROOT/'profiles'/name, HUB/'runtime/hermes/profiles'/name) for name in ('health','backup','triage','analyst')]
    results = []
    for source, destination in mappings:
        if source.is_symlink():
            if source.resolve() != destination.resolve():raise RuntimeError('Unexpected existing compatibility link')
        else:
            if not source.is_dir():raise RuntimeError('Required source directory missing')
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            if destination.exists():destination.rmdir()  # Only an empty prepared directory is accepted.
            source.rename(destination)
            source.symlink_to(destination, target_is_directory=True)
        results.append({'previous_path': str(source), 'canonical_path': str(destination)})
    stamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    (HUB/'migration.json').write_text(json.dumps({'migrated_at': stamp, 'mappings': results, 'method': 'Same-filesystem rename; original paths retained as compatibility symlinks'}, indent=2)+'\n')
    if not (HUB/'README.md').exists():(HUB/'README.md').write_text((ROOT/'docs/llm-hub.md').read_text())
    if not (HUB/'hub').exists():
        (HUB/'hub').write_text('#!/usr/bin/env python3\nimport runpy,sys\nsys.path.insert(0,'+repr(str(ROOT))+')\nrunpy.run_module("hub",run_name="__main__")\n')
        (HUB/'hub').chmod(0o700)
    for name in AGENTS:
        guide=HUB/'agents'/name/'README.md'
        if not guide.exists():guide.write_text('# '+name.title()+'\n\nDrop files in inbox; work in workspace; collect reports from deliverables. Archive completed work manually. Skills are reference instructions; runtime is managed. Dropped files never execute automatically. Keep passwords in the vault.\n')
    print('Moved '+str(len(results))+' storage/skill directories into '+str(HUB))

if __name__ == '__main__':main()
