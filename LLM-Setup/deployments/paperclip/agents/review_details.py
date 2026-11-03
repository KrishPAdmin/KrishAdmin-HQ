"""Evidence-based review cards and human-readable compute receipts."""
import json,re


def compute_markdown(execution=None):
    e=execution or {}
    rows=[('Execution type',e.get('kind','Not recorded for this historical task')),
          ('Where it ran',e.get('location','Not recorded')),
          ('Model for this step',e.get('model') or ('None — no model inference' if e.get('model_inference') is False else 'Not recorded'))]
    if e.get('seconds') is not None:rows.append(('Execution time',str(e['seconds'])+' seconds'))
    if e.get('input_tokens') is not None:rows.append(('Input / output tokens',str(e['input_tokens'])+' / '+str(e.get('output_tokens',0))))
    if e.get('run_id'):rows.append(('Run ID',e['run_id']))
    if e.get('note'):rows.append(('Evidence limits',e['note']))
    def cell(value):return str(value).replace('|','\\|').replace('\n',' ')
    return '## Compute used\n\n| Field | Recorded value |\n|---|---|\n'+'\n'.join('| '+a+' | '+cell(b)+' |' for a,b in rows)


def readable_result(content):
    lines=[]
    skipping_compute=False
    for line in content.splitlines():
        # Raw artifact JSON is already downloadable; don't bury the review in a duplicate dump.
        if re.match(r'^\S+\.json: [\[{]',line):continue
        if 'Local inference: `deterministic-' in line:continue
        if line.startswith('## Compute used'):
            skipping_compute=True
            continue
        if skipping_compute:
            if not line.strip() or line.startswith('|'):continue
            skipping_compute=False
        lines.append(line)
    text='\n'.join(lines).strip()
    return text[:10000]+('\n\nFull evidence continues on the task.' if len(text)>10000 else '')


def build_review(issue,content,execution=None):
    identifier=issue.get('identifier',issue['id'])
    request=issue.get('description') or 'No task description was provided.'
    result=readable_result(content)
    network='TCP connect discovery only' in content
    logs_requested=bool(re.search(r'\blogs?\b',request,re.I))
    ips=set(re.findall(r'^- (192\.0\.2\.\d+): TCP',content,re.M))
    gaps=[]
    if network:
        findings=f'Network discovery found {len(ips)} responding addresses on 192.0.2.0/24 using the configured TCP ports.'
        gaps.append('Discovery did not authenticate to discovered hosts or collect/verify their system logs. Open ports do not establish system health or device identity.')
        if logs_requested:
            findings+=' Partial completion: the requested host-log verification has not been performed.'
            prompt=f'{len(ips)} addresses responded to the network scan. Requested host logs were NOT verified. Decide whether to accept discovery only or request authenticated log checks.'
        else:prompt=f'{len(ips)} addresses responded to TCP discovery. Review the scan evidence and its limits before accepting the discovery result.'
    else:
        candidates=[l.strip(' #*-') for l in result.splitlines() if l.strip() and not l.startswith(('#','Collected at','Deliverables:','---','Internal handoff'))]
        findings=' '.join(candidates[:3])[:650] or 'Review the actual result and linked deliverables below.'
        prompt=f'Review {identifier}: {issue["title"]}. '+findings[:500]
    if execution and execution.get('model_inference') is False:
        prompt += (' Coordinator step: HQ CPU / Python; see specialist receipts for their compute.' if 'orchestration' in execution.get('kind','').lower() else ' Compute: HQ CPU / Python; no model inference.')
    if not gaps:gaps.append('Check the stated scope, timestamps, missing access and any unverified claims in the evidence. Acceptance does not authorize infrastructure changes.')
    accepted='Accept discovery only' if network and logs_requested else 'Accept result'
    rejected='Request log verification' if network and logs_requested else 'Needs revision'
    decisions=(f'- **{accepted}:** acknowledge this result within its stated scope. This does not approve repairs or run new commands. Mark the task Done separately when you are satisfied.\n'
               f'- **{rejected}:** record what is missing and why. '+('Request authenticated log collection for named hosts; observer access is required.' if network and logs_requested else 'Specify the correction or additional evidence needed.')+'\n'
               '- Neither choice changes remote systems or automatically retries a failed operation.')
    details=('## Decision required\n\n'+prompt+'\n\n## Original request\n\n'+request[:2500]+
             '\n\n## Findings\n\n'+findings+'\n\n## Missing work and limits\n\n'+'\n'.join('- '+g for g in gaps)+
             '\n\n'+compute_markdown(execution)+'\n\n## What each choice means\n\n'+decisions+
             '\n\n## Result and evidence\n\n'+result+'\n\n[Open full task](/KRI/issues/'+identifier+')')
    return {'title':('Review '+identifier+': '+issue['title'])[:240], 'summary':findings[:1000],
            'payload':{'version':1,'prompt':prompt[:1000],'detailsMarkdown':details[:20000],
                       'acceptLabel':accepted,'rejectLabel':rejected,'rejectRequiresReason':True,'rejectReasonLabel':'What evidence or correction is still needed?'}}
