#!/usr/bin/env python3
"""One fixed target per Paperclip checker. Task text never supplies shell commands."""
import json,os,time,uuid
from pathlib import Path
import local_agent
from hermes_bridge import HermesAgent

class DiagnosticsAgent(HermesAgent):
    def infer(self,messages,schema=None):
        target=os.environ.get('HQ_DIAGNOSTIC_TARGET')
        if target not in ('hq','nvidia-gpu','amd-gpu'):raise RuntimeError('Unsupported configured target')
        started=time.monotonic();results=[]
        for check in ('overview','gpu','processes','services','storage'):
            self.require_active_run()
            results.append(local_agent.request('http://hq-hermes-broker:8080/diagnostics','POST',{'target':target,'check':check},
                {'Authorization':'Bearer '+Path('/paperclip/hq-hermes/bridge-token').read_text().strip()},timeout=60))
        folder=Path('/paperclip/operations')/str(uuid.UUID(self.issue['id']));folder.mkdir(parents=True,exist_ok=True)
        (folder/'ssh-diagnostics.json').write_text(json.dumps({'target':target,'results':results},indent=2)+'\n')
        from artifacts import attachments
        links=attachments(self,folder)
        self.execution_evidence={'kind':'Fixed local/SSH diagnostics','model_inference':False,'location':'HQ collector / '+target.upper()+' local checks','model':None,'seconds':round(time.monotonic()-started,2),'run_id':self.run_id,'note':'Read-only diagnostics; no arbitrary commands, repairs or network research on targets.'}
        report=['# '+target.upper()+' host diagnostics','']
        for r in results:
            report.append('- '+r['check']+': '+r['status']+(' — '+r['reason'] if r.get('reason') else ''))
        report+=['','Measurements are in the attached evidence. Missing commands and access errors are not proof of hardware failure. No repairs were performed.','Evidence: '+', '.join(links)]
        return '\n'.join(report),'deterministic-fixed-diagnostics',round(time.monotonic()-started,2)

if __name__=='__main__':
    agent=DiagnosticsAgent()
    try:agent.run()
    except Exception as error:
        if agent.issue:agent.api('PATCH','/issues/'+agent.issue['id'],{'status':'blocked','comment':'Fixed diagnostics failed: '+type(error).__name__+'. Inspect HQ collector before retrying.'})
        raise SystemExit(1)
