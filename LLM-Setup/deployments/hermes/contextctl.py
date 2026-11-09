#!/usr/bin/env python3
"""Operator CLI for context windows: preview, validated apply, snapshots and rollback."""
import argparse,datetime,fcntl,json,os,re,shlex,subprocess,sys,tempfile,uuid
from pathlib import Path
import yaml
import context_settings as settings
from hq_client import ROOT,call

def atomic(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:f.write(data);f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def encoded(value):return (json.dumps(value,indent=2)+'\n').encode()

def planned_files(candidate,root=ROOT):
    files={root/'config/context-windows.json':encoded(candidate),root.parent/'paperclip/data/hq-hermes/context-windows.json':encoded(candidate)}
    for name in ('concierge','health','backup','triage','analyst'):
        path=root/'profiles'/name/'config.yaml'
        if not path.exists():continue
        config=yaml.safe_load(path.read_text());config['model']['context_length']=settings.window(name,candidate)
        if name=='concierge':
            config['compression']=settings.compression(candidate)
            config['auxiliary']['compression']['context_length']=settings.window('jessica',candidate)
        files[path]=encoded(config)
    for name in ('jessica','harvey','mike','louis','rachel','donna'):
        path=root/'profiles'/name/'role.json'
        if path.exists():
            role=json.loads(path.read_text());role['context_length']=settings.window(name,candidate);files[path]=encoded(role)
    path=root.parent/'paperclip/pi-worker/models.json'
    if path.exists():
        config=json.loads(path.read_text())
        for provider in config.get('providers',{}).values():
            for model in provider.get('models',[]):
                if model.get('id')=='paperclip-qwen3.5:9b':model['contextWindow']=settings.window('pi',candidate)
        files[path]=encoded(config)
    return files

def apply_pi(tokens):
    # Management stays on the operator SSH path; the inference proxy remains read-only.
    if type(tokens) is not int or tokens%1024 or not 4096<=tokens<=262144:raise ValueError('Invalid Pi context')
    script='context_file=$(mktemp /tmp/hq-context.XXXXXX); trap \'rm -f "$context_file"\' EXIT; cat > "$context_file"; ollama create paperclip-qwen3.5:9b -f "$context_file"'
    command=['ssh','-i',str(Path.home()/'.ssh/krishadmin-hq-nvidia-gpu'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes',
             '-o','IdentitiesOnly=yes','-o','ConnectTimeout=5','krishadmin@192.0.2.181',
             'docker exec -i homelab-fast-ollama sh -c '+shlex.quote(script)]
    result=subprocess.run(command,input='FROM paperclip-qwen3.5:9b\nPARAMETER num_ctx '+str(tokens)+'\n',text=True,capture_output=True,timeout=180)
    if result.returncode:raise RuntimeError('Fixed Pi model-alias update failed; inspect operator SSH access and model state locally')

def commit(candidate,current,root=ROOT,restart=True):
    files=planned_files(candidate,root);before={p:p.read_bytes() if p.exists() else None for p in files}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8]
    backup=root/'backups/context-settings'/stamp;backup.mkdir(parents=True,mode=0o700)
    atomic(backup/'context-windows.json',encoded(current))
    # Profile snapshots stay private; rollback restores settings into current profiles.
    for number,(path,data) in enumerate(before.items()):
        if data is not None:atomic(backup/(str(number)+'-'+path.name),data)
    pi_changed=candidate['contexts']['pi']!=current['contexts']['pi']
    try:
        if pi_changed:apply_pi(candidate['contexts']['pi'])
        for path,data in files.items():atomic(path,data)
        if pi_changed:
            subprocess.run(['docker','compose','-f',str(root.parent/'paperclip/compose.yaml'),'up','-d','--force-recreate','pi-worker'],check=True,timeout=90)
        if restart and any(candidate['contexts'][name]!=current['contexts'][name] for name in ('concierge','jessica')):
            subprocess.run([sys.executable,str(root/'restart_gateway.py')],check=True,timeout=90)
    except Exception:
        for path,data in before.items():
            if data is None:path.unlink(missing_ok=True)
            else:atomic(path,data)
        if pi_changed:
            try:apply_pi(current['contexts']['pi'])
            except Exception:print('Pi alias rollback could not be confirmed. Reconcile before further changes.',file=sys.stderr)
            try:subprocess.run(['docker','compose','-f',str(root.parent/'paperclip/compose.yaml'),'up','-d','--force-recreate','pi-worker'],check=True,timeout=90)
            except Exception:print('Pi worker rollback restart could not be confirmed.',file=sys.stderr)
        if restart and any(candidate['contexts'][name]!=current['contexts'][name] for name in ('concierge','jessica')):
            try:subprocess.run([sys.executable,str(root/'restart_gateway.py')],check=True,timeout=90)
            except Exception:print('Gateway rollback restart could not be confirmed; run the local doctor.',file=sys.stderr)
        raise
    return stamp

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='action',required=True)
    show=sub.add_parser('show');show.add_argument('--json',action='store_true')
    for action in ('set','reset'):
        p=sub.add_parser(action);p.add_argument('target',choices=[*settings.DEFAULTS,*(['all'] if action=='reset' else [])])
        if action=='set':p.add_argument('tokens',type=int);p.add_argument('--experimental',action='store_true')
        p.add_argument('--apply',action='store_true',help='Apply the displayed setting; otherwise preview only')
    p=sub.add_parser('rollback');p.add_argument('snapshot');p.add_argument('--apply',action='store_true')
    args=parser.parse_args();os.umask(0o077)
    if args.action=='show':
        data=call('/context',{'include_native':True},timeout=120)
        if args.json:print(json.dumps(data,indent=2));return
        print(f'{"TARGET":24} {"BACKEND":9} {"CONFIGURED":>11} {"LOADED":>11} {"MODEL MAX":>11}')
        for r in data['agents']:
            print(f'{r["target"]:24} {r["backend"]:9} {r["configured_tokens"]:>11,} {str(r["loaded_context_tokens"] or "not loaded"):>11} {str(r["model_max_tokens"] or "unknown"):>11}')
        print('Loaded allocation is shared model state, not conversation usage. Larger windows may reload the model and use more VRAM.');return
    folder=ROOT/'state/context-control';folder.mkdir(parents=True,exist_ok=True)
    with (folder/'lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=settings.load();candidate=json.loads(json.dumps(current))
        if args.action=='rollback':
            if not re.fullmatch(r'\d{8}T\d{6}Z-[a-f0-9]{8}',args.snapshot):raise ValueError('Invalid snapshot ID')
            snapshot=ROOT/'backups/context-settings'/args.snapshot/'context-windows.json'
            if not snapshot.is_file():raise ValueError('Context snapshot does not exist')
            candidate=settings.load(snapshot)
        elif args.action=='reset':
            for name in settings.DEFAULTS if args.target=='all' else [args.target]:
                candidate['contexts'][name]=settings.DEFAULTS[name]
                candidate['experimental']=[x for x in candidate['experimental'] if x!=name]
        else:
            candidate['contexts'][args.target]=args.tokens
            candidate['experimental']=[x for x in candidate['experimental'] if x!=args.target]
            if args.experimental:candidate['experimental'].append(args.target)
        settings.validate(candidate)
        changed=[name for name in settings.DEFAULTS if current['contexts'][name]!=candidate['contexts'][name]]
        for name in changed:print(f'{name}: {current["contexts"][name]:,} → {candidate["contexts"][name]:,} tokens')
        if not changed:print('No context changes required.');return
        print('Compaction trigger:',settings.compression(candidate)['threshold_tokens'],'tokens. Existing generation finishes with its original allocation.')
        if not args.apply:print('Preview only. Repeat with --apply to save.');return
        live={r['target']:r for r in call('/context',{'include_native':True},timeout=120)['agents']}
        for name in changed:
            cap=live.get(name,{}).get('model_max_tokens')
            if not cap or candidate['contexts'][name]>cap:raise ValueError(name+': requested size exceeds or could not verify the installed model maximum')
        stamp=commit(candidate,current)
        print('Applied. Settings are read on the next request. Rollback: python3 contextctl.py rollback '+stamp+' --apply')
        try:
            from stack_status import refresh
            refresh()
        except Exception:print('Dashboard snapshot refresh is pending the next scheduled collection.')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,RuntimeError,subprocess.SubprocessError) as error:raise SystemExit('Context update failed: '+str(error))
