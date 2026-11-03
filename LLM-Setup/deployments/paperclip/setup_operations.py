"""Idempotent operator provisioning of observational agents and routines."""
import json
from admin_api import Admin, ROOT

def main():
    a=Admin().login(); state=json.loads((ROOT/'instance.json').read_text()); cid=state['company_id']
    agents=a.api('GET',f'/api/companies/{cid}/agents'); ids={}
    def upsert(payload, old):
        if old:
            payload.pop('permissions', None)
            return a.api('PATCH', f'/api/agents/{old["id"]}', payload)
        hire=a.api('POST',f'/api/companies/{cid}/agent-hires',payload)
        if hire.get('approval'):
            a.api('POST',f'/api/approvals/{hire["approval"]["id"]}/approve',
                  {'decisionNote':'Operator authorized the outlined network, health, diagnostics and Codex integration work on 2026-10-24.'})
        return hire['agent']
    heartbeat={'heartbeat':{'enabled':False,'intervalSec':0,'wakeOnDemand':True,'maxConcurrentRuns':1,'maxDailyRuns':100}}
    for name, mode, description in [
        ('System Health Observer','health','Read-only GPU API checks and fresh HQ/NVIDIA-GPU host observations. Publishes measured JSON and Markdown; marks stale or unavailable coverage explicitly.'),
        ('Network Discovery','network','Bounded TCP connect discovery of 192.0.2.0/24 on ports 22,53,80,443,445,8006,8443,11434. No arbitrary ranges or commands.'),
        ('System Diagnostics','diagnostics','Collects current GPU and HQ/NVIDIA-GPU host evidence, failed services, container status and resource usage. No host changes. AMD-GPU host access may be unavailable.')]:
        payload={'name':name,'role':'engineer','title':name,'reportsTo':state['agents']['coordinator'],
            'capabilities':description,'adapterType':'process',
            'adapterConfig':{'command':'python3','args':['/opt/hq-agents/operations.py'],'cwd':'/paperclip','timeoutSec':120,
                'env':{'HQ_MODE':'specialist','HQ_BACKEND':'nvidia-gpu','HQ_OPERATIONS_MODE':mode}},
            'runtimeConfig':heartbeat,'permissions':{'canCreateAgents':False,'canCreateSkills':False}}
        old=next((x for x in agents if x['name']==name),None)
        agent=upsert(payload,old)
        ids[mode]=agent['id']
    # A dedicated Codex home supports device login without exposing the operator's full host home.
    name='Codex Escalation Engineer'
    payload={'name':name,'role':'engineer','title':name,'reportsTo':state['agents']['coordinator'],
        'capabilities':'External Codex debugging and code repair from supplied evidence in /paperclip/codex-workspace. Account login required. No host SSH keys, host Docker socket or power/storage access.',
        'adapterType':'codex_local','adapterConfig':{'engine':'cli','command':'/opt/hq-agents/codex_guard.py','cwd':'/paperclip/codex-workspace','timeoutSec':600,
            'env':{'CODEX_HOME':'/paperclip/codex-operator'},
            'instructionsFilePath':'/opt/hq-agents/codex-instructions.md','dangerouslyBypassApprovalsAndSandbox':False},
        'runtimeConfig':heartbeat,'permissions':{'canCreateAgents':False,'canCreateSkills':False}}
    old=next((x for x in agents if x['name']==name),None)
    agent=upsert(payload,old)
    ids['codex']=agent['id']
    cfg=json.loads((ROOT/'agents/department.json').read_text())
    # Enable Codex routing only after a successful live account QA run.
    cfg['targets'].update({k:ids[k] for k in ('health','network','diagnostics')})
    if cfg.get('codex_ready'): cfg['targets']['codex'] = ids['codex']
    (ROOT/'agents/department.json').write_text(json.dumps(cfg,indent=2)+'\n')
    state['operations_agents']=ids;(ROOT/'instance.json').write_text(json.dumps(state,indent=2)+'\n')
    routines=a.api('GET',f'/api/companies/{cid}/routines')
    daily=next(x for x in routines if x['title']=='Daily GPU health report')
    a.api('PATCH',f'/api/routines/{daily["id"]}',{'assigneeAgentId':ids['health'],
        'description':'Deterministic GPU API and host observations. Publish actual JSON and Markdown. No model generation required. Missing or stale telemetry is unknown; never report it healthy.',
        'concurrencyPolicy':'skip_if_active','catchUpPolicy':'skip_missed'})
    print(json.dumps(ids,indent=2))
if __name__=='__main__':main()
