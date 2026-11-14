#!/usr/bin/env python3
"""HQ host service: a private Unix socket brokers fixed SSH observer requests."""
import datetime,hashlib,hmac,json,os,socketserver,subprocess,threading,sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler
ROOT=Path(__file__).resolve().parent
OPS=ROOT.parent/'paperclip/operations';SOCKET=ROOT/'run/diagnostics/check.sock'
CHECKS=('overview','gpu','processes','services','storage');HOSTS={'nvidia-gpu':'192.0.2.181','amd-gpu':'198.51.100.202'}
LOCK=threading.BoundedSemaphore(2)

def execute(body):
    if not isinstance(body,dict) or set(body)-{'target','check'}:raise ValueError('Only target and check are accepted')
    target=body.get('target');check=body.get('check','overview')
    if target not in ('hq',*HOSTS) or check not in CHECKS:raise ValueError('Select hq, nvidia-gpu or amd-gpu and a supported diagnostic check')
    if not LOCK.acquire(blocking=False):raise RuntimeError('Diagnostic workers are busy; retry shortly')
    try:
        if target=='hq':args=['/usr/bin/python3',str(OPS/'diagnostics_probe.py'),check]
        else:args=['/usr/bin/ssh','-F','/dev/null','-o','BatchMode=yes','-o','IdentitiesOnly=yes','-o','StrictHostKeyChecking=yes','-o','ClearAllForwardings=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-o','UserKnownHostsFile='+str(Path.home()/'.ssh/known_hosts'),'-i',str(OPS/'keys/observer'),'paperclip-observer@'+HOSTS[target],'diagnostics '+check]
        try:
            if target=='amd-gpu':
                sys.path.insert(0,str(OPS))
                from ssh_access import amd_gpu
                r=amd_gpu('/usr/bin/python3 /usr/local/lib/paperclip/diagnostics_probe.py '+check,timeout=40)
            else:r=subprocess.run(args,capture_output=True,text=True,timeout=40)
        except subprocess.TimeoutExpired:return {'target':target,'check':check,'status':'unavailable','reason':'Diagnostic collection timed out'}
        if r.returncode:return {'target':target,'check':check,'status':'unavailable','reason':'SSH/observer or local probe failed; verify enrollment and host trust','exit_code':r.returncode}
        if len(r.stdout)>65000:raise ValueError('Probe output exceeds limit')
        data=json.loads(r.stdout)
        if data.get('schema_version')!=1 or data.get('check')!=check:
            return {'target':target,'check':check,'status':'unavailable','reason':'Observer upgrade required; the installed observer only supports basic telemetry','basic_telemetry_unchanged':True}
        data.update(target=target,transport='local' if target=='hq' else 'verified SSH password authentication; fixed HQ command allowlist' if target=='amd-gpu' else 'verified SSH forced command')
        data['evidence_sha256']=hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
        receipt={k:data[k] for k in ('target','check','status','checked_at_utc','evidence_sha256')}
        with (ROOT/'state/diagnostics/audit.jsonl').open('a') as f:f.write(json.dumps(receipt)+'\n')
        return data
    finally:LOCK.release()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        status=200
        try:
            if self.path not in ('/diagnostics','/homelab-read'):raise ValueError('Unknown route')
            if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+(ROOT/'access/worker').read_text().strip()):
                status=403;raise ValueError('Forbidden')
            n=int(self.headers.get('Content-Length',0))
            if not 0<n<=1024:raise ValueError('Invalid body size')
            body=json.loads(self.rfile.read(n))
            if self.path=='/homelab-read':
                if body!={}:raise ValueError('Homelab read accepts no arguments')
                if not LOCK.acquire(blocking=False):raise RuntimeError('Diagnostic workers are busy')
                try:
                    result=subprocess.run([str(ROOT/'.venv-management/bin/python'),str(ROOT/'homelab_read.py')],capture_output=True,text=True,timeout=90)
                    if result.returncode or len(result.stdout)>65000:raise RuntimeError('Homelab collection failed')
                    data=json.loads(result.stdout)
                finally:LOCK.release()
            else:data=execute(body)
        except (ValueError,TypeError) as e:status=400 if status==200 else status;data={'error':str(e)}
        except RuntimeError as e:status=409;data={'error':str(e)}
        except Exception as e:status=502;data={'error':type(e).__name__}
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
if __name__=='__main__':
    os.umask(0o077);SOCKET.parent.mkdir(parents=True,exist_ok=True);(ROOT/'state/diagnostics').mkdir(parents=True,exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET),Handler) as server:server.serve_forever()
