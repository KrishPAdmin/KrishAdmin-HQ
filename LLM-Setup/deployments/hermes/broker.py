"""HQ-only collection and inference relay. No model-selected shell or remote tools."""
import concurrent.futures, datetime, fcntl, hashlib, hmac, html, http.client
import ipaddress, json, os, re, socket, sqlite3, ssl, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import urllib.request
from health_rules import assess,age_seconds
from capabilities import TASKS,prompt_for,calculate
from team import TEAM
from web_research import collect as collect_web,search_web,read_page,weather
from task_updates import issue_url,origin_checked,subscribe

STATE = Path('/state')
TOKENS = Path('/run/access')
BACKENDS = {
    'nvidia-gpu': ('https://192.0.2.181:11434', '/run/secrets/nvidia-gpu-token', '/run/secrets/nvidia-gpu-ca.crt', 'qwen3.5:9b'),
    'amd-gpu': ('http://198.51.100.202:11434', '/run/secrets/amd-gpu-token', None, 'qwen2.5:72b-instruct-q8_0'),
}
ROLES = {'concierge': 'nvidia-gpu', 'health': 'nvidia-gpu', 'backup': 'nvidia-gpu', 'triage': 'nvidia-gpu', 'analyst': 'amd-gpu', 'operator': 'nvidia-gpu', 'paperclip': 'nvidia-gpu'}
ROLES.update({name:role['backend'] for name,role in TEAM.items()})
AUDIT_LOCK = threading.Lock()

def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
def audit(event, **values):
    record = {'time': now(), 'event': event, 'executor': 'HQ gateway 192.0.2.180', **values}
    with AUDIT_LOCK:
        with (STATE/'audit.jsonl').open('a') as f: f.write(json.dumps(record)+'\n')
    return record

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): raise ValueError('Redirect refused')

def request(url, body=None, token=None, ca=None, timeout=240):
    ctx = ssl.create_default_context(cafile=ca)
    client = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=ctx))
    req = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type':'application/json', **({'Authorization':'Bearer '+token} if token else {})})
    with client.open(req, timeout=timeout) as res:
        raw = res.read(2_000_001)
        if len(raw)>2_000_000: raise ValueError('Response too large')
        return json.loads(raw)

def gpu(name):
    url, secret, ca, model = BACKENDS[name]
    start = time.monotonic()
    try:
        data = request(url+'/api/tags', token=Path(secret).read_text().strip(), ca=ca, timeout=12)
        loaded=request(url+'/api/ps',token=Path(secret).read_text().strip(),ca=ca,timeout=12).get('models',[])
        return {'system':name, 'status':'reachable', 'models':[m['name'] for m in data['models']],
            'loaded_models':[{k:m.get(k) for k in ('name','size','size_vram','context_length')} for m in loaded],
            'acceleration':'gpu_residency_reported' if any(m.get('size_vram',0)>0 for m in loaded) else 'cpu_only' if loaded else 'no_model_loaded',
            'seconds':round(time.monotonic()-start,3)}
    except Exception as e: return {'system':name, 'status':'unavailable', 'reason':type(e).__name__}

def evidence(kind):
    result = {'collected_at':now(), 'collector':'HQ gateway 192.0.2.180', 'kind':kind}
    if kind in ('health','triage'):
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool: result['gpu_api'] = list(pool.map(gpu, BACKENDS))
        try:
            snapshot=json.loads(Path('/observations/host-health.json').read_text())
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(snapshot['checked_at_utc'])).total_seconds()
            # Only bounded structured status; raw logs and full command output stay local.
            hosts={'hq':snapshot['hq']}
            hosts.update({k:v['data'] for k,v in snapshot.get('remote_hosts',{}).items() if v.get('status')=='observed'})
            result['hosts']={k:{x:v.get(x) for x in ('root_disk','memory','load_average')} for k,v in hosts.items()}
            result['snapshot_status']='fresh' if 0<=age<=600 else 'stale'
            result['snapshot_age_seconds']=round(age)
            result['host_telemetry']={'hq':{'status':'observed'}}
            result['host_telemetry'].update({k:{'status':v['status'],
                **({'reason':v.get('reason','Not collected')} if v['status']!='observed' else {})}
                for k,v in snapshot.get('remote_hosts',{}).items()})
            result['coverage']={k:('host_telemetry_observed' if v['status']=='observed' else 'host_telemetry_unavailable')
                for k,v in snapshot.get('remote_hosts',{}).items()}
        except Exception: result['snapshot_status']='unavailable'
    if kind in ('backup','health','triage'):
        try:
            result['backups']=json.loads(Path('/backup-observations/backup-status.json').read_text())
            age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(result['backups']['checked_at_utc'])).total_seconds()
            result['backups']['metadata_status']='fresh' if 0<=age<=600 else 'stale'
            result['backups']['metadata_age_seconds']=round(age)
        except Exception: result['backups']={'status':'unavailable'}
    result['limitations']='Report GPU API status separately from host telemetry coverage. A reachable AMD-GPU API must not be labelled unavailable because host telemetry is unavailable. GPU memory residency does not prove active inference. Backup file presence is not a successful restore; database restore validation is not full application recovery. Missing/stale evidence remains unknown.'
    if kind in ('health','triage'):result['assessment']=assess(result)
    if kind in ('health','triage'):
        try:
            history=json.loads((STATE/'monitor.json').read_text())
            age=age_seconds(history.get('checked_at'),datetime.datetime.now(datetime.timezone.utc))
            result['monitor_history']={'checked_at':history.get('checked_at'),
                'status':'fresh' if age is not None and 0<=age<=600 else 'stale',
                'collection_status':history.get('collection_status'),'recent_changes':history.get('events',[])[-8:]}
        except (OSError,ValueError):result['monitor_history']={'status':'not_collected'}
    result['evidence_sha256']=digest(result)
    audit('collection', kind=kind, evidence_sha256=result['evidence_sha256'])
    return result

def validate_inference(role, body):
    if role not in ROLES: raise PermissionError('Unknown identity')
    backend=ROLES[role]
    allowed_model=TEAM[role]['model'] if role in TEAM else BACKENDS[backend][3]
    # The concierge may send a tool-free history summary to Jessica's 64K model.
    # Actual tool selection remains NVIDIA-GPU; no tool schemas or execution run on AMD-GPU.
    if role=='concierge' and body.get('model')==TEAM['jessica']['model']:
        backend='amd-gpu';allowed_model=TEAM['jessica']['model']
    if body.get('model')!=allowed_model: raise PermissionError('Model not permitted for this identity')
    messages=body.get('messages')
    if not isinstance(messages,list) or not messages or len(messages)>2000: raise ValueError('Invalid messages')
    if len(json.dumps(messages).encode())>600000: raise ValueError('Request exceeds the 600000-byte transport limit; compact history or split the source')
    if (backend=='amd-gpu' or role in TEAM) and (body.get('tools') or body.get('functions') or any(m.get('role') in ('tool','function') or m.get('tool_calls') for m in messages)):
        raise PermissionError('AMD-GPU is evidence-only; tools and tool execution transcripts are prohibited')
    if backend=='nvidia-gpu':
        names={t.get('function',{}).get('name') for t in body.get('tools',[])}
        if names-{'hq_status','hq_task','hq_research','hq_analyze','hq_files','hq_knowledge','hq_draft','hq_team','hq_calculate','hq_diagnostics','hq_github',
                  'mcp__research__search','mcp__research__read_page','mcp__research__weather','mcp__workbench__check_system','mcp__workbench__review_file','mcp__workbench__plan_automation'}: raise PermissionError('Tool outside HQ allowlist')
    return backend

def inference(role, body):
    backend=validate_inference(role,body)
    url, secret, ca, model=BACKENDS[backend]
    model=body['model']
    messages=json.loads(json.dumps(body['messages']))
    for message in messages:
        if message.get('content') is None:message['content']=''
        for call in message.get('tool_calls') or []:
            args=call.get('function',{}).get('arguments')
            if isinstance(args,str):call['function']['arguments']=json.loads(args)
    native={'model':model,'messages':messages,'stream':False,
        'options':{'temperature':0.1,'num_ctx':context_length(model,backend),'num_predict':min(4096 if role=='concierge' and backend=='amd-gpu' else 1800,int(body.get('max_tokens') or body.get('max_completion_tokens') or 1200))}}
    if backend=='nvidia-gpu': native['think']=False
    if body.get('tools'): native['tools']=body['tools']
    start=time.monotonic(); rid=str(uuid.uuid4())
    with Path('/locks',backend+'.lock').open('a') as lock:
        while True:
            try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB); break
            except BlockingIOError:
                if time.monotonic()-start>180: raise TimeoutError('GPU queue deadline')
                time.sleep(.25)
        queued=time.monotonic()-start
        loaded=request(url+'/api/ps',token=Path(secret).read_text().strip(),ca=ca,timeout=10).get('models',[])
        if any(m.get('name')==model and not m.get('size_vram',0)>0 for m in loaded):
            audit('inference_denied',identity=role,backend=backend,reason='model loaded on CPU; GPU recovery required')
            raise ValueError('Model is loaded on CPU; GPU recovery required')
        response=request(url+'/api/chat',native,Path(secret).read_text().strip(),ca,timeout=min(420,max(10,450-queued)))
        residency=request(url+'/api/ps',token=Path(secret).read_text().strip(),ca=ca,timeout=10)
        resident=next((m for m in residency.get('models',[]) if m.get('name')==model),{})
    message=response.get('message',{})
    if backend=='amd-gpu' and message.get('tool_calls'): raise PermissionError('AMD-GPU attempted a tool call; never executed')
    if not response.get('done') or response.get('done_reason')=='length': raise ValueError('Incomplete inference')
    receipt=audit('inference',request_id=rid,identity=role,backend=backend,model=model,
        prompt_sha256=digest(body['messages']), tool_count=len(native.get('tools',[])),
        queue_seconds=round(queued,3),seconds=round(time.monotonic()-start,3),
        input_tokens=response.get('prompt_eval_count'),output_tokens=response.get('eval_count'),
        loaded_bytes=resident.get('size'),vram_bytes=resident.get('size_vram'),context_length=resident.get('context_length'),
        load_seconds=round((response.get('load_duration') or 0)/1e9,3),
        generation_seconds=round((response.get('eval_duration') or 0)/1e9,3),
        generation_tokens_per_second=round((response.get('eval_count') or 0)/max((response.get('eval_duration') or 1)/1e9,.001),2),
        tool_executor='HQ only' if backend=='nvidia-gpu' else 'none; inference only')
    if not resident.get('size_vram',0)>0:raise ValueError('GPU acceleration not confirmed; completion withheld')
    if message.get('tool_calls'):
        for item in message['tool_calls']:
            item['id']='call_'+uuid.uuid4().hex[:20];item['type']='function'
            if not isinstance(item['function'].get('arguments'),str): item['function']['arguments']=json.dumps(item['function'].get('arguments',{}))
    return {'id':rid,'object':'chat.completion','created':int(time.time()),'model':model,
        'hq_receipt':{'run_id':rid,'backend':backend,'model':model,'context_length':receipt['context_length'],'input_tokens':receipt['input_tokens'],'output_tokens':receipt['output_tokens'],'vram_bytes':receipt['vram_bytes'],'time':receipt['time']},
        'choices':[{'index':0,'message':message,'finish_reason':'tool_calls' if message.get('tool_calls') else 'stop'}],
        'usage':{'prompt_tokens':receipt['input_tokens'] or 0,'completion_tokens':receipt['output_tokens'] or 0,
                 'total_tokens':(receipt['input_tokens'] or 0)+(receipt['output_tokens'] or 0)}}

def context_length(model,backend):
    if backend=='nvidia-gpu' or model==TEAM['jessica']['model']:return 65536
    if model in (BACKENDS['amd-gpu'][3],TEAM['louis']['model']):return 32768
    return 8192

def specialist_budget(name):
    return {'jessica':56000,'louis':24000,'harvey':6000}.get(name,24000)

def research(urls):
    """Fixed public origins, pinned DNS result, TLS verification, no redirects or cookies."""
    allowed=set(json.loads(Path('/config/research-origins.json').read_text()))
    if not isinstance(urls,list) or not 1<=len(urls)<=3: raise ValueError('Supply 1–3 URLs')
    sources=[]
    for url in urls:
        p=urlsplit(url)
        if p.scheme!='https' or p.hostname not in allowed or p.port not in (None,443) or p.username or p.password or p.fragment:
            raise PermissionError('Research origin is not approved')
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses): raise PermissionError('Non-public research address')
        chosen=addresses[0];host=p.hostname
        class PinnedHTTPS(http.client.HTTPSConnection):
            def connect(self):
                sock=socket.socket(chosen[0],chosen[1],chosen[2]);sock.settimeout(20);sock.connect(chosen[4])
                self.sock=self._context.wrap_socket(sock,server_hostname=host)
        conn=PinnedHTTPS(host,timeout=20,context=ssl.create_default_context())
        try:
            conn.request('GET',p.path or '/',headers={'User-Agent':'KrishAdmin-HQ-Research/1.0','Accept':'text/plain,text/html','Accept-Encoding':'identity'}) if not p.query else conn.request('GET',(p.path or '/')+'?'+p.query,headers={'User-Agent':'KrishAdmin-HQ-Research/1.0','Accept-Encoding':'identity'})
            res=conn.getresponse()
            if res.status!=200: raise ValueError('Research returned HTTP '+str(res.status))
            if not any(t in res.getheader('Content-Type','') for t in ('text/','application/json')): raise ValueError('Unsupported research media')
            raw=res.read(500001)
            if len(raw)>500000: raise ValueError('Research document too large')
            text=raw.decode('utf-8',errors='replace')
            text=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
            main=re.search(r'<main\b[^>]*>(.*?)</main>',text,flags=re.S|re.I)
            if main:text=main.group(1)
            text=re.sub(r'<(nav|header|footer)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
            text=html.unescape(re.sub('<[^>]+>',' ',text));text=re.sub(r'\s+',' ',text).strip()
            excerpt=text.encode('utf-8')[:3600//len(urls)].decode('utf-8',errors='ignore')
            sources.append({'url':url,'fetched_at':now(),'collector':'HQ gateway 192.0.2.180',
                'body_sha256':hashlib.sha256(raw).hexdigest(),'excerpt':excerpt,'truncated':len(excerpt)<len(text)})
        finally: conn.close()
    packet={'sources':sources,'collector':'HQ gateway 192.0.2.180'}
    packet['evidence_sha256']=digest(packet)
    audit('research',urls=urls,evidence_sha256=packet['evidence_sha256'],source_hashes=[s['body_sha256'] for s in sources])
    return packet

def run_worker(kind, packet, question, task_kind=None):
    if kind not in ('health','backup','triage','analyst'): raise ValueError('Unknown worker')
    if len(question)>4000:raise ValueError('Question exceeds 4000 characters; shorten it explicitly')
    if kind=='analyst':prompt_for(task_kind or 'research',question,packet)
    return request('http://'+kind+':8080/run',{'question':question,'evidence':packet,'task_kind':task_kind or 'research'},
        TOKENS.joinpath('worker').read_text().strip(),timeout=520)

def uploaded(body):
    return request('http://files:8080/files',body,TOKENS.joinpath('worker').read_text().strip(),timeout=30)

def analysis_packet(body):
    kind=body.get('kind','plan');question=body.get('question','')
    if kind not in TASKS or not isinstance(question,str) or not question.strip():raise ValueError('Choose a supported analysis kind and provide a question')
    if kind in ('health','backup','triage'):packet=evidence(kind)
    else:
        text=body.get('text','')
        if not isinstance(text,str) or len(text.encode('utf-8'))>50000:raise ValueError('Supplied text exceeds 50000 bytes; use a smaller excerpt')
        packet={'kind':kind,'collected_at':now(),'text':text}
    if body.get('file_id'):
        file=uploaded({'action':'read','file_id':body['file_id'],'offset':body.get('offset',0),'limit':body.get('limit',3000)})
        packet['file']={k:file[k] for k in ('file_id','sha256','extraction_truncated','extracted_characters')}
        packet['text']=file['text']
        packet['reviewed_span']={'offset':file['offset'],'characters':len(file['text']),'next_offset':file['next_offset']}
        packet['validation']=uploaded({'action':'validate','file_id':body['file_id']})['validation']
    packet['evidence_sha256']=digest(packet)
    return kind,question,packet

def analyze(body):
    kind,question,packet=analysis_packet(body)
    if len(json.dumps(packet,ensure_ascii=False).encode())+len(question.encode())>20000:
        prompt_for(kind,question,packet,max_bytes=56000)
        result=request('http://jessica:8080/run',{'question':question,'evidence':packet,'task_kind':kind},TOKENS.joinpath('worker').read_text().strip(),timeout=520)
    else:result=run_worker('analyst',packet,question,kind)
    if body.get('file_id'):
        audit('file_analysis',file_sha256=packet['file']['sha256'],validation_status=packet['validation']['status'],run_id=result['run_id'],backend=result['backend'],reviewed_span=packet['reviewed_span'])
    return {'compute_receipt':result.get('compute_receipt',{'run_id':result.get('run_id'),'backend':result.get('backend'),'model':result.get('model')}),
            'analysis':result,'evidence':packet,'compute':'AMD-GPU; tools and file handling remain on HQ'}

def research_request(body):
    question=body.get('question') or body.get('query')
    if not isinstance(question,str) or not question.strip():raise ValueError('A research question is required')
    packet=collect_web(body.get('query') or question,body.get('urls'))
    packet['research_status']=packet['status']
    packet['search_summary']={k:v for k,v in packet['search'].items() if k!='results'}
    if not packet['sources']:
        audit('web_research',status=packet['status'],evidence_sha256=packet['evidence_sha256'])
        return {'evidence':packet,'analysis':None,'status':'research_incomplete','reason':'No readable sources collected; use search/read tools or a supplied public source URL. Do not guess an answer.'}
    for attempt in range(12):
        try:prompt_for('research',question,packet);break
        except ValueError as error:
            if 'prompt budget' not in str(error):raise
            source=max(packet['sources'],key=lambda s:len(s['excerpt'].encode()))
            if len(source['excerpt'].encode())<=200:raise
            source['excerpt']=source['excerpt'].encode()[:max(200,int(len(source['excerpt'].encode())*.8))].decode('utf-8',errors='ignore');source['truncated']=True
    packet['evidence_sha256']=digest({k:v for k,v in packet.items() if k!='evidence_sha256'})
    result=run_worker('analyst',packet,question,'research')
    audit('web_research',status=packet['status'],backend=result['backend'],run_id=result['run_id'],urls=[s['url'] for s in packet['sources']],evidence_sha256=packet['evidence_sha256'])
    return {'evidence':packet,'analysis':result,'status':'completed','workflow':'HQ search and source retrieval -> AMD-GPU analysis'}

def workbench(body):
    """Repeatable evidence workflows; never run model-selected commands."""
    action=body.get('action')
    if action=='review_file':
        if not body.get('file_id'):raise ValueError('An uploaded file_id is required')
        result=analyze({'kind':body.get('kind','code_review'),'question':body.get('question') or 'Review this file for concrete issues and propose fixes. State the coverage of this slice.',
                        'file_id':body['file_id'],'offset':body.get('offset',0),'limit':3000})
        return {**result,'validation':result['evidence']['validation'],'next_offset':result['evidence']['reviewed_span']['next_offset'],'workflow':'HQ extraction and syntax validation -> AMD-GPU review','executed_code':False}
    if action=='plan_automation':
        result=team_request({'action':'delegate','agent':'louis','kind':'automation','question':body.get('question',''),'text':body.get('text','')})
        result['artifact']=draft({'title':'automation-plan','extension':'md','content':result['analysis']['text']})
        result['status']='draft_only_not_executed'
        return result
    if action!='check_system':raise ValueError('Unknown workbench operation')
    target=body.get('target');checks=body.get('checks') or ['overview','gpu']
    if target not in ('hq','nvidia-gpu','amd-gpu') or not isinstance(checks,list) or not 1<=len(checks)<=3 or any(c not in ('overview','gpu','processes','services','storage') for c in checks):raise ValueError('Select one enrolled target and 1–3 fixed checks')
    results=[]
    for check in dict.fromkeys(checks):
        try:result=diagnostics({'target':target,'check':check})
        except Exception as error:result={'target':target,'check':check,'status':'unavailable','error_type':type(error).__name__}
        # Preserve per-command failures and evidence hashes, while limiting raw output.
        summary={k:result[k] for k in ('target','check','checked_at_utc','status','reason','evidence_sha256') if k in result}
        summary['checks']={}
        for name,value in result.get('checks',{}).items():
            if not isinstance(value,dict):continue
            item={k:value[k] for k in ('status','exit_code','sample_seconds','reason') if k in value}
            if 'rows' in value:item['rows']=value['rows'][:5];item['rows_omitted']=max(0,len(value['rows'])-5)
            if 'output' in value:item['output_excerpt']=value['output'][:350];item['truncated']=value.get('truncated',False) or len(value['output'])>350
            summary['checks'][name]=item
        results.append(summary)
    text=json.dumps(results,ensure_ascii=False,separators=(',',':'))
    # A large bundle remains available to the user; do not silently feed partial JSON to the model.
    if len(text.encode())>4200:
        for result in results:
            for item in result['checks'].values():
                if 'output_excerpt' in item:item['output_excerpt']=item['output_excerpt'][:100];item['truncated']=True
                if 'rows' in item:item['rows']=item['rows'][:3];item['rows_omitted']='only first 3 retained'
        text=json.dumps(results,ensure_ascii=False,separators=(',',':'))
    question=body.get('question') or 'Interpret these fresh fixed diagnostic checks. Separate confirmed issues, unavailable checks, and next steps. CPU activity is not GPU inference proof.'
    result=analyze({'kind':'diagnostics','question':question,'text':text})
    return {**result,'checks':results,'workflow':'HQ fixed diagnostics -> AMD-GPU analysis','changes_made':False,'limitations':'Measurements precede the analysis run. No complete health, thermal-throttling, memory-leak or safe-temperature certification. No thresholds were supplied. Counters with unspecified units are opaque; do not compare them with percent utilization.'}

def team_request(body):
    body=dict(body)
    if not body.get('action'):body['action']='delegate' if body.get('agent') else 'roster'
    if body['action']=='delegate' and not body.get('question') and body.get('search_query'):
        body['question']=body['search_query']
    if body['action']=='roster':
        return {'agents':{name:{k:v for k,v in role.items() if k!='persona'} for name,role in TEAM.items()},
                'coordinator':'Donna persona in the Hermes Discord gateway on HQ; tool calls and delegation stay on HQ',
                'approval':'The human operator authorizes production changes.'}
    if body.get('action')!='delegate' or body.get('agent') not in TEAM:raise ValueError('Choose roster or delegate to a named team member')
    name=body['agent']
    if body.get('delegate_to'):
        if name!='jessica' or body['delegate_to']!='rachel':raise ValueError('Supported managed research workflow: Jessica delegates to Rachel')
        question=body.get('question','')
        if not isinstance(question,str) or not question.strip():raise ValueError('A research question or search_query is required; no delegation was performed')
        brief=team_request({'action':'delegate','agent':'jessica','kind':'plan','question':'Write a research brief for Rachel in at most 100 words. Do not answer the factual question or invent findings. Request: '+question})
        result=team_request({'action':'delegate','agent':'rachel','kind':'research','question':question,'search_query':body.get('search_query') or question,'urls':body.get('urls'),'manager_brief':brief['analysis']['text']})
        result['manager']=brief['analysis'];result['workflow']='Jessica research brief -> HQ web search/source fetch -> Rachel analysis';return result
    kind,question,packet=analysis_packet(body)
    if body.get('urls'):
        if name!='rachel':raise ValueError('Source fetching is assigned to Rachel; other agents can analyze the supplied source text')
        packet=collect_web(body.get('search_query') or question,body['urls']);kind='research'
    elif name=='rachel' and (kind=='research' or not body.get('text') and not body.get('file_id')):
        packet=collect_web(body.get('search_query') or question);kind='research'
    if name=='rachel' and kind=='research' and 'search' in packet:
        packet['research_status']=packet['status'];packet['search_summary']={k:v for k,v in packet['search'].items() if k!='results'}
        if body.get('manager_brief'):
            brief=body['manager_brief'];excerpt=brief.encode()[:500].decode('utf-8',errors='ignore')
            packet['manager_brief']={'excerpt':excerpt,'truncated':len(excerpt)<len(brief)}
        # Source excerpts and generated briefs may be shortened explicitly; never trim the user's question.
        for attempt in range(8):
            try:prompt_for(kind,question,packet);break
            except ValueError as error:
                if 'prompt budget' not in str(error) or not packet['sources']:raise
                source=max(packet['sources'],key=lambda s:len(s['excerpt'].encode()))
                if len(source['excerpt'].encode())<=400:raise
                source['excerpt']=source['excerpt'].encode()[:max(400,int(len(source['excerpt'].encode())*.8))].decode('utf-8',errors='ignore');source['truncated']=True
        packet['evidence_sha256']=digest({k:v for k,v in packet.items() if k!='evidence_sha256'})
        audit('web_research',status=packet['status'],search_status=packet['search']['status'],urls=[s['url'] for s in packet['sources']],evidence_sha256=packet['evidence_sha256'])
        if not packet['sources']:
            return {'evidence':packet,'analysis':None,'status':'research_incomplete','reason':'No readable sources collected. Do not report completed research or guess an answer.'}
    prompt_for(kind,question,packet,max_bytes=specialist_budget(name))
    if name=='mike' and body.get('compute')=='amd-gpu':
        result=run_worker('analyst',packet,'As Mike, handle this escalation: '+question,kind)
        result['agent']='mike';result['escalated']=True
    else:
        result=request('http://'+name+':8080/run',{'question':question,'evidence':packet,'task_kind':kind},TOKENS.joinpath('worker').read_text().strip(),timeout=520)
    audit('delegation',agent=name,backend=result['backend'],model=result['model'],run_id=result['run_id'],evidence_sha256=packet['evidence_sha256'])
    return {'evidence':packet,'analysis':result}

KNOWLEDGE={'index','quickstart','architecture','operations','monitoring','discord','backups','security','troubleshooting','recovery','reference','acceptance','capabilities','diagnostics','github','mcp'}
def knowledge(body):
    section=body.get('section');query=body.get('query','')
    if section:
        if section not in KNOWLEDGE:raise ValueError('Unknown runbook section')
        path=Path('/knowledge')/(section+'.md')
        if path.is_symlink():raise ValueError('Runbook symlink refused')
        offset=body.get('offset',0);limit=body.get('limit',16000)
        if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=16000:raise ValueError('Use offset >= 0 and limit 1–16000')
        text=path.read_text();chunk=text[offset:offset+limit]
        return {'section':section,'text':chunk,'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(text) else None,'truncated':offset>0 or offset+len(chunk)<len(text)}
    if not isinstance(query,str) or not 1<=len(query)<=160:raise ValueError('Supply a search query or section')
    matches=[];terms=query.lower().split()
    for name in sorted(KNOWLEDGE):
        path=Path('/knowledge')/(name+'.md')
        if not path.exists() or path.is_symlink():continue
        for paragraph in path.read_text().split('\n\n'):
            if all(term in paragraph.lower() for term in terms):matches.append({'section':name,'excerpt':paragraph[:1200]})
    return {'matches':matches[:8],'more_matches':len(matches)>8,'scope':'Maintained local runbooks only'}

def draft(body):
    extension=body.get('extension','md');content=body.get('content','');title=body.get('title','draft')
    if extension not in ('md','txt','py','sh','json','yaml','yml','js','ts','sql','csv'):raise ValueError('Unsupported draft extension')
    if not isinstance(content,str) or not content or len(content.encode('utf-8'))>100000:raise ValueError('Draft must contain 1–100000 UTF-8 bytes')
    if not isinstance(title,str):raise ValueError('Draft title must be text')
    for path in list(TOKENS.iterdir())+[Path('/run/secrets/nvidia-gpu-token'),Path('/run/secrets/amd-gpu-token')]:
        if path.is_file():
            secret=path.read_text().strip()
            if len(secret)>=16 and secret in content:raise PermissionError('Draft contains a protected local credential')
    name=re.sub(r'[^a-zA-Z0-9_-]','-',title)[:48] or 'draft'
    name=name+'-'+uuid.uuid4().hex[:12]+'.'+extension
    folder=Path('/drafts');folder.mkdir(exist_ok=True)
    with (folder/name).open('x',encoding='utf-8') as f:f.write(content)
    (folder/name).chmod(0o600)
    return {'name':name,'bytes':len(content.encode('utf-8')),'sha256':hashlib.sha256(content.encode()).hexdigest(),
        'delivery_path':'/profile/cache/documents/drafts/'+name,'status':'draft_only_not_executed'}

def compute_usage():
    from collections import deque
    rows=[]
    with (STATE/'audit.jsonl').open() as f:
        for line in deque(f,maxlen=5000):
            try:row=json.loads(line)
            except ValueError:continue
            if row.get('event')=='inference':rows.append(row)
    return {'scope':'Hermes relay inference receipts in the last 5000 audit records; not whole-host utilization',
        'routing':{'discord_coordination':'nvidia-gpu','specialist_analysis_default':'amd-gpu','explicit_fast_analysis':'nvidia-gpu','research_collection':'HQ'},
        'backends':{name:{'requests':len([r for r in rows if r.get('backend')==name]),
            'gpu_confirmed_requests':len([r for r in rows if r.get('backend')==name and (r.get('vram_bytes') or 0)>0]),
            'latest':[{k:r.get(k) for k in ('time','identity','model','seconds','input_tokens','output_tokens','vram_bytes','tool_count')} for r in rows if r.get('backend')==name][-3:]}
            for name in BACKENDS}}

def task(body):
    cfg=json.loads(Path('/config/paperclip.json').read_text())
    token=TOKENS.joinpath('paperclip-api').read_text().strip()
    def api(path,value=None):return request('http://server:3100/api'+path,value,token,timeout=30)
    origin=origin_checked(body.get('_discord_origin'),json.loads(Path('/discord-enrollment.json').read_text())) if body.get('_discord_origin') is not None else None
    with sqlite3.connect(STATE/'tasks.db',timeout=10) as db:
        db.execute('CREATE TABLE IF NOT EXISTS tasks (key TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, issue_id TEXT, identifier TEXT, state TEXT NOT NULL)')
        if body.get('action')=='status':
            row=db.execute('SELECT issue_id FROM tasks WHERE (issue_id=? OR identifier=?) AND state=?',(body.get('task_id'),body.get('task_id'),'created')).fetchone()
            if not row:raise PermissionError('Only tasks submitted by this bridge are visible')
            issue=api('/issues/'+row[0]);result={'task':issue['identifier'],'id':issue['id'],'status':issue['status'],'url':issue_url(issue['identifier'])}
            if body.get('include_result'):
                comments=api('/issues/'+row[0]+'/comments?order=desc&limit=5')
                comments=sorted((c for c in comments if c.get('authorAgentId') and not c.get('deletedAt')),key=lambda c:c.get('createdAt',''),reverse=True)
                if comments:
                    comment=comments[0];result['agent_comment']=comment.get('body','')[:12000];result['comment_id']=comment['id']
                    match=re.search(r'\[hermes-evidence\.json\]\(/api/attachments/([a-f0-9-]{36})/content\)',result['agent_comment'])
                    if match:
                        artifact=api('/attachments/'+match[1]+'/content')
                        # Structured collector/receipt fields only; no model text or uploaded content.
                        result['result_evidence']={'analysis':{k:artifact.get('analysis',{}).get(k) for k in ('backend','model','seconds','run_id')},
                            'evidence':{k:artifact.get('evidence',{}).get(k) for k in ('assessment','gpu_api','collected_at','snapshot_status')}}
            return result
        if body.get('action')!='submit' or body.get('kind') not in TASKS:raise ValueError('Invalid task operation')
        team_agent=body.get('agent')
        if team_agent is None and body['kind'] not in ('health','backup','triage'):
            team_agent={'code_review':'louis','config_review':'louis','automation':'louis','plan':'harvey','summarize':'mike','compare':'jessica','research':'rachel'}[body['kind']]
        if team_agent is not None and team_agent not in TEAM:raise ValueError('Unknown named agent')
        key=body.get('request_id','')
        if not re.fullmatch(r'[a-zA-Z0-9_:.\-]{8,160}',key):raise ValueError('Stable request ID required')
        description=str(body.get('description',''))
        if len(description)>4000:raise ValueError('Task description exceeds 4000 characters')
        payload_hash=digest([body['kind'],description,team_agent] if team_agent else [body['kind'],description])
        db.execute('BEGIN IMMEDIATE')
        prior=db.execute('SELECT payload_hash,issue_id,identifier,state FROM tasks WHERE key=?',(key,)).fetchone()
        if prior:
            if prior[0]!=payload_hash:raise ValueError('Request ID reused with different content')
            if prior[3]!='created':raise ValueError('Submission outcome uncertain; reconcile in Paperclip before retrying')
            watching=subscribe(db,prior[1],origin)
            return {'task':prior[2],'id':prior[1],'duplicate':True,'url':issue_url(prior[2]),'discord_updates':watching}
        db.execute('INSERT INTO tasks VALUES (?,?,NULL,NULL,?)',(key,payload_hash,'pending'));db.commit()
        # Persist reservation before network I/O. Ambiguous failures cannot create a second task.
        issue=api('/companies/'+cfg['company_id']+'/issues',{'title':'Hermes '+body['kind']+' request '+hashlib.sha256(key.encode()).hexdigest()[:10],'description':('[HQ task kind='+body['kind']+']\n' if team_agent else '')+description+'\n\n[HQ Hermes request '+key+']',
            'status':'todo','assigneeAgentId':cfg['team_agents'][team_agent] if team_agent else cfg['agents'][body['kind']],'projectId':cfg['project_id']})
        if '[HQ Hermes request '+key+']' not in (issue.get('description') or ''):raise ValueError('Paperclip reused a different task; reconcile before retrying')
        db.execute('UPDATE tasks SET issue_id=?,identifier=?,state=? WHERE key=?',(issue['id'],issue['identifier'],'created',key))
        watching=subscribe(db,issue['id'],origin);db.commit()
        audit('task_submitted',task=issue['identifier'],request_id=key)
        return {'task':issue['identifier'],'id':issue['id'],'duplicate':False,'url':issue_url(issue['identifier']),'discord_updates':watching}

def diagnostics(body):
    if not isinstance(body,dict) or set(body)-{'target','check'}:raise ValueError('Only target and check are accepted')
    if body.get('target') not in ('hq','nvidia-gpu','amd-gpu') or body.get('check','overview') not in ('overview','gpu','processes','services','storage'):raise ValueError('Unsupported diagnostic target or check')
    conn=http.client.HTTPConnection('localhost',timeout=50)
    sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.settimeout(50)
    try:
        sock.connect('/diagnostic-socket/check.sock');conn.sock=sock
        conn.request('POST','/diagnostics',json.dumps(body),{'Content-Type':'application/json','Authorization':'Bearer '+(TOKENS/'worker').read_text().strip()})
        response=conn.getresponse();raw=response.read(65001)
        if len(raw)>65000:raise ValueError('Diagnostic output exceeds limit')
        data=json.loads(raw)
        if response.status!=200:raise ValueError(data.get('error','Diagnostic service failed'))
        audit('diagnostics',target=body['target'],check=body.get('check','overview'),status=data.get('status'),evidence_sha256=data.get('evidence_sha256'))
        return data
    finally:conn.close();sock.close()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def send(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):
        if self.path=='/health': return self.send(200,{'status':'ok','collection_executor':'HQ','amd-gpu':'inference-only'})
        self.send(404,{'error':'not found'})
    def do_POST(self):
        try:
            auth=self.headers.get('Authorization','').removeprefix('Bearer ')
            role=next((r for r in ROLES if hmac.compare_digest(auth,TOKENS.joinpath(r).read_text().strip())),None)
            if not role: raise PermissionError('Authentication required')
            length=int(self.headers.get('Content-Length',0))
            if not 0<length<=768000: raise ValueError('Invalid body size')
            body=json.loads(self.rfile.read(length))
            if self.path=='/v1/chat/completions':
                value=inference(role,body)
                if not body.get('stream'): return self.send(200,value)
                # The upstream model is buffered to validate completion before publishing.
                message=value['choices'][0]['message']; delta={k:v for k,v in message.items() if k in ('role','content','tool_calls')}
                for i,t in enumerate(delta.get('tool_calls',[])):t['index']=i
                chunk={**value,'object':'chat.completion.chunk','choices':[{'index':0,'delta':delta,'finish_reason':None}]}
                tail={**value,'object':'chat.completion.chunk','choices':[{'index':0,'delta':{},'finish_reason':value['choices'][0]['finish_reason']}]}
                raw=('data: '+json.dumps(chunk)+'\n\ndata: '+json.dumps(tail)+'\n\ndata: [DONE]\n\n').encode()
                self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
            if role=='analyst' or role in TEAM: raise PermissionError('Specialist identities are inference-only; collection and delegation run on HQ coordinator')
            if self.path=='/diagnostics' and role=='paperclip':return self.send(200,diagnostics(body))
            if self.path=='/team' and role=='paperclip':return self.send(200,team_request(body))
            if role in ('concierge','operator'):
                if self.path=='/web/weather':return self.send(200,weather(body.get('location'),body.get('country_code')))
                if self.path=='/web/search':return self.send(200,search_web(body.get('query')))
                if self.path=='/web/read':return self.send(200,read_page(body.get('url'),body.get('offset',0),body.get('limit',4000),body.get('find')))
                if self.path=='/workbench':return self.send(200,workbench(body))
                if self.path=='/research':return self.send(200,research_request(body))
                if self.path=='/diagnostics':return self.send(200,diagnostics(body))
                if self.path=='/analyze':return self.send(200,analyze(body))
                if self.path=='/files':return self.send(200,uploaded(body))
                if self.path=='/knowledge':return self.send(200,knowledge(body))
                if self.path=='/draft':return self.send(200,draft(body))
                if self.path=='/compute':return self.send(200,compute_usage())
                if self.path=='/team':return self.send(200,team_request(body))
                if self.path=='/calculate':return self.send(200,calculate(body.get('expression')))
            if self.path=='/status': return self.send(200,evidence('health'))
            if self.path=='/task' and role in ('concierge','operator'):return self.send(200,task(body))
            if self.path=='/run' and role in ('operator','paperclip'):
                kind=body['kind']; packet=evidence(kind)
                if kind not in ('health','backup','triage'): raise PermissionError('Worker not allowed')
                compute=body.get('compute','amd-gpu')
                if compute not in ('nvidia-gpu','amd-gpu'):raise ValueError('Compute must be nvidia-gpu or amd-gpu')
                result=run_worker('analyst' if compute=='amd-gpu' else kind,packet,body.get('question','Report current evidence, uncertainty and recommended next steps.'),kind)
                return self.send(200,{'evidence':packet,'analysis':result})
            raise PermissionError('Operation not allowed')
        except PermissionError as e: self.send(403,{'error':str(e)})
        except (ValueError,KeyError,TypeError) as e: self.send(400,{'error':str(e)[:200]})
        except Exception as e:
            audit('failure',error_type=type(e).__name__,path=self.path)
            self.send(502,{'error':type(e).__name__})

if __name__=='__main__':
    STATE.mkdir(exist_ok=True);ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
