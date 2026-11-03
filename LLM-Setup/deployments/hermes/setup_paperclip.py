"""Register approved Hermes workers without altering existing routines or agent routing."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'paperclip'))
from admin_api import Admin

def main():
    os.umask(0o077);a=Admin().login()
    old=json.loads((ROOT.parent/'paperclip/instance.json').read_text());cid=old['company_id']
    agents=a.api('GET',f'/api/companies/{cid}/agents');state={'company_id':cid,'agents':{}}
    config_file=ROOT/'config/paperclip.json'
    if config_file.exists():
        prior=json.loads(config_file.read_text())
        for field in ('team_agents','diagnostic_agents'):
            if field in prior:state[field]=prior[field]
    for kind,name in [('dispatcher','Hermes HQ Dispatcher'),('health','Hermes Lab Health'),('backup','Hermes Backup Watch'),('triage','Hermes Incident Triage')]:
        payload={'name':name,'role':'engineer','title':name,'reportsTo':old['agents']['coordinator'],
            'capabilities':'Read-only HQ evidence collection and tool-free AMD-GPU analysis by default; optional NVIDIA-GPU analysis. All research collection stays on HQ. No infrastructure writes.',
            'adapterType':'process','adapterConfig':{'command':'python3','args':['/opt/hq-agents/hermes_bridge.py'],'cwd':'/paperclip','timeoutSec':600,
                'env':{'HQ_MODE':'specialist','HQ_BACKEND':'amd-gpu','HQ_HERMES_KIND':kind}},
            'runtimeConfig':{'heartbeat':{'enabled':False,'wakeOnDemand':kind!='dispatcher','maxConcurrentRuns':1,'maxDailyRuns':24}},
            'permissions':{'canCreateAgents':False,'canCreateSkills':False}}
        existing=next((x for x in agents if x['name']==name),None)
        if existing:
            payload.pop('permissions');agent=a.api('PATCH',f'/api/agents/{existing["id"]}',payload)
        else:
            hire=a.api('POST',f'/api/companies/{cid}/agent-hires',payload)
            if hire.get('approval'):a.api('POST',f'/api/approvals/{hire["approval"]["id"]}/approve',{'decisionNote':'Owner approved Hermes worker and Discord setup on 2026-11-02; read-only operations, changes require approval.'})
            agent=hire['agent']
        state['agents'][kind]=agent['id']
    secret=ROOT/'access/paperclip-api'
    if not secret.exists():
        key=a.api('POST',f'/api/agents/{state["agents"]["dispatcher"]}/keys',{'name':'HQ Hermes scoped broker'})
        token=key.get('token') or key.get('key')
        if not isinstance(token,str):raise RuntimeError('Unexpected key response; inspect key schema without logging secret')
        secret.write_text(token+'\n')
    projects=a.api('GET',f'/api/companies/{cid}/projects')
    state['project_id']=next(x['id'] for x in projects if x['name']=='Cluster Operations')
    (ROOT/'config/paperclip.json').write_text(json.dumps(state,indent=2)+'\n')
    destination=ROOT.parent/'paperclip/data/hq-hermes';destination.mkdir(exist_ok=True)
    (destination/'bridge-token').write_text((ROOT/'access/paperclip').read_text())
    print(json.dumps(state,indent=2))
if __name__=='__main__':main()
