"""Single-job Codex controller. No Paperclip credentials, host mounts or LAN egress."""
import hashlib,hmac,json,os,secrets,shutil,subprocess,threading,uuid,signal,tempfile,time,re,base64
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
AUTH=Path('/auth');JOBS=Path('/jobs');GATE=threading.Lock();LOGIN={'process':None,'output':None};RUN_STATE={'uid':None,'sha256':None}
def login_state():
 p=LOGIN['process'];f=LOGIN['output']
 if not p:return {'status':'idle','auth_configured':(AUTH/'auth.json').exists()}
 raw=os.pread(f.fileno(),min(os.fstat(f.fileno()).st_size,10000),0).decode(errors='replace');raw=re.sub(r'\x1b\[[0-9;]*m','',raw)
 code=re.search(r'\b[A-Z0-9]{4}-[A-Z0-9]{5}\b',raw)
 return {'status':'connected' if p.poll()==0 else 'failed' if p.poll() is not None else 'pending','verificationUrl':'https://auth.openai.com/codex/device','userCode':code.group(0) if code else None}
def stop_uid(uid):
 for _ in range(3):
  found=False
  for proc in Path('/proc').iterdir():
   if not proc.name.isdigit():continue
   try:
    line=next(x for x in (proc/'status').read_text().splitlines() if x.startswith('Uid:'))
    if int(line.split()[1])==uid:os.kill(int(proc.name),signal.SIGKILL);found=True
   except (OSError,StopIteration,ValueError):pass
  if not found:return
  time.sleep(.05)

class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def reply(self,status,data):
  raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
 def do_GET(self):self.reply(200 if self.path=='/health' else 404,{'ok':self.path=='/health','auth_configured':(AUTH/'auth.json').exists()})
 def do_POST(self):
  secret=Path('/run/secrets/worker-bridge-token').read_text().strip()
  if self.path not in ('/run','/login/start','/login/status','/cancel') or not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+secret):self.reply(403,{'error':'Forbidden'});return
  if self.path=='/cancel':
   try:
    n=int(self.headers.get('Content-Length','0'));body=json.loads(self.rfile.read(min(n,1000)))
    if RUN_STATE['uid'] is not None and body.get('sha256')==RUN_STATE['sha256']:stop_uid(RUN_STATE['uid'])
    self.reply(200,{'ok':True})
   except Exception:self.reply(400,{'error':'Invalid cancellation'})
   return
  if self.path=='/login/status':self.reply(200,login_state());return
  if self.path=='/login/start':
   old=LOGIN['process']
   if old and old.poll() is None:self.reply(200,login_state());return
   if GATE.locked():self.reply(409,{'error':'Wait for the current approved task to finish.'});return
   AUTH.mkdir(exist_ok=True);f=tempfile.TemporaryFile();env={**os.environ,'HOME':'/auth','CODEX_HOME':'/auth','HTTPS_PROXY':'http://codex-egress:8888','HTTP_PROXY':'http://codex-egress:8888','ALL_PROXY':'http://codex-egress:8888','NO_PROXY':''}
   LOGIN.update(process=subprocess.Popen(['codex','login','--device-auth'],stdout=f,stderr=f,env=env,start_new_session=True),output=f)
   time.sleep(.5);self.reply(200,login_state());return
  if not GATE.acquire(False):self.reply(409,{'error':'Codex worker is busy. Retry when the current approved task finishes.'});return
  job=None;uid=None
  try:
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<160000:raise ValueError()
   b=json.loads(self.rfile.read(n));prompt=b['prompt'];digest=b['sha256']
   if not isinstance(prompt,str) or len(prompt)>20000 or hashlib.sha256(prompt.encode()).hexdigest()!=digest:raise ValueError()
   if not (AUTH/'auth.json').exists():self.reply(422,{'error':'Codex account needs to be connected.'});return
   uid=200000+secrets.randbelow(1_000_000_000);job=JOBS/str(uuid.uuid4());home=job/'home';workspace=job/'workspace';home.mkdir(parents=True,mode=0o700);workspace.mkdir(mode=0o700)
   old_auth=json.loads((AUTH/'auth.json').read_text())
   shutil.copyfile(AUTH/'auth.json',home/'auth.json');(home/'auth.json').chmod(0o600)
   (home/'config.toml').write_text('cli_auth_credentials_store = "file"\nforced_login_method = "chatgpt"\n')
   for p in [job,home,workspace,*home.iterdir()]:os.chown(p,uid,uid)
   RUN_STATE.update(uid=uid,sha256=digest)
   env={'PATH':'/usr/local/bin:/usr/bin:/bin','HOME':str(home),'CODEX_HOME':str(home),
        'HTTPS_PROXY':'http://codex-egress:8888','HTTP_PROXY':'http://codex-egress:8888','ALL_PROXY':'http://codex-egress:8888','NO_PROXY':'','CODEX_DISABLE_TELEMETRY':'1'}
   # Container network and separate Unix UID enforce the boundary; no host sandbox bypass is used.
   args=['codex','-a','never','exec','--json','--skip-git-repo-check','--sandbox','danger-full-access','-']
   with tempfile.TemporaryFile() as out,tempfile.TemporaryFile() as err:
    proc=subprocess.Popen(args,stdin=subprocess.PIPE,stdout=out,stderr=err,env=env,cwd=workspace,user=uid,group=uid,extra_groups=[],start_new_session=True)
    proc.stdin.write(prompt.encode());proc.stdin.close();deadline=time.monotonic()+480
    while proc.poll() is None:
     if time.monotonic()>deadline or os.fstat(out.fileno()).st_size>4_000_000 or os.fstat(err.fileno()).st_size>1_000_000:
      os.killpg(proc.pid,signal.SIGKILL);proc.wait();self.reply(504,{'error':'Approved task exceeded its time or output limit.'});return
     time.sleep(.25)
    out.seek(0);err.seek(0)
    class Result:pass
    r=Result();r.returncode=proc.returncode;r.stdout=out.read(4_000_000).decode(errors='replace');r.stderr=err.read(1200).decode(errors='replace')
   stop_uid(uid)
   # Retain token refreshes in the root-owned account cache, never in results.
   if not home.is_symlink() and not (home/'auth.json').is_symlink() and (home/'auth.json').exists() and (home/'auth.json').stat().st_size<20000:
    refreshed=json.loads((home/'auth.json').read_text());tmp=AUTH/'auth.next.json';tmp.write_text(json.dumps(refreshed));tmp.chmod(0o600);tmp.replace(AUTH/'auth.json')
   credential_values=[]
   for data in [old_auth,json.loads((AUTH/'auth.json').read_text())]:
    for v in (data.get('tokens') or {}).values():
     if isinstance(v,str) and len(v)>20:credential_values.append(v)
   raw=r.stdout[:4_000_000];err=r.stderr[:1200]
   for value in credential_values:raw=raw.replace(value,'[redacted]');err=err.replace(value,'[redacted]')
   files=[]
   if not workspace.is_symlink():
    for file in workspace.rglob('*'):
     if len(files)>=3:break
     rel=file.relative_to(workspace)
     if file.is_symlink() or not file.is_file() or any(part.startswith('.') for part in rel.parts) or not file.resolve().is_relative_to(workspace.resolve()):continue
     if not 0<file.stat().st_size<=262144:continue
     content=file.read_bytes()
     if any(value.encode() in content for value in credential_values):continue
     files.append({'name':str(rel),'base64':base64.b64encode(content).decode()})
   self.reply(200,{'ok':r.returncode==0,'stdout':raw,'error':err if r.returncode else '', 'packet_sha256':digest,'files':files})
  except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.reply(400,{'error':'Invalid approved packet.'})
  except Exception:self.reply(500,{'error':'Codex worker could not execute the approved packet.'})
  finally:
   if uid is not None:stop_uid(uid)
   RUN_STATE.update(uid=None,sha256=None)
   if job is not None:shutil.rmtree(job,ignore_errors=True)
   GATE.release()
if __name__=='__main__':
 JOBS.mkdir(exist_ok=True);JOBS.chmod(0o755);ThreadingHTTPServer(('0.0.0.0',8081),Handler).serve_forever()
