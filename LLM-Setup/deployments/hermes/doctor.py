"""Read-only local diagnostics; never dumps environment variables or credentials."""
import datetime,json,stat,subprocess
import yaml
from pathlib import Path
from hq_client import ROOT,call
from health_rules import age_seconds
from team import TEAM

def diagnose():
    now=datetime.datetime.now(datetime.timezone.utc);checks=[]
    def add(name,ok,detail):checks.append({'check':name,'status':'pass' if ok else 'attention','detail':detail})
    try:
        data=call('/status',timeout=40)
        add('broker',True,'Authenticated status collection succeeded.')
        add('observations',not data['assessment']['alerts'],data['assessment']['result'])
    except Exception as error:add('broker',False,type(error).__name__+'; broker unavailable or response invalid')
    try:
        result=subprocess.run(['docker','compose','ps','--all','--format','json'],cwd=ROOT,capture_output=True,text=True,timeout=15,check=True)
        rows=[json.loads(line) for line in result.stdout.splitlines() if line.strip()]
        rows={r['Service']:r for r in rows}
        for name in ('broker','health','backup','triage','analyst','discord-egress','concierge','files','renderer','render-fetch',*TEAM):
            row=rows.get(name,{})
            add('container:'+name,row.get('State')=='running' and row.get('Health') not in ('unhealthy','starting'),
                str(row.get('State','missing'))+'; health='+str(row.get('Health') or 'not configured'))
        network=json.loads(subprocess.check_output(['docker','network','inspect','hq-hermes_private'],timeout=10))[0]
        add('internal_agent_network',network.get('Internal') is True,'Docker private network must be internal.')
        analyst=json.loads(subprocess.check_output(['docker','inspect','hq-hermes-analyst-1'],timeout=10))[0]
        add('analyst_network_membership',set(analyst['NetworkSettings']['Networks'])=={'hq-hermes_private'},'Analyst must join only the internal network.')
        browser=json.loads(subprocess.check_output(['docker','inspect','hq-hermes-renderer-1'],timeout=10))[0]
        net=json.loads(subprocess.check_output(['docker','network','inspect','hq-hermes_research_internal'],timeout=10))[0]
        add('browser_network_isolation',net.get('Internal') is True and set(browser['NetworkSettings']['Networks'])=={'hq-hermes_research_internal'},'Browser has only an internal network; public HTTPS uses the validating fetch relay.')
    except Exception as error:add('container_inspection',False,type(error).__name__+'; run docker compose ps locally')
    try:
        gateway=json.loads((ROOT/'profiles/concierge/gateway_state.json').read_text())
        heartbeat=json.loads((ROOT/'profiles/concierge/state/gateway.heartbeat').read_text())
        age=age_seconds(heartbeat.get('updated_at'),now)
        connected=gateway.get('platforms',{}).get('discord',{}).get('state')=='connected'
        add('discord_gateway',connected and age is not None and 0<=age<=180,
            'Connection='+str(connected)+'; heartbeat age seconds='+str(round(age) if age is not None else 'unknown'))
    except Exception as error:add('discord_gateway',False,type(error).__name__+'; inspect gateway state locally')
    try:
        config=yaml.safe_load((ROOT/'profiles/concierge/config.yaml').read_text())
        servers=config.get('mcp_servers',{})
        add('mcp_configuration',set(servers)=={'research','workbench'} and all(s.get('command')=='python' and s.get('tools',{}).get('resources') is False and s.get('tools',{}).get('prompts') is False for s in servers.values()),
            'Two local stdio servers with explicit tool filters; native discovery is verified separately.')
        add('conversation_compaction',config.get('compression',{}).get('enabled') is True and config.get('auxiliary',{}).get('compression',{}).get('model')==TEAM['jessica']['model'],
            'History compaction enabled with the AMD-GPU Jessica model.')
    except Exception as error:add('agent_workflow_configuration',False,type(error).__name__)
    for name in ('paperclip-observations.timer','hq-hermes-evidence.timer','hq-hermes-monitor.timer','hq-hermes-diagnostics.service','hq-hermes-task-notifications.timer','hq-hermes-github.service'):
        result=subprocess.run(['systemctl','--user','is-active',name],capture_output=True,text=True,timeout=5)
        add('timer:'+name,result.returncode==0,result.stdout.strip() or 'unknown')
    try:
        import time
        notification=json.loads((ROOT/'state/task-notifications/status.json').read_text())
        age=time.time()-notification['checked_at']
        add('task_notification_delivery',0<=age<=180 and notification['delivery_errors']==0,
            'Poll age seconds='+str(round(age))+'; delivery errors='+str(notification['delivery_errors']))
    except Exception as error:add('task_notification_delivery',False,type(error).__name__+'; inspect notification timer')
    result=subprocess.run(['systemctl','is-active','hq-backup-observations.timer'],capture_output=True,text=True,timeout=5)
    add('timer:hq-backup-observations.timer',result.returncode==0,result.stdout.strip() or 'unknown')
    exposed=[p.name for p in (ROOT/'access').iterdir() if p.is_file() and stat.S_IMODE(p.stat().st_mode)&0o077]
    add('credential_file_permissions',not exposed,'Private files are restricted to their owner.' if not exposed else 'Unexpected group/other permissions on '+', '.join(exposed))
    return {'checked_at':now.isoformat(),'result':'pass' if all(c['status']=='pass' for c in checks) else 'attention_required',
            'checks':checks,'scope':'Read-only configuration and service checks; not a security audit or full recovery test.'}
