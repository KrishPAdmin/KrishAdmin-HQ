"""Paperclip process adapter for bounded read-only Hermes workers on HQ."""
import json,os,sys,uuid
from pathlib import Path
import local_agent

class HermesAgent(local_agent.Agent):
    def private_values(self):
        values=[os.environ.get('PAPERCLIP_API_KEY',''),Path('/paperclip/hq-hermes/bridge-token').read_text().strip()]
        return [v for v in values if len(v)>6]

    def require_active_run(self):
        if self.api('GET',f'/heartbeat-runs/{self.run_id}').get('status')!='running':raise SystemExit(2)

    def review(self,content):
        self.require_active_run()
        return super().review(content)

    def infer(self,messages,schema=None):
        kind=os.environ['HQ_HERMES_KIND']
        if kind not in ('health','backup','triage'):raise RuntimeError('Dispatcher is intake-only; assign a specialist')
        result=local_agent.request('http://hq-hermes-broker:8080/run','POST',
            {'kind':kind,'question':messages[-1]['content'][:4000]},
            {'Authorization':'Bearer '+Path('/paperclip/hq-hermes/bridge-token').read_text().strip()},timeout=550)
        workspace=Path('/paperclip/operations')/str(uuid.UUID(self.issue['id']));workspace.mkdir(parents=True,exist_ok=True)
        (workspace/'hermes-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
        from artifacts import attachments
        links=attachments(self,workspace)
        analysis=result['analysis'];evidence=result['evidence'];self.backend=analysis['backend']
        self.execution_evidence={'kind':'Hermes evidence analysis','model_inference':True,'location':'HQ agent / '+analysis['backend'].upper()+' inference',
            'model':analysis['model'],'seconds':analysis['seconds'],'run_id':analysis['run_id'],
            'note':'Collection and agent execution occur on HQ. Source hash: '+evidence['evidence_sha256']+'. GPU inference receipts are in the HQ broker audit.'}
        headline='Partial observation; not a complete infrastructure health certification.'
        text=headline+'\n\nSnapshot: '+evidence.get('snapshot_status','not applicable')+'. Coverage: '+json.dumps(evidence.get('coverage',{}))+'.\n\nModel analysis (advisory):\n'+analysis['text']+'\n\nEvidence: '+', '.join(links)
        return text,analysis['model'],analysis['seconds']

if __name__=='__main__':
    # Local-only adapter: do not call the generic optional cloud escalation handler.
    agent=HermesAgent()
    try:agent.run()
    except Exception as e:
        print('Hermes adapter failure: '+type(e).__name__+': '+str(e)[:200],file=sys.stderr)
        if agent.issue:
            agent.api('PATCH',f'/issues/{agent.issue["id"]}',{'status':'blocked',
                'unblockDescriptor':{'owner':{'agentId':agent.agent_id},'action':'Inspect local runtime evidence and reconcile before retrying.'},
                'comment':'Hermes worker failed: '+type(e).__name__+'. Inspect local runtime evidence before retrying.'})
        raise SystemExit(1)
