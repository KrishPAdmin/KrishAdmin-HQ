"""Company-scoped dashboard snapshot. No credentials, account addresses or private content."""
import datetime,json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
from hq_client import ROOT,call
from team import TEAM

def refresh():
    now=datetime.datetime.now(datetime.timezone.utc).isoformat()
    config=json.loads((ROOT/'config/paperclip.json').read_text());cid=config['company_id']
    context=call('/context',{'include_native':True},timeout=120)
    status=call('/status',{},timeout=45)
    rows={r['target']:r for r in context['agents']}
    sys.path.insert(0,str(ROOT.parent/'paperclip'))
    from admin_api import Admin
    admin=Admin().login();agents=admin.api('GET','/api/companies/'+cid+'/agents')
    team_names={r['name']:key for key,r in TEAM.items()}
    legacy={'Local Coordinator':'paperclip-coordinator','NVIDIA-GPU Assistant':'paperclip-nvidia-gpu','AMD-GPU Analyst':'paperclip-amd-gpu','Pi Workspace Engineer':'pi'}
    inventory=[]
    for agent in agents:
        name=agent['name'];target=team_names.get(name) or legacy.get(name)
        if name in ('Hermes Lab Health','Hermes Backup Watch','Hermes Incident Triage'):target='analyst'
        row=rows.get(target,{})
        runtime='local model' if row else 'external / account configured' if agent['adapterType']=='codex_local' else 'fixed tools / dispatcher; no model window'
        inventory.append({'id':agent['id'],'name':name,'status':agent['status'],'title':agent.get('title'),'target':target,
                          'runtime':runtime,'backend':row.get('backend'),'model':row.get('model'),'context_tokens':row.get('configured_tokens'),
                          'model_max_tokens':row.get('model_max_tokens'),'context_control':target is not None,
                          'capabilities':(agent.get('capabilities') or '')[:1000]})
    repositories=[]
    for repo in ('KrishPAdmin/KrishAdmin-HQ','KrishPAdmin/KrishAdmin-HQ-Private'):
        try:
            raw=subprocess.run(['gh','api','repos/'+repo],capture_output=True,text=True,timeout=12,check=True)
            data=json.loads(raw.stdout)
            repositories.append({'name':repo,'url':data['html_url'],'private':data['private'],'default_branch':data['default_branch'],
                                 'open_issues_and_prs':data['open_issues_count'],'pushed_at':data['pushed_at'],'status':'reachable'})
        except Exception:repositories.append({'name':repo,'status':'unavailable'})
    try:gateway=json.loads((ROOT/'profiles/concierge/gateway_state.json').read_text()).get('platforms',{}).get('discord',{}).get('state','unknown')
    except (OSError,ValueError):gateway='unknown'
    try:notifications=json.loads((ROOT/'state/task-notifications/status.json').read_text());delivery_errors=notifications.get('delivery_errors')
    except (OSError,ValueError):delivery_errors=None
    accounts=ROOT/'state/google/accounts'
    connected=sum(1 for p in accounts.glob('*.json') if p.is_file()) if accounts.exists() else 0
    integrations=[
        {'name':'Discord gateway','status':gateway,'detail':'Enrolled channel and per-user private DMs. Paperclip report footers; long replies become Markdown attachments.'},
        {'name':'Suits / Paperclip','status':'configured','detail':str(len(TEAM))+' named specialists; '+str(len(agents))+' total Paperclip agents. Task status is separate from GPU execution.'},
        {'name':'Task notifications','status':'ready' if delivery_errors==0 else 'attention' if delivery_errors else 'unknown','detail':'Delivery errors: '+str(delivery_errors)+'; durable updates and uncertain-send reconciliation.'},
        {'name':'Local MCP research','status':'configured','detail':'Search, read public pages, weather. HQ fetches sources; AMD-GPU synthesizes evidence. Public browser rendering available.'},
        {'name':'Local MCP workbench','status':'configured','detail':'Fixed system checks, bounded file review, automation drafts; generated code is not automatically executed.'},
        {'name':'GitHub','status':'reachable' if all(r['status']=='reachable' for r in repositories) else 'partial','detail':'Two repositories; owner-only Discord reads, project status and confirmed review-branch proposals.'},
        {'name':'Gmail / Calendar','status':'OAuth pending' if connected==0 else 'enrolled; live acceptance per user','detail':f'{connected} individual account credential file(s). Email/calendar contents and account addresses are never included here. Sending and event changes require separate confirmation.'},
        {'name':'Herdr.dev','status':'installed; acceptance not established' if shutil.which('herdr') else 'not installed','detail':'Integration guide prepared. Recommended host: HQ; use existing broker and GPU queues.'},
        {'name':'Backups','status':status.get('backups',{}).get('metadata_status','unknown'),'detail':'See current backup observations and alerts. Metadata does not prove a restore; full restore and off-host coverage remain separate.'}]
    services=[]
    try:
        format='{"Name":"{{.Names}}","State":"{{.State}}","Health":"{{.Status}}","Project":"{{.Label "com.docker.compose.project"}}","Service":"{{.Label "com.docker.compose.service"}}"}'
        p=subprocess.run(['docker','ps','-a','--format',format],capture_output=True,text=True,check=True,timeout=15)
        for line in p.stdout.splitlines():
            row=json.loads(line);services.append({'Service':(row['Project']+' / '+row['Service']) if row['Project'] and row['Service'] else row['Name'],
                                                 'State':row['State'],'Health':row['Health']})
        services.sort(key=lambda row:row['Service'])
    except Exception:services=[{'Service':'HQ runtime','State':'unavailable','Health':None}]
    skills=[]
    for path in sorted((ROOT/'profiles/concierge/skills').glob('hq-*/SKILL.md')):
        skills.append({'name':path.parent.name})
    try:
        issues=admin.api('GET','/api/companies/'+cid+'/issues?limit=100')
        issues=issues if isinstance(issues,list) else issues.get('data',issues.get('issues',[]))
        tasks=[{'id':i['id'],'identifier':i.get('identifier'),'title':i['title'],'status':i['status'],'updated_at':i.get('updatedAt'),
                'url':'https://paperclip.example.invalid/KRI/issues/'+i.get('identifier',i['id'])} for i in sorted(issues,key=lambda i:i.get('updatedAt',''),reverse=True)[:10]]
    except Exception:tasks=[]
    value={'schema_version':1,'company_id':cid,'collected_at':now,'stale_after_seconds':600,'context':context,'agents':inventory,
           'services':services,'integrations':integrations,'repositories':repositories,'skills':skills,'tasks':tasks,
           'assessment':status.get('assessment'),'hosts':status.get('hosts'),'backup_status':status.get('backups'),
           'coverage':'All registered Paperclip agents and HQ Docker services, including stopped containers. Recent tasks are limited to ten; GPU telemetry refreshes separately every five seconds. Personal account content and credentials are excluded.'}
    out=ROOT.parent/'paperclip/data/hq-hermes/stack.json';out.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=out.parent)
    with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2)
    os.chmod(tmp,0o600);os.replace(tmp,out)
    return {'agents':len(inventory),'services':len(services),'collected_at':now}

if __name__=='__main__':print(json.dumps(refresh()))
