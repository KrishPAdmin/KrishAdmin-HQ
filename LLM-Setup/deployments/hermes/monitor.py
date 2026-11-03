#!/usr/bin/env python3
"""Bounded local observation history. Never sends messages or repairs infrastructure."""
import datetime,fcntl,json,os,tempfile
from pathlib import Path
from hq_client import call,ROOT

MAX_EVENTS=200
MAX_SAMPLES=288

def save(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2);f.write('\n')
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def advance(previous,alerts,stamp,ok):
    old={a['id']:a for a in previous.get('active_alerts',[])}
    new={a['id']:a for a in alerts}
    # Failed collection cannot prove recovery of previously measured problems.
    if not ok:new={**old,**new}
    events=list(previous.get('events',[]))
    for key,row in new.items():
        if key not in old or old[key]['severity']!=row['severity']:
            events.append({'time':stamp,'change':'raised' if key not in old else 'severity_changed',**row})
    for key,row in old.items():
        if key not in new:events.append({'time':stamp,'change':'resolved',**row})
    return {'checked_at':stamp,'collection_status':'ok' if ok else 'unavailable',
            'last_success_at':stamp if ok else previous.get('last_success_at'),
            'active_alerts':list(new.values()),'events':events[-MAX_EVENTS:]}

def main():
    state=ROOT/'state';state.mkdir(exist_ok=True)
    with (state/'monitor.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        previous={}
        path=state/'monitor.json'
        if path.exists():previous=json.loads(path.read_text())
        stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();packet=None
        try:packet=call('/status',timeout=40);alerts=packet['assessment']['alerts'];ok=True
        except Exception:
            alerts=[{'id':'broker:local','target':'broker','severity':'critical','message':'The local monitor could not collect status.',
                     'next_step':'Run python3 hq.py doctor and inspect local services.'}];ok=False
        value=advance(previous,alerts,stamp,ok)
        samples=previous.get('samples',[])
        samples.append({'time':stamp,'collection_ok':ok,'alert_count':len(value['active_alerts']),
            'gpu_api':{g['system']:g['status'] for g in (packet or {}).get('gpu_api',[])},
            'snapshot_age_seconds':(packet or {}).get('snapshot_age_seconds'),
            'evidence_sha256':(packet or {}).get('evidence_sha256')})
        value['samples']=samples[-MAX_SAMPLES:];save(path,value)
        print(json.dumps({'collection':value['collection_status'],'active_alerts':len(value['active_alerts']),
                          'retained_events':len(value['events']),'retained_samples':len(value['samples'])}))
        if not ok:raise SystemExit(1)

if __name__=='__main__':main()
