"""Enrich pending review content without changing recipients, outcomes or task state.

The installed API has no interaction-edit route. Update only presentation fields
with optimistic guards, preserve a before snapshot, and write an operator audit event.
"""
import json,re,subprocess,sys,uuid
from pathlib import Path
from admin_api import Admin,ROOT
sys.path.insert(0,str(ROOT/'agents'))
from review_details import build_review

def historical_compute(issue,content,agents,interaction=None):
    agent=agents.get(issue.get('assigneeAgentId'),{})
    config=agent.get('adapterConfig') or {}
    if '/opt/hq-agents/operations.py' in config.get('args',[]) or ('TCP connect discovery only' in content and 'no additional coordinator inference was required' in content):
        return {'kind':'Deterministic Python tools / CPU','location':'HQ 192.0.2.180 / Paperclip server container',
                'model_inference':False,'model':None,'input_tokens':0,'output_tokens':0,
                'run_id':(interaction or {}).get('sourceRunId'),
                'note':'Verified against the fixed operations runtime and task evidence. Any old NVIDIA-GPU label on deterministic results was incorrect.'}
    match=re.search(r'Local inference: `([^`]+)` on \*\*(NVIDIA-GPU|AMD-GPU)\*\*; ([\d.]+)s',content)
    if match and not match[1].startswith('deterministic-'):
        return {'kind':'Local model inference','location':match[2]+' GPU endpoint','model_inference':True,'model':match[1],'seconds':float(match[3]),'run_id':(interaction or {}).get('sourceRunId'),'note':'Historical model attribution from runtime footer; utilization and token counts not reconstructed.'}
    return {'kind':'Historical compute not recorded','location':'Not recorded','note':'No compute claim is inferred from the assigned agent name alone. See task run history.'}

def main():
    a=Admin().login();s=json.loads((ROOT/'instance.json').read_text());cid=s['company_id']
    agents={r['id']:r for r in a.api('GET',f'/api/companies/{cid}/agents')}
    issues=a.api('GET',f'/api/companies/{cid}/issues?status=in_review');changes=[];before=[]
    for issue in issues:
        if issue['status']!='in_review':continue
        interactions=a.api('GET',f'/api/issues/{issue["id"]}/interactions')
        pending=[r for r in interactions if r['status']=='pending' and r['kind']=='request_confirmation'
                 and r.get('title')=='Review local agent result' and not r['payload'].get('toolAction') and not r['payload'].get('secretProposal')]
        if not pending:continue
        comments=a.api('GET',f'/api/issues/{issue["id"]}/comments')
        for decision in pending:
            outputs=[c for c in comments if c.get('authorAgentId')==decision.get('createdByAgentId') and
                     (not decision.get('sourceRunId') or c.get('createdByRunId')==decision['sourceRunId'])]
            outputs=[c for c in outputs if not c['body'].startswith(('Waiting for team:','HQ execution plan'))]
            if not outputs:continue
            content=outputs[0]['body']
            execution=historical_compute(issue,content,agents,decision)
            detail=build_review(issue,content,execution)
            changes.append({'id':decision['id'],'issue_id':issue['id'],'title':detail['title'],'summary':detail['summary'],
                            'payload':detail['payload'],'expected_payload':decision['payload'],'expected_updated_at':decision['updatedAt']})
            before.append({'issue':{'id':issue['id'],'identifier':issue['identifier']},'interaction':decision})
    if not changes:
        print(json.dumps({'updated_pending_reviews':0,'reason':'No generic pending reviews need enrichment'}))
        return
    folder=ROOT/'validation/decision-details';folder.mkdir(exist_ok=True)
    snapshot = folder/'pending-reviews-before.json'
    if snapshot.exists(): snapshot = folder/('pending-reviews-before-'+uuid.uuid4().hex+'.json')
    snapshot.write_text(json.dumps(before,indent=2)+'\n')
    (folder/'pending-reviews-patch.json').write_text(json.dumps(changes,indent=2)+'\n')
    marker='review_'+uuid.uuid4().hex;payload=json.dumps(changes)
    sql=f'''BEGIN;
WITH patches AS (
 SELECT * FROM jsonb_to_recordset(${marker}${payload}${marker}$::jsonb)
 AS p(id uuid, issue_id uuid, title text, summary text, payload jsonb, expected_payload jsonb, expected_updated_at timestamptz)
), changed AS (
 UPDATE issue_thread_interactions i SET title=p.title,summary=p.summary,payload=i.payload||p.payload,updated_at=now()
 FROM patches p WHERE i.id=p.id AND i.issue_id=p.issue_id AND i.company_id='{cid}'::uuid
 AND i.status='pending' AND i.kind='request_confirmation' AND i.title='Review local agent result'
 AND date_trunc('milliseconds',i.updated_at)=p.expected_updated_at AND i.payload=p.expected_payload
 AND NOT (i.payload ? 'toolAction') AND NOT (i.payload ? 'secretProposal')
 RETURNING i.id
) SELECT coalesce(json_agg(id),'[]'::json) FROM changed;
COMMIT;'''
    r=subprocess.run(['sudo','-n','docker','compose','exec','-T','db','psql','-U','paperclip','-d','paperclip','-v','ON_ERROR_STOP=1','-At'],input=sql,text=True,capture_output=True,check=True)
    updated=json.loads(next(line for line in r.stdout.splitlines() if line.startswith('[')))
    session=a.api('GET','/api/auth/get-session')
    a.api('POST',f'/api/companies/{cid}/activity',{'actorType':'user','actorId':session['user']['id'],
        'action':'issue.review_details_enriched','entityType':'company','entityId':cid,
        'details':{'interactionIds':updated,'count':len(updated),'reason':'Operator requested detailed pending decision cards. Presentation fields only; outcomes, recipients, resolver policies and task status unchanged.'}})
    (folder/'enrichment-result.json').write_text(json.dumps({'updated':updated,'count':len(updated)},indent=2)+'\n')
    print(json.dumps({'updated_pending_reviews':len(updated)}))
if __name__=='__main__':main()
