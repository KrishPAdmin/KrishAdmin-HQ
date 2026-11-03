#!/usr/bin/env python3
"""Local operator interface; credentials are never command-line arguments."""
import argparse,json,os
from pathlib import Path
from hq_client import ROOT,call
from capabilities import TASKS
from team import TEAM

GUIDES={'index':'index.md','quickstart':'quickstart.md','architecture':'architecture.md',
        'operations':'operations.md','monitoring':'monitoring.md','discord':'discord.md',
        'backups':'backups.md','security':'security.md','troubleshooting':'troubleshooting.md',
        'recovery':'recovery.md','reference':'reference.md','acceptance':'acceptance.md','capabilities':'capabilities.md','diagnostics':'diagnostics.md','github':'github.md'}
def main():
    p=argparse.ArgumentParser(description='HQ operations: status and diagnostics are read-only; submit creates a read-only Paperclip task.')
    p.add_argument('operation',choices=['status','alerts','history','doctor','report','guide','health','backup','triage','research','submit','task-status','analyze','files','knowledge','compute','team','calculate','diagnostics'])
    p.add_argument('--target',choices=['hq','nvidia-gpu','amd-gpu']);p.add_argument('--check',choices=['overview','gpu','processes','services','storage'],default='overview')
    p.add_argument('--question',default='Report current evidence and explicitly identify missing coverage.')
    p.add_argument('--url',action='append');p.add_argument('--kind',choices=TASKS)
    p.add_argument('--text',default='');p.add_argument('--text-file',type=Path);p.add_argument('--file-id');p.add_argument('--offset',type=int,default=0)
    p.add_argument('--file-limit',type=int,default=3000);p.add_argument('--compute',choices=['nvidia-gpu','amd-gpu']);p.add_argument('--agent',choices=TEAM)
    p.add_argument('--query');p.add_argument('--expression')
    p.add_argument('--task');p.add_argument('--request-id');p.add_argument('--output',type=Path,help='Save report to a new private Markdown file; refuses overwrite')
    p.add_argument('--section',choices=GUIDES,default='index');p.add_argument('--limit',type=int,default=20)
    a=p.parse_args()
    if a.output and a.operation!='report':p.error('--output is available only for report')
    if not 1<=a.limit<=200:p.error('--limit must be 1–200')
    if a.operation=='guide':print((ROOT/'docs'/GUIDES[a.section]).read_text());return
    if a.operation=='doctor':
        from doctor import diagnose
        result=diagnose();print(json.dumps(result,indent=2))
        if result['result']!='pass':raise SystemExit(1)
        return
    if a.operation=='history':
        path=ROOT/'state/monitor.json'
        if not path.exists():print(json.dumps({'status':'not_collected','events':[]}));return
        result=json.loads(path.read_text())
        from health_rules import age_seconds
        import datetime
        age=age_seconds(result.get('checked_at'),datetime.datetime.now(datetime.timezone.utc))
        print(json.dumps({'checked_at':result.get('checked_at'),'freshness':'fresh' if age is not None and 0<=age<=600 else 'stale',
            'collection_status':result.get('collection_status'),'active_alerts':result.get('active_alerts',[]),
            'events':result.get('events',[])[-a.limit:]},indent=2));return
    if a.operation in ('status','alerts','report'):route,body='/status',{}
    elif a.operation=='diagnostics':
        if not a.target:p.error('--target is required for diagnostics')
        route,body='/diagnostics',{'target':a.target,'check':a.check}
    elif a.operation=='calculate':route,body='/calculate',{'expression':a.expression}
    elif a.operation=='compute':route,body='/compute',{}
    elif a.operation=='files':route,body='/files',{'action':'read' if a.file_id else 'list','file_id':a.file_id,'offset':a.offset,'limit':a.file_limit}
    elif a.operation=='knowledge':route,body='/knowledge',{'query':a.query} if a.query else {'section':a.section}
    elif a.operation in ('analyze','team'):
        text=a.text
        if a.text_file:
            if a.text_file.stat().st_size>12000:p.error('--text-file must be at most 12000 bytes; supply a smaller excerpt')
            text=a.text_file.read_text()
        body={'kind':a.kind or 'plan','question':a.question,'text':text,'file_id':a.file_id,'offset':a.offset,'limit':a.file_limit}
        route='/analyze'
        if a.operation=='team':
            route='/team';body.update(action='delegate' if a.agent else 'roster',agent=a.agent,compute=a.compute,urls=a.url)
    elif a.operation=='research':route,body='/research',{'urls':a.url or [],'question':a.question}
    elif a.operation=='submit':
        if not a.request_id:p.error('--request-id is required for durable deduplication')
        route,body='/task',{'action':'submit','kind':a.kind or 'health','agent':a.agent,'description':a.question,'request_id':a.request_id}
    elif a.operation=='task-status':
        if not a.task:p.error('--task is required')
        route,body='/task',{'action':'status','task_id':a.task}
    else:route,body='/run',{'kind':a.operation,'question':a.question,'compute':a.compute or 'amd-gpu'}
    result=call(route,body)
    if a.operation=='alerts':result={k:result.get(k) for k in ('collected_at','assessment','monitor_history','evidence_sha256')}
    if a.operation=='report':
        from reporting import markdown
        text=markdown(result)
        if a.output:
            fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as f:f.write(text)
            print('Report saved: '+str(a.output.resolve()))
        else:print(text)
        return
    print(json.dumps(result,indent=2))

if __name__=='__main__':
    try:main()
    except (RuntimeError,OSError,ValueError) as error:
        print('Operation failed: '+(str(error) if isinstance(error,RuntimeError) else type(error).__name__)+'. Run hq.py doctor for service checks.')
        raise SystemExit(1)
