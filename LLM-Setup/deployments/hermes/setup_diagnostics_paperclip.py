"""Register three deterministic checkers under Harvey, preserving existing agent IDs."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT.parent/'paperclip'))
from admin_api import Admin

def main():
    path=ROOT/'config/paperclip.json';cfg=json.loads(path.read_text());a=Admin().login();cid=cfg['company_id']
    existing=a.api('GET',f'/api/companies/{cid}/agents');ids={}
    for target,name in [('hq','HQ Host Checker'),('nvidia-gpu','NVIDIA-GPU GPU Checker'),('amd-gpu','AMD-GPU GPU Checker')]:
        payload={'name':name,'role':'devops','title':'Fixed read-only '+target.upper()+' diagnostics','reportsTo':cfg['team_agents']['harvey'],
          'capabilities':'Collect fresh CPU/memory, GPU/driver, process, failed-service and local-storage evidence. No model inference, arbitrary shell, repairs, or network research on targets. AMD-GPU uses the operator-selected password authentication on HQ.',
          'adapterType':'process','adapterConfig':{'command':'python3','args':['/opt/hq-agents/ssh_diagnostics_bridge.py'],'cwd':'/paperclip','timeoutSec':360,'env':{'HQ_MODE':'specialist','HQ_DIAGNOSTIC_TARGET':target}},
          'runtimeConfig':{'heartbeat':{'enabled':False,'wakeOnDemand':True,'maxConcurrentRuns':1,'maxDailyRuns':24}},'permissions':{'canCreateAgents':False,'canCreateSkills':False}}
        old=next((x for x in existing if x['name']==name),None)
        if old:
            payload.pop('permissions');agent=a.api('PATCH','/api/agents/'+old['id'],payload)
        else:
            result=a.api('POST',f'/api/companies/{cid}/agent-hires',payload)
            if result.get('approval'):a.api('POST','/api/approvals/'+result['approval']['id']+'/approve',{'decisionNote':'Owner requested SSH agents for fixed local read-only diagnostics on HQ, NVIDIA-GPU and AMD-GPU.'})
            agent=result['agent']
        ids[target]=agent['id']
    cfg['diagnostic_agents']=ids;path.write_text(json.dumps(cfg,indent=2)+'\n');print(json.dumps(ids))
if __name__=='__main__':main()
