#!/usr/bin/env python3
"""Refresh allowlisted observations; no arbitrary commands or model input."""
import concurrent.futures, datetime, ipaddress, json, os, re, subprocess, tempfile
from pathlib import Path
from host_probe import collect, command
ROOT = Path(__file__).resolve().parent
def targets():
    configured = json.loads((ROOT/'targets.json').read_text())
    if not isinstance(configured,dict) or len(configured)>16: raise ValueError('At most 16 host targets are supported')
    # The operator UI can enroll restricted observers, but cannot supply SSH commands or key paths.
    control_root = ROOT.parent/'data/hq-control'
    for file in control_root.glob('*.json'):
        control=json.loads(file.read_text())
        for target in control.get('systems',[]):
            if target.get('kind')=='linux' and target.get('readAccess')!='off':
                configured['managed_'+target['id'].replace('-','')]={'host':target['host'],'user':'paperclip-observer','key':str(ROOT/'keys/observer')}
    if len(configured)>16: raise ValueError('At most 16 observed hosts are supported')
    for name,cfg in configured.items():
        address=ipaddress.ip_address(cfg['host'])
        if address not in ipaddress.ip_network('192.0.2.0/24') and str(address)!='198.51.100.202':
            raise ValueError('Host outside authorized network')
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}',cfg['user']):raise ValueError('Invalid SSH user')
        if cfg.get('auth')=='password':
            if name!='amd-gpu' or cfg['host']!='198.51.100.202' or cfg['user']!='krishadmin':raise ValueError('Unsupported password-auth target')
            continue
        key=Path(cfg['key']).resolve()
        if not (key.is_relative_to(Path.home()/'.ssh') or key.is_relative_to(ROOT/'keys')):raise ValueError('SSH key outside observer key directories')
    return configured

def remote(item):
    name, cfg = item
    host, key, user = cfg['host'], cfg.get('key'), cfg['user']
    try:
        if cfg.get('auth')=='password':
            from ssh_access import amd_gpu
            r=amd_gpu('/usr/bin/python3 /usr/local/lib/paperclip/host_probe.py',timeout=25)
        else:
            r = subprocess.run(['ssh','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes',
                '-o','ConnectTimeout=5','-i',key,user+'@'+host,'python3 -'],
                input=(ROOT/'host_probe.py').read_text(), capture_output=True,text=True,timeout=25)
        if r.returncode:
            return name, {'status':'unavailable', 'reason':'SSH authentication, host verification or transport failed', 'exit_code':r.returncode}
        return name, {'status':'observed', 'data':json.loads(r.stdout)}
    except (OSError,ValueError,subprocess.TimeoutExpired) as e:
        return name, {'status':'unavailable','reason':type(e).__name__}

def main():
    local = collect()
    local['containers'] = command(['sudo','-n','docker','ps','-a','--format','{{.Names}}\t{{.State}}\t{{.Status}}'])
    result = {'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(), 'hq':local}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        result['remote_hosts'] = dict(pool.map(remote,targets().items()))
    folder = ROOT/'snapshots'; folder.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=folder,prefix='.health-')
    try:
        with os.fdopen(fd,'w') as f: json.dump(result,f,indent=2); f.write('\n')
        os.chmod(tmp,0o644); os.replace(tmp,folder/'host-health.json')
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print(json.dumps({'event':'host_snapshot_refreshed','remote':{k:v['status'] for k,v in result['remote_hosts'].items()}}))
if __name__ == '__main__': main()
