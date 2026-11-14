"""Named team task adapter; actual inference is delegated through the HQ broker."""
import json,os,re,sys,uuid
from pathlib import Path
import local_agent
from hermes_bridge import HermesAgent

def execution_requested(issue,comments):
    """Only issue instructions and human follow-ups can request workspace execution."""
    human=[c.get('body','') for c in sorted(comments,key=lambda c:c.get('createdAt','')) if c.get('authorUserId') and not c.get('authorAgentId')]
    text='\n'.join([issue.get('title',''),issue.get('description') or '',*human])
    latest=human[-1] if human else issue.get('description') or issue.get('title','')
    if re.search(r'\b(?:do not|don.t|never)\s+(?:execute|implement|build|code|run)\b|\b(?:review|plan|analysis) only\b',latest,re.I):return False
    description=issue.get('description') or ''
    if description.startswith('[HQ task kind=coding]'):return True
    if description.startswith('[HQ task kind=') and not human:return False
    return bool(re.search(r'\b(?:code|coding|software|program|application|script|app)\b',text,re.I) and
                re.search(r'\b(?:build|implement|develop|execute|create|run|make)\b',text,re.I))

class TeamAgent(HermesAgent):
    def run(self):
        # A completed execution child can wake a blocked supervising specialist.
        run=self.api('GET',f'/heartbeat-runs/{self.run_id}')
        context=run.get('contextSnapshot') or {}
        source=context.get('issueId') or context.get('taskId') or (context.get('paperclipIssue') or {}).get('id')
        if source:
            issue=self.api('GET',f'/issues/{source}')
            if issue.get('assigneeAgentId')==self.agent_id and issue.get('status')=='blocked':
                children=self.execution_children(source)
                if children and all(c.get('status')=='done' for c in children):
                    self.require_active_run()
                    self.api('PATCH',f'/issues/{source}',{'status':'todo'})
        return super().run()

    def execution_children(self,issue_id):
        children=self.api('GET',f'/companies/{self.company_id}/issues?parentId={issue_id}')
        return [c for c in children if c.get('parentId')==issue_id and c.get('createdByAgentId')==self.agent_id
                and (c.get('description') or '').startswith('[HQ coding execution v1]')]

    def review(self,content):
        child=getattr(self,'coding_child',None)
        if child and child.get('status')!='done':
            self.require_active_run()
            self.api('PATCH',f'/issues/{self.issue["id"]}',{'status':'blocked','blockedByIssueIds':[child['id']],
                'unblockDescriptor':{'owner':{'agentId':self.agent_id},'action':'Wait for the linked Benjamin coding child, verify its files and tests, then review the result. The supervising agent owns this handoff.'},
                'comment':content})
            return
        return super().review(content)

    def delegate_coding(self,messages,comments):
        children=self.execution_children(self.issue['id'])
        if children:
            child=max(children,key=lambda c:c.get('createdAt',''));self.coding_child=child
            if child.get('status')=='done':
                reports=self.api('GET',f'/issues/{child["id"]}/comments')
                messages[-1]['content']+='\n\nCompleted coding child '+child.get('identifier',child['id'])+'; review actual execution evidence, scope and remaining gaps:\n'+ '\n'.join(c.get('body','') for c in reports[:3])[:10000]
                return None
            return 'Existing coding task '+child.get('identifier',child['id'])+' is '+child['status']+'. Its files and test evidence require completion/review; no duplicate job created.','deterministic-coding-handoff',0
        human=[c.get('body','') for c in sorted(comments,key=lambda c:c.get('createdAt','')) if c.get('authorUserId') and not c.get('authorAgentId')]
        task=self.issue.get('title','')+'\n'+(self.issue.get('description') or '')+'\nHuman follow-ups:\n'+'\n'.join(human)[-6000:]
        try:
            result=local_agent.request('http://hq-hermes-broker:8080/team','POST',
                {'action':'delegate','agent':'louis','kind':'automation','question':'Prepare a concise implementable specification and concrete acceptance tests for the isolated coding worker. It WILL write and execute code. Honor the latest human scope. Do not invent legal/tax constants beyond supplied official evidence. Limit to 600 words. Task:\n'+task[:12000]},
                {'Authorization':'Bearer '+Path('/paperclip/hq-hermes/bridge-token').read_text().strip()},timeout=550)
            analysis=result['analysis']
        except (local_agent.ApiError,TimeoutError,OSError):
            # Advisory compute is not a prerequisite for already-authorized local
            # implementation. Preserve the supplied requirements and disclose it.
            analysis={'backend':'unavailable','model':'no successful Louis inference','run_id':'none',
                'seconds':0,'text':'Louis advisory service unavailable. Implement the supplied owner requirements directly; do not invent missing facts. Supervisor model review is still pending.'}
        packet='[HQ coding execution v1]\nSupervisor: '+os.environ['HQ_TEAM_AGENT']+'. Coding specification: Louis on '+analysis['backend']+' / '+analysis['model']+'; inference '+analysis['run_id']+'.\n\n'+task[:10000]+'\n\nLouis specification (advisory; task requirements take precedence):\n'+analysis['text'][:5000]
        packet+='\n\nExecutor: Benjamin, Suits Implementation Engineer; reporting to Harvey, with Louis providing coding guidance and the named supervisor reviewing the result.\n\nEXECUTE NOW: create runnable source files, tests, README with exact commands, and a test-results.txt from executed checks in this task workspace. Implement a bounded working increment; no plans-only response. Use Python standard library unless the task specifies otherwise. Keep at most five top-level deliverables, excluding caches. Do not browse from GPU hosts or deploy services. If requirements are missing, implement the independent foundation and identify the exact remaining gap. Never claim tax filing certification. Verify the files with tools and run the tests before reporting.'
        target=json.loads(Path('/opt/hq-agents/targets.json').read_text())['pi']
        self.require_active_run()
        child=self.api('POST',f'/companies/{self.company_id}/issues',{'title':('Benjamin: '+self.issue['title'])[:200],
            'description':packet,'parentId':self.issue['id'],'assigneeAgentId':target,'status':'todo',
            **({'projectId':self.issue['projectId']} if self.issue.get('projectId') else {})})
        self.coding_child=child
        advisory=('Louis supplied the specification on '+analysis['backend']+' ('+analysis['model']+', run '+analysis['run_id']+').' if analysis['backend']!='unavailable' else 'Louis advisory service was unavailable; the supplied owner requirements were forwarded unchanged. Model review remains pending.')
        return ('Coding execution assigned to '+child.get('identifier',child['id'])+'. '+advisory+' Benjamin, the Suits implementation engineer, will write files and run tests on HQ. This parent waits for verified child completion, then supervisor review. No implementation success claimed yet.','deterministic-coding-handoff',analysis['seconds'])

    def infer(self,messages,schema=None):
        name=os.environ['HQ_TEAM_AGENT']
        comments=self.api('GET',f'/issues/{self.issue["id"]}/comments')
        if execution_requested(self.issue,comments):
            handoff=self.delegate_coding(messages,comments)
            if handoff:return handoff
        description=self.issue.get('description') or self.issue.get('title','')
        match=re.match(r'^\[HQ task kind=([a-z_]+)\]\n',description)
        kind=match.group(1) if match else ('code_review' if name=='louis' else 'plan')
        if kind=='coding':kind='code_review'
        if match:description=description[match.end():]
        description=re.sub(r'\n\n\[HQ Hermes request [^\]]+\]$','',description)
        # The shared lifecycle already includes recent comments and child evidence.
        description=messages[-1]['content'][:20000]
        try:
            result=local_agent.request('http://hq-hermes-broker:8080/team','POST',
                {'action':'delegate','agent':name,'kind':kind,'question':description},
                {'Authorization':'Bearer '+Path('/paperclip/hq-hermes/bridge-token').read_text().strip()},timeout=550)
        except (local_agent.ApiError,TimeoutError,OSError):
            child=getattr(self,'coding_child',None)
            if not child or child.get('status')!='done':raise
            reports=self.api('GET',f'/issues/{child["id"]}/comments')
            report='\n\n'.join(c.get('body','') for c in reports[:2])[:12000]
            return ('Implementation evidence is available in '+child.get('identifier',child['id'])+'. The named supervisor model is currently unavailable, so no model review is claimed. Human review of the tested increment and its stated limitations is required.\n\n'+report,'deterministic-implementation-evidence',0)
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
        detail=str(error) if isinstance(error,local_agent.ApiError) else type(error).__name__
        print('Named specialist failed: '+detail,file=sys.stderr)
        if agent.issue:agent.api('PATCH',f'/issues/{agent.issue["id"]}',{'status':'blocked',
            'unblockDescriptor':{'owner':{'agentId':agent.agent_id},'action':'Inspect the HQ named-specialist runtime and reconcile before retrying.'},
            'comment':'Named specialist failed: '+detail+'. No infrastructure changes executed.'})
        raise SystemExit(1)
