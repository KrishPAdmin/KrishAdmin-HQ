#!/usr/bin/env python3
"""Operator-terminal enrollment: passwords stay in SSH/sudo, never in Python."""
import base64,json,subprocess,sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OPS=ROOT.parent/'paperclip/operations'
HOST='198.51.100.202'

def main():
    if not sys.stdin.isatty():raise SystemExit('Run this interactively in your gateway VM terminal.')
    installer=(OPS/'install-observer.sh').read_bytes()
    encoded=base64.b64encode(installer).decode('ascii')
    print('Connecting to AMD-GPU as krishadmin. Enter its SSH password and sudo password locally if prompted.')
    print('Installs a fixed local host probe and a source-restricted, forced-command observer key. No browsing or outbound network requests are performed on AMD-GPU.')
    command="set -eu; umask 077; observer_tmp=$(mktemp); trap 'rm -f \"$observer_tmp\"' EXIT; printf '%s' '"+encoded+"' | base64 -d > \"$observer_tmp\"; sudo /bin/sh \"$observer_tmp\""
    subprocess.run(['ssh','-t','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=10',
        '-o','IdentitiesOnly=yes','-i',str(Path.home()/'.ssh/krishadmin-hq-amd-gpu'),
        'krishadmin@'+HOST,command],check=True)
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','IdentitiesOnly=yes',
        '-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=5','-i',str(OPS/'keys/observer'),
        'paperclip-observer@'+HOST,'probe'],capture_output=True,text=True,timeout=30)
    if result.returncode:raise SystemExit('Observer check failed. Existing target configuration has not changed. Check the source-IP restriction and SSH access.')
    data=json.loads(result.stdout)
    if not all(k in data for k in ('hostname','memory','root_disk')):raise SystemExit('Unexpected probe response; target configuration unchanged.')
    path=OPS/'targets.json';config=json.loads(path.read_text())
    config['amd-gpu']={'host':HOST,'user':'paperclip-observer','key':str(OPS/'keys/observer')}
    temporary=path.with_suffix('.json.new');temporary.write_text(json.dumps(config,indent=2)+'\n');temporary.replace(path)
    subprocess.run(['systemctl','--user','start','hq-hermes-evidence.service'],check=True)
    print('AMD-GPU read-only host observation verified and enabled. No model tools were enabled on AMD-GPU.')

if __name__=='__main__':main()
