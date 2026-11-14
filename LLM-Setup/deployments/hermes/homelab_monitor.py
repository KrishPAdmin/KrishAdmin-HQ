#!/usr/bin/env python3
"""One-minute observations with bounded, reconciled owner-only Discord changes."""
import fcntl,hashlib,json,os,time
from homelab import ROOT,STATE,snapshot
from notify_tasks import discord

def states(data):
    result={h['target']:h['status'] for h in data['hosts']}
    for key,name,value in [('swarm_nodes','hostname','status'),('swarm_services','name','replicas')]:
        collection=data.get(key,[])
        if isinstance(collection,list):
            result.update({key+':'+row[name]:row[value] for row in collection})
        else:result[key]='unavailable'
    kuma=data.get('uptime_kuma',{})
    if 'monitors' not in kuma:result['uptime_kuma']='unavailable'
    else:
        for row in kuma['monitors']:
            if row['active']:result['monitor:'+row['name']]=row['status']
    return result

def save(name,data):
    path=STATE/name;temp=path.with_suffix('.tmp');temp.write_text(json.dumps(data,indent=2)+'\n');temp.replace(path)

def changes(previous,current):
    return [{'name':key,'before':previous.get(key,'not observed'),'after':current.get(key,'not observed')} for key in sorted(previous.keys()|current.keys()) if previous.get(key)!=current.get(key)]

def deliver(pending,policy):
    channel=policy.get('maintenance_dm',{})
    if channel.get('owner_id')!=policy['owner_id']:raise PermissionError('Owner DM is not enrolled')
    target=channel['channel_id'];destination=discord('GET','/channels/'+target)
    if destination.get('type')!=1 or {r['id'] for r in destination.get('recipients',[])}!={policy['owner_id']}:raise PermissionError('Owner DM mismatch')
    marker=pending['marker'];before=None
    if pending.get('attempted_at'):
        # Reconcile a lost response before retrying; never blindly duplicate a send.
        reached=False
        for _ in range(5):
            messages=discord('GET','/channels/'+target+'/messages?limit=100'+('&before='+before if before else ''))
            if any(m.get('author',{}).get('id')==policy['application_id'] and marker in m.get('content','') for m in messages):return
            if len(messages)<100:reached=True;break
            before=min((m['id'] for m in messages),key=int)
            if ((int(before)>>22)+1420070400000)/1000<pending['attempted_at']-5:reached=True;break
        if not reached:raise RuntimeError('Notification reconciliation requires review')
    pending['attempted_at']=time.time();save('pending.json',pending)
    result=discord('POST','/channels/'+target+'/messages',{'content':pending['content'],'allowed_mentions':{'parse':[]},'nonce':marker[-20:],'enforce_nonce':True})
    if not result.get('id'):raise RuntimeError('Missing delivery receipt')

def run_once():
    os.umask(0o077);STATE.mkdir(parents=True,exist_ok=True)
    with (STATE/'monitor.lock').open('w') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        watch=json.loads((STATE/'watch.json').read_text()) if (STATE/'watch.json').exists() else {'enabled':False}
        policy=json.loads((ROOT/'profiles/concierge/discord-enrollment.json').read_text())
        if not watch.get('enabled') or watch.get('owner')!=policy['owner_id']:return
        pending_path=STATE/'pending.json'
        if pending_path.exists():
            pending=json.loads(pending_path.read_text());deliver(pending,policy);save('previous.json',pending['states']);pending_path.unlink()
        data=snapshot();save('snapshot.json',data);current=states(data)
        previous_path=STATE/'previous.json'
        if not previous_path.exists():save('previous.json',current);return
        delta=changes(json.loads(previous_path.read_text()),current)
        if not delta:return
        marker='Homelab update '+hashlib.sha256(json.dumps([current,data['checked_at']],sort_keys=True).encode()).hexdigest()[:20]
        labels={0:'down',1:'up',2:'pending',3:'maintenance',None:'unknown'}
        text='Homelab status changes — '+data['checked_at']+'\n'
        for row in delta[:15]:
            label=lambda v:labels.get(v,v) if row['name'].startswith('monitor:') else v
            text+=row['name'][:80]+': '+str(label(row['before']))+' → '+str(label(row['after']))+'\n'
        if len(delta)>15:text+=str(len(delta)-15)+' additional changes; ask for current homelab status.\n'
        text+='https://status.example.invalid/dashboard\n'+marker
        pending={'states':current,'marker':marker,'content':text[:1950]};save('pending.json',pending)
        deliver(pending,policy);save('previous.json',current);pending_path.unlink()

if __name__=='__main__':
    try:run_once()
    except Exception as error:
        save('monitor-error.json',{'time':time.time(),'error':type(error).__name__})
        raise SystemExit(1)
