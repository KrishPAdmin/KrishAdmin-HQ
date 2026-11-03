"""Named team task adapter; actual inference is delegated through the HQ broker."""
import json,os,re,sys,uuid
from pathlib import Path
import local_agent
from hermes_bridge import HermesAgent

class TeamAgent(HermesAgent):
    def infer(self,messages,schema=None):
        name=os.environ['HQ_TEAM_AGENT']
        description=self.issue.get('description') or self.issue.get('title','')
        match=re.match(r'^\[HQ task kind=([a-z_]+)\]\n',description)
        kind=match.group(1) if match else ('code_review' if name=='louis' else 'plan')
        if match:description=description[match.end():]
        description=re.sub(r'\n\n\[HQ Hermes request [^\]]+\]$','',description)
        result=local_agent.request('http://hq-hermes-broker:8080/team','POST',
            {'action':'delegate','agent':name,'kind':kind,'question':description},
            {'Authorization':'Bearer '+Path('/paperclip/hq-hermes/bridge-token').read_text().strip()},timeout=550)
        analysis=result['analysis'];self.backend=analysis['backend']
        folder=Path('/paperclip/operations')/str(uuid.UUID(self.issue['id']));folder.mkdir(parents=True,exist_ok=True)
        (folder/'hermes-team-evidence.json').write_text(json.dumps(result,indent=2)+'\n')
        from artifacts import attachments
        links=attachments(self,folder)
        self.execution_evidence={'kind':'Named local specialist','model_inference':True,'location':'HQ runtime / '+self.backend.upper()+' inference',
            'model':analysis['model'],'seconds':analysis['seconds'],'run_id':analysis['run_id'],
            'note':'Specialist '+analysis['name']+'; output is advisory. No infrastructure changes executed.'}
        return analysis['text']+'\n\nEvidence: '+', '.join(links),analysis['model'],analysis['seconds']

if __name__=='__main__':
    agent=TeamAgent()
    try:agent.run()
    except Exception as error:
        print('Named specialist failed: '+type(error).__name__,file=sys.stderr)
        if agent.issue:agent.api('PATCH',f'/issues/{agent.issue["id"]}',{'status':'blocked',
            'unblockDescriptor':{'owner':{'agentId':agent.agent_id},'action':'Inspect the HQ named-specialist runtime and reconcile before retrying.'},
            'comment':'Named specialist failed: '+type(error).__name__+'. No infrastructure changes executed.'})
        raise SystemExit(1)
