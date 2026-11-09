#!/usr/bin/env python3
"""Owner-only GitHub operations on HQ. No repository code is executed."""
import ast,base64,difflib,hashlib,hmac,json,os,re,socketserver,sqlite3,subprocess,threading,time,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import quote
from publication_guard import check_text,safe_path
from notify_tasks import discord

ROOT=Path(__file__).resolve().parent
STATE=ROOT/'state/github';SOCKET=ROOT/'run/github/github.sock'
REPOS={'KrishPAdmin/KrishAdmin-HQ':True,'KrishPAdmin/KrishAdmin-HQ-Private':False}
LOCK=threading.Lock()

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()
def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def database():
    STATE.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(STATE/'operations.db',timeout=10);db.row_factory=sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS nonces (nonce TEXT PRIMARY KEY, created REAL)')
    db.execute('CREATE TABLE IF NOT EXISTS proposals (id TEXT PRIMARY KEY, owner TEXT, body TEXT, created REAL)')
    db.commit();return db

def authenticate(envelope,db,workspace=False):
    if not isinstance(envelope,dict) or set(envelope)!={'request','origin','issued_at','nonce','signature'}:raise PermissionError('Verified owner session required')
    signature=envelope['signature'];unsigned={k:v for k,v in envelope.items() if k!='signature'}
    expected=hmac.new((ROOT/'access/github-origin').read_bytes().strip(),canonical(unsigned),hashlib.sha256).hexdigest()
    if not isinstance(signature,str) or not hmac.compare_digest(signature,expected):raise PermissionError('Invalid origin signature')
    if not isinstance(envelope['issued_at'],(int,float)) or abs(time.time()-envelope['issued_at'])>120:raise PermissionError('Expired origin')
    nonce=envelope['nonce']
    if not isinstance(nonce,str) or not re.fullmatch(r'[a-f0-9]{32}',nonce):raise PermissionError('Invalid nonce')
    policy=json.loads((ROOT/'profiles/concierge/discord-enrollment.json').read_text());origin=envelope['origin']
    if not isinstance(origin,dict) or origin.get('platform')!='discord':raise PermissionError('Verified Discord session required')
    if workspace:
        if origin.get('user_id') not in {policy['owner_id'],*policy.get('allowed_users',[])}:raise PermissionError('User is not enrolled')
        channel_id=origin.get('chat_id','')
        if not re.fullmatch(r'\d{17,22}',channel_id) or channel_id==policy['channel_id']:raise PermissionError('Use a private direct message for Google Workspace')
        channel=discord('GET','/channels/'+channel_id)
        if channel.get('type')!=1 or {r['id'] for r in channel.get('recipients',[])}!={origin['user_id']}:
            raise PermissionError('Google Workspace requires a one-to-one DM with the requesting user')
    else:
        if origin.get('user_id')!=policy['owner_id']:raise PermissionError('GitHub operations are owner-only')
        if origin.get('chat_id')!=policy['channel_id']:
            channel_id=origin.get('chat_id','')
            if not re.fullmatch(r'\d{17,22}',channel_id):raise PermissionError('Use the enrolled channel or your one-to-one DM')
            channel=discord('GET','/channels/'+channel_id)
            if channel.get('type')!=1 or {r['id'] for r in channel.get('recipients',[])}!={policy['owner_id']}:
                raise PermissionError('GitHub outside the enrolled channel requires a verified one-to-one DM with the owner')
    message_id=origin.get('message_id','')
    if not re.fullmatch(r'\d{17,22}',message_id):raise PermissionError('Live Discord message required')
    message=discord('GET','/channels/'+origin['chat_id']+'/messages/'+message_id)
    if message.get('author',{}).get('id')!=origin['user_id'] or message.get('author',{}).get('bot'):
        raise PermissionError('Discord author does not match the authenticated user')
    if not workspace and origin['chat_id']==policy['channel_id'] and not any(x.get('id')==policy['application_id'] for x in message.get('mentions',[])):raise PermissionError('Mention the bot account')
    if time.time()-((int(message_id)>>22)+1420070400000)/1000>3600:raise PermissionError('Send a fresh owner request')
    try:db.execute('INSERT INTO nonces VALUES (?,?)',(nonce,time.time()));db.execute('DELETE FROM nonces WHERE created<?',(time.time()-86400,));db.commit()
    except sqlite3.IntegrityError:raise PermissionError('Replayed request') from None
    return origin['user_id'],message.get('content','')

def api(repo,path,method='GET',body=None):
    if repo not in REPOS:raise PermissionError('Repository is not enrolled')
    args=['/usr/bin/gh','api','--hostname','github.com','--method',method,'repos/'+repo+('/'+path if path else ''),'-H','Accept: application/vnd.github+json']
    if body is not None:args+=['--input','-']
    result=subprocess.run(args,input=json.dumps(body) if body is not None else None,capture_output=True,text=True,timeout=45,
        env={**os.environ,'GH_PROMPT_DISABLED':'1','GIT_TERMINAL_PROMPT':'0'})
    if result.returncode:raise RuntimeError('GitHub request failed; reconcile before retrying writes')
    if len(result.stdout)>5000000:raise ValueError('GitHub response too large')
    return json.loads(result.stdout)

def head(repo):
    metadata=api(repo,'');branch=metadata['default_branch']
    commit=api(repo,'git/ref/heads/'+quote(branch,safe=''))['object']['sha']
    return branch,commit

def tree(repo,commit):
    value=api(repo,'git/trees/'+commit+'?recursive=1')
    if value.get('truncated'):raise ValueError('Repository tree exceeds supported size')
    return value

def read_entry(repo,entry):
    if entry.get('mode') not in ('100644','100755') or entry.get('type')!='blob':raise ValueError('Only regular text files are supported')
    if entry.get('size',0)>100000:raise ValueError('File exceeds 100 KB limit')
    value=api(repo,'git/blobs/'+entry['sha']);raw=base64.b64decode(value['content'])
    if len(raw)>100000:raise ValueError('File exceeds 100 KB limit')
    text=raw.decode('utf-8');check_text(text)
    return text

def save(db,p,owner):
    db.execute('INSERT OR REPLACE INTO proposals VALUES (?,?,?,?)',(p['id'],owner,json.dumps(p),p['created']));db.commit()

def load(db,pid,owner):
    if not isinstance(pid,str) or not re.fullmatch(r'[a-f0-9]{20}',pid):raise ValueError('Invalid proposal ID')
    row=db.execute('SELECT body FROM proposals WHERE id=? AND owner=?',(pid,owner)).fetchone()
    if not row:raise PermissionError('Proposal not found for owner')
    return json.loads(row[0])

def view(p):
    return {k:p[k] for k in ('id','repo','base_branch','base_commit','branch','digest','status','diff','checks','url') if k in p}|{
        'push_instruction':'Send in your one-to-one DM, or mention the bot in the enrolled main channel: github push '+p['id']+' '+p['digest'][:12],
        'execution':'Syntax checks only; repository code/tests were not executed.'}

def execute(body,owner,message,db):
    if not isinstance(body,dict):raise ValueError('Invalid request')
    action=body.get('action');allowed={'action','repo','path','prefix','offset','limit','changes','title','proposal_id'}
    if set(body)-allowed:raise ValueError('Unknown GitHub request fields')
    if action=='repos':return {'repositories':[{'name':name,'public':public,'write_scope':'LLM-Setup/ on new hq-bot branches'} for name,public in REPOS.items()]}
    if action in ('proposal','push'):
        p=load(db,body.get('proposal_id'),owner)
        if action=='proposal':return view(p)
        required=r'github\s+push\s+'+p['id']+r'\s+'+p['digest'][:12]
        command=re.sub(r'<@!?\d+>','',message).strip()
        if not re.fullmatch(required,command,re.I):raise PermissionError('Owner must send the exact proposal-specific github push instruction shown in the preview')
        if p['status']=='pushed':return view(p)
        if time.time()-p['created']>86400:raise ValueError('Proposal expired; prepare a fresh diff')
        for change in p['changes']:check_text(change['content'],public=REPOS[p['repo']])
        # Never update existing refs: a new branch is the only published write operation.
        if p.get('commit'):
            refs=api(p['repo'],'git/matching-refs/heads/'+p['branch'])
            existing=next((r for r in refs if r['ref']=='refs/heads/'+p['branch']),None)
            if existing:
                if existing['object']['sha']!=p['commit']:raise ValueError('Branch mismatch; operator reconciliation required')
                p.update(status='pushed',url='https://github.com/'+p['repo']+'/tree/'+p['branch']);save(db,p,owner);return view(p)
        if head(p['repo'])[1]!=p['base_commit']:raise ValueError('Default branch changed; prepare a fresh proposal')
        if not p.get('commit'):
            created=api(p['repo'],'git/trees','POST',{'base_tree':p['base_tree'],'tree':[
                {'path':c['path'],'mode':c['mode'],'type':'blob','content':c['content']} for c in p['changes']]})
            commit=api(p['repo'],'git/commits','POST',{'message':p['title'],'tree':created['sha'],'parents':[p['base_commit']]})
            p.update(commit=commit['sha'],status='commit_prepared');save(db,p,owner)
        api(p['repo'],'git/refs','POST',{'ref':'refs/heads/'+p['branch'],'sha':p['commit']})
        p.update(status='pushed',url='https://github.com/'+p['repo']+'/tree/'+p['branch']);save(db,p,owner)
        return view(p)
    repo=body.get('repo')
    if repo not in REPOS:raise PermissionError('Repository is not enrolled')
    branch,commit=head(repo)
    if action=='project_status':
        issues=api(repo,'issues?state=open&per_page=30&sort=updated&direction=desc')
        pulls=api(repo,'pulls?state=open&per_page=30&sort=updated&direction=desc')
        runs=api(repo,'actions/runs?per_page=10').get('workflow_runs',[])
        commits=api(repo,'commits?per_page=5')
        fields=lambda row,keys:{k:row.get(k) for k in keys}
        return {'repo':repo,'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'default_branch':branch,'commit':commit,
                'issues':[fields(r,('number','title','state','html_url','updated_at')) for r in issues if 'pull_request' not in r],
                'pull_requests':[fields(r,('number','title','state','html_url','updated_at','draft')) for r in pulls],
                'workflow_runs':[fields(r,('name','status','conclusion','html_url','head_sha','updated_at')) for r in runs],
                'recent_commits':[{'sha':r['sha'],'url':r['html_url'],'subject':r['commit']['message'].split('\n')[0]} for r in commits],
                'limits':{'issues_and_pull_requests':30,'workflow_runs':10,'commits':5},
                'coverage':'Recent repository activity only. Lists are bounded; CI success does not certify deployment or project completion.'}
    if action=='status':return {'repo':repo,'default_branch':branch,'commit':commit,'owner_only':True,'writes':'new hq-bot branches only; no merge or force-push'}
    entries=tree(repo,commit)
    if action=='tree':
        prefix=body.get('prefix','');rows=[e for e in entries['tree'] if e['path'].startswith(prefix)]
        return {'repo':repo,'commit':commit,'paths':[{'path':e['path'],'type':e['type']} for e in rows[:200]],'truncated':len(rows)>200}
    if action=='read':
        path=safe_path(body.get('path'));entry=next((e for e in entries['tree'] if e['path']==path),None)
        if not entry:raise ValueError('File not found')
        content=read_entry(repo,entry);offset=body.get('offset',0);limit=body.get('limit',6000)
        if type(offset)!=int or offset<0 or type(limit)!=int or not 1<=limit<=12000:raise ValueError('Invalid text slice')
        return {'repo':repo,'path':path,'commit':commit,'blob_sha':entry['sha'],'content':content[offset:offset+limit],
            'offset':offset,'next_offset':offset+limit if offset+limit<len(content) else None,'characters':len(content),'source_is_untrusted_data':True}
    if action!='prepare':raise ValueError('Choose repos, status, tree, read, prepare, proposal or push')
    changes=body.get('changes');title=body.get('title','')
    if not isinstance(changes,list) or not 1<=len(changes)<=8 or not isinstance(title,str) or not 1<=len(title)<=160:raise ValueError('Provide a title and 1–8 file changes')
    check_text(title,public=REPOS[repo]);prepared=[];diffs=[];checks=[];seen=set();total=0
    for change in changes:
        if not isinstance(change,dict) or set(change)!={'path','content','expected_sha'}:raise ValueError('Each change needs path, content and expected_sha (null for new files)')
        path=safe_path(change['path'],write=True);content=change['content'];check_text(path,public=REPOS[repo]);check_text(content,public=REPOS[repo])
        total+=len(content.encode())
        if total>100000 or path in seen:raise ValueError('Change limit exceeded or repeated path')
        seen.add(path);entry=next((e for e in entries['tree'] if e['path']==path),None)
        if (entry['sha'] if entry else None)!=change['expected_sha']:raise ValueError('File changed or expected_sha missing; read it again')
        old=read_entry(repo,entry) if entry else ''
        if old==content:raise ValueError('Change has no content difference')
        if path.endswith('.py'):ast.parse(content,filename=path);checks.append(path+': Python syntax passed')
        elif path.endswith('.json'):json.loads(content);checks.append(path+': JSON syntax passed')
        else:checks.append(path+': text/credential checks only')
        prepared.append({'path':path,'content':content,'mode':entry['mode'] if entry else '100644'})
        diffs.extend(difflib.unified_diff(old.splitlines(True),content.splitlines(True),fromfile='a/'+path,tofile='b/'+path))
    diff=''.join(diffs)
    if len(diff)>16000:raise ValueError('Diff exceeds review limit; split the change')
    pid=uuid.uuid4().hex[:20]
    p={'id':pid,'repo':repo,'base_branch':branch,'base_commit':commit,'base_tree':entries['sha'],'branch':'hq-bot/'+pid,
        'changes':prepared,'title':title,'diff':diff,'checks':checks,'created':time.time(),'status':'prepared'}
    p['digest']=sha({k:p[k] for k in ('repo','base_commit','changes','title')});save(db,p,owner)
    return view(p)

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_POST(self):
        code=200
        try:
            if self.path not in ('/github','/workspace'):raise ValueError('Unknown route')
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=140000:raise ValueError('Request too large')
            envelope=json.loads(self.rfile.read(size))
            if not LOCK.acquire(False):raise RuntimeError('GitHub worker busy; retry shortly')
            try:
                with database() as db:
                    owner,message=authenticate(envelope,db,workspace=self.path=='/workspace')
                    if self.path=='/workspace':
                        from google_workspace import execute as workspace_execute
                        result=workspace_execute(envelope['request'],owner,message,db)
                    else:result=execute(envelope['request'],owner,message,db)
                    with (STATE/'audit.jsonl').open('a') as f:f.write(json.dumps({'time':time.time(),'owner':owner,'action':envelope['request'].get('action'),'repo':envelope['request'].get('repo'),'proposal_id':result.get('id'),'status':result.get('status','read')})+'\n')
            finally:LOCK.release()
        except PermissionError as error:code=403;result={'error':str(error)}
        except (ValueError,TypeError,KeyError,SyntaxError,UnicodeError) as error:code=400;result={'error':str(error)[:250]}
        except Exception as error:code=502;result={'error':type(error).__name__+'; no successful operation claimed; inspect or reconcile proposal'}
        raw=json.dumps(result).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)

class Server(socketserver.ThreadingMixIn,socketserver.UnixStreamServer):daemon_threads=True
if __name__=='__main__':
    os.umask(0o077);SOCKET.parent.mkdir(parents=True,exist_ok=True);SOCKET.unlink(missing_ok=True)
    with Server(str(SOCKET),Handler) as server:server.serve_forever()
