#!/usr/bin/env python3
"""Poll subscribed Paperclip tasks; publish one durable Discord update per task/requester.

No model calls. No arbitrary recipients. HTTP errors never print credentials or bodies.
"""
import fcntl,hashlib,json,os,sqlite3,time,urllib.error,urllib.request
from pathlib import Path
from hq_client import ROOT,call
from task_updates import TERMINAL,schema,origin_checked,render,fingerprint

class DiscordError(RuntimeError):
    def __init__(self,status,retry_after=60):
        super().__init__('Discord HTTP '+str(status));self.status=status;self.retry_after=retry_after

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise RuntimeError('Discord redirect refused')

def discord(method,path,body=None):
    token=(ROOT/'access/discord-token').read_text().strip()
    request=urllib.request.Request('https://discord.com/api/v10'+path,method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Authorization':'Bot '+token,'Content-Type':'application/json','User-Agent':'DiscordBot (https://github.com/NousResearch/hermes-agent, 1.0)'})
    client=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    try:
        with client.open(request,timeout=20) as response:return json.load(response)
    except urllib.error.HTTPError as error:
        delay=60
        if error.code==429:
            try:delay=max(1,min(3600,float(json.loads(error.read(1000)).get('retry_after',60))))
            except (ValueError,TypeError):pass
        raise DiscordError(error.code,delay) from None

def marker_for(row):
    return hashlib.sha256(('|'.join(str(row[k]) for k in ('issue_id','channel_id','user_id'))).encode()).hexdigest()[:20]

def reconcile(row,marker,policy):
    """Recover a successful send whose response/SQLite commit was lost, even after restart.

    Scan back to the attempted send. If the bounded scan cannot reach it, stop safely
    instead of risking a duplicate after Discord's short nonce window expires.
    """
    before=None
    for _ in range(10):
        path='/channels/'+row['channel_id']+'/messages?limit=100'+('&before='+before if before else '')
        messages=discord('GET',path)
        for message in messages:
            if message.get('author',{}).get('id')==policy['application_id'] and ('Task update reference: '+marker) in message.get('content',''):
                return message['id']
        if len(messages)<100:return None
        before=min((m['id'] for m in messages),key=int)
        if ((int(before)>>22)+1420070400000)/1000 < row['attempted_at']-5:return None
    raise RuntimeError('Delivery reconciliation requires review; scan limit reached')

def process(db,row,policy,secrets):
    key=(row['issue_id'],row['channel_id'],row['user_id'])
    # Recheck current permissions at delivery time (also respects later user removal).
    origin_checked({'platform':'discord','chat_id':row['channel_id'],'user_id':row['user_id']},policy)
    pending=json.loads(row['pending']) if row['pending'] else None
    if pending is None:
        result=call('/task',{'action':'status','task_id':row['issue_id'],'include_result':True},timeout=100)
        if result['status'] not in TERMINAL:
            db.execute('UPDATE task_watches SET next_poll=?,failures=0,last_error=NULL WHERE issue_id=? AND channel_id=? AND user_id=?',(time.time()+30,*key));db.commit();return 'waiting'
        payload=render(result,row['user_id'],marker_for(row),secrets)
        content_hash=fingerprint(payload)
        if row['delivered_hash']==content_hash:
            db.execute('UPDATE task_watches SET next_poll=?,failures=0,last_error=NULL WHERE issue_id=? AND channel_id=? AND user_id=?',(time.time()+30,*key));db.commit();return 'unchanged'
        pending={'payload':payload,'hash':content_hash,'status':result['status']}
        db.execute('UPDATE task_watches SET pending=? WHERE issue_id=? AND channel_id=? AND user_id=?',(json.dumps(pending),*key));db.commit()
    message_id=row['message_id'];marker=marker_for(row)
    if not message_id and row['attempted_at']:
        message_id=reconcile(row,marker,policy)
    if message_id:
        # Edits are idempotent. Deleted update messages remain an explicit error for review.
        response=discord('PATCH','/channels/'+row['channel_id']+'/messages/'+message_id,pending['payload'])
    else:
        db.execute('UPDATE task_watches SET attempted_at=? WHERE issue_id=? AND channel_id=? AND user_id=?',(time.time(),*key));db.commit()
        payload={**pending['payload'],'nonce':marker,'enforce_nonce':True}
        if row['source_message_id']:
            payload['message_reference']={'message_id':row['source_message_id'],'fail_if_not_exists':False}
        response=discord('POST','/channels/'+row['channel_id']+'/messages',payload)
    if not str(response.get('id','')).isdigit():raise RuntimeError('Missing Discord delivery receipt')
    db.execute('''UPDATE task_watches SET message_id=?,delivered_hash=?,pending=NULL,attempted_at=NULL,
        next_poll=?,failures=0,last_error=NULL,closed=? WHERE issue_id=? AND channel_id=? AND user_id=?''',
        (response['id'],pending['hash'],time.time()+30,int(pending['status'] in ('done','cancelled','canceled')),*key));db.commit()
    return 'delivered'

def run_once():
    os.umask(0o077)
    folder=ROOT/'state/task-notifications';folder.mkdir(exist_ok=True)
    with (folder/'lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        policy=json.loads((ROOT/'profiles/concierge/discord-enrollment.json').read_text())
        secrets=[p.read_text().strip() for p in (ROOT/'access').iterdir() if p.is_file()]
        counts={}
        with sqlite3.connect(ROOT/'state/tasks.db',timeout=10) as db:
            db.row_factory=sqlite3.Row;schema(db);db.commit()
            rows=db.execute('SELECT * FROM task_watches WHERE closed=0 AND next_poll<=? ORDER BY next_poll LIMIT 50',(time.time(),)).fetchall()
            for row in rows:
                try:outcome=process(db,row,policy,secrets)
                except Exception as error:
                    outcome='error';failures=row['failures']+1
                    delay=max(min(900,30*2**min(failures,5)),getattr(error,'retry_after',0))
                    detail=type(error).__name__+(' '+str(error.status) if isinstance(error,DiscordError) else '')
                    db.execute('UPDATE task_watches SET failures=?,last_error=?,next_poll=? WHERE issue_id=? AND channel_id=? AND user_id=?',
                               (failures,detail,time.time()+delay,row['issue_id'],row['channel_id'],row['user_id']));db.commit()
                counts[outcome]=counts.get(outcome,0)+1
            errors=db.execute('SELECT COUNT(*) FROM task_watches WHERE closed=0 AND last_error IS NOT NULL').fetchone()[0]
        receipt={'checked_at':time.time(),'counts':counts,'delivery_errors':errors}
        temp=folder/'status.tmp';temp.write_text(json.dumps(receipt)+'\n');temp.replace(folder/'status.json')
        print(json.dumps(receipt))

if __name__=='__main__':run_once()
