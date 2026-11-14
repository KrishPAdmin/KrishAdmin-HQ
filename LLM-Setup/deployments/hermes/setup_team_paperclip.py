"""Register the operator-requested Suits team and its reporting hierarchy."""
import datetime,json,os,sys
from pathlib import Path
from team import TEAM, EXECUTION_TEAM
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'paperclip'))
from admin_api import Admin

def sync_execution(admin,config,public):
    """Reuse the existing worker identity, adapter and tasks; update its team metadata."""
    target=json.loads((ROOT.parent/'paperclip/agents/targets.json').read_text())['pi']
    role=EXECUTION_TEAM['benjamin'];manager=config['team_agents'][role['reports_to']]
    admin.api('PATCH',f'/api/agents/{target}',{'name':role['name'],'title':role['title'],
        'reportsTo':manager,'capabilities':role['persona']+' Model: '+role['model']+' on NVIDIA-GPU; file and shell tools run on HQ.'})
    config['execution_agents']={'benjamin':target}
    public['agents']=[a for a in public['agents'] if a['id']!=target and a.get('key')!='benjamin']
    public['agents'].append({**{k:v for k,v in role.items() if k!='persona'},'key':'benjamin',
        'id':target,'summary':role['persona'],'reports_to_id':manager})
    public['generated_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
    (ROOT/'config/paperclip.json').write_text(json.dumps(config,indent=2)+'\n')
    return public

def main():
    os.umask(0o077);admin=Admin().login()
    config=json.loads((ROOT/'config/paperclip.json').read_text());cid=config['company_id']
    destination=ROOT.parent/'paperclip/data/hq-hermes/team.json'
    if '--execution-only' in sys.argv:
        public=sync_execution(admin,config,json.loads(destination.read_text()))
        temp=destination.with_suffix('.json.tmp');temp.write_text(json.dumps(public,indent=2)+'\n');temp.replace(destination)
        print(json.dumps(config['execution_agents'],indent=2));return
    existing=admin.api('GET',f'/api/companies/{cid}/agents');ids={}
    coordinator=json.loads((ROOT.parent/'paperclip/instance.json').read_text())['agents']['coordinator']
    for name,role in TEAM.items():
        payload={'name':role['name'],'role':{'jessica':'ceo','harvey':'pm','rachel':'researcher','donna':'general'}.get(name,'engineer'),'title':role['title'],
            'reportsTo':None if role['reports_to']=='operator' else ids[role['reports_to']],
            'capabilities':role['persona']+' Fixed model: '+role['model']+' on '+role['backend']+'. Paperclip coding requests delegate implementation to Benjamin, the Suits implementation engineer, with real HQ file/test tools; synchronous team analysis remains advisory. No infrastructure writes.',
            'adapterType':'process','adapterConfig':{'command':'python3','args':['/opt/hq-agents/hermes_team_bridge.py'],'cwd':'/paperclip','timeoutSec':600,
                'env':{'HQ_MODE':'specialist','HQ_BACKEND':role['backend'],'HQ_TEAM_AGENT':name}},
            'runtimeConfig':{'heartbeat':{'enabled':False,'wakeOnDemand':True,'maxConcurrentRuns':1,'maxDailyRuns':24}},
            'permissions':{'canCreateAgents':False,'canCreateSkills':False}}
        prior=next((a for a in existing if a['name']==role['name']),None)
        if prior:
            payload.pop('permissions');agent=admin.api('PATCH',f'/api/agents/{prior["id"]}',payload)
        else:
            result=admin.api('POST',f'/api/companies/{cid}/agent-hires',payload)
            if result.get('approval'):admin.api('POST',f'/api/approvals/{result["approval"]["id"]}/approve',{'decisionNote':'Operator explicitly requested these six named local specialists and their seniority/model hierarchy; analysis and draft output only.'})
            agent=result['agent']
        ids[name]=agent['id']
    config['team_agents']=ids;(ROOT/'config/paperclip.json').write_text(json.dumps(config,indent=2)+'\n')
    (ROOT.parent/'paperclip/agents/coding_supervisors.json').write_text(json.dumps(sorted(ids.values()),indent=2)+'\n')
    # Keep existing routine assignments while placing their coordinator under Donna.
    admin.api('PATCH',f'/api/agents/{coordinator}',{'role':'pm','title':'Existing workflow coordinator','reportsTo':ids['donna']})
    public={'company_id':cid,'generated_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'agents':[{**{k:v for k,v in role.items() if k!='persona'},'key':name,'id':ids[name],
            'summary':role['persona'],'reports_to_id':ids.get(role['reports_to'])} for name,role in TEAM.items()]}
    public=sync_execution(admin,config,public)
    temp=destination.with_suffix('.json.tmp');temp.write_text(json.dumps(public,indent=2)+'\n');temp.replace(destination)
    print(json.dumps(ids,indent=2))

if __name__=='__main__':main()
