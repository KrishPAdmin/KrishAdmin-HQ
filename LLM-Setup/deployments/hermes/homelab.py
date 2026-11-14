"""Fixed owner-only Pi Swarm actions; credentials and arbitrary shell stay off tools."""
import concurrent.futures,hashlib,json,re,shlex,time,uuid
from pathlib import Path
from homelab_access import HOSTS,ROOT,kuma,run,target_name
STATE=ROOT/'state/homelab'
CATALOG={'nginx':{'image':'nginx:stable-alpine','port':80},'httpd':{'image':'httpd:2.4-alpine','port':80},'redis':{'image':'redis:7-alpine','port':6379}}
NODES={key:'KrishAdmin-HQ-Pi-Cluster-0'+str(i) for i,key in enumerate(HOSTS,1)}

def checked(target,command,timeout=25):
    result=run(target,command,timeout)
    if result['exit_code']:raise RuntimeError('Remote operation failed (exit '+str(result['exit_code'])+'); inspect current state before retry')
    return result['output']

def rows(command,fields):
    text=checked('Pi-Cluster-01',command)
    return [dict(zip(fields,line.split('|'))) for line in text.splitlines() if line]

def services():
    return rows("docker service ls --format '{{.ID}}|{{.Name}}|{{.Image}}|{{.Replicas}}'",['id','name','image','replicas'])

def nodes():
    return rows("docker node ls --format '{{.Hostname}}|{{.Status}}|{{.Availability}}|{{.ManagerStatus}}'",['hostname','status','availability','manager'])

def host_status(target):
    target=target_name(target)
    if target not in HOSTS:raise ValueError('Select Pi-Cluster-01, Pi-Cluster-02 or Pi-Cluster-03')
    script="""import json,os,shutil,socket
from pathlib import Path
mem={k:int(v.split()[0])*1024 for k,v in (line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())}
disk=shutil.disk_usage('/')
t=Path('/sys/class/thermal/thermal_zone0/temp')
print(json.dumps(dict(hostname=socket.gethostname(),uptime_seconds=float(Path('/proc/uptime').read_text().split()[0]),load_average=os.getloadavg(),memory_total_bytes=mem['MemTotal'],memory_available_bytes=mem.get('MemAvailable'),root_disk_total_bytes=disk.total,root_disk_free_bytes=disk.free,temperature_celsius=int(t.read_text())/1000 if t.exists() else None)))"""
    try:
        data=json.loads(checked(target,'python3 -c '+shlex.quote(script)))
        data.update(target=target,address=HOSTS[target],status='observed')
        return data
    except Exception as error:return {'target':target,'address':HOSTS[target],'status':'unavailable','reason':type(error).__name__}

def snapshot():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        hosts=list(pool.map(host_status,HOSTS))
    result={'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'hosts':hosts}
    for key,collect in [('swarm_nodes',nodes),('swarm_services',services),('uptime_kuma',kuma)]:
        try:result[key]=collect()
        except Exception as error:result[key]={'status':'unavailable','reason':type(error).__name__}
    return result

def save(p):
    STATE.mkdir(parents=True,exist_ok=True);path=STATE/(p['id']+'.json')
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(p,indent=2)+'\n');temp.chmod(0o600);temp.replace(path)

def preview(p):return {k:v for k,v in p.items() if k not in ('owner',)}

def load(pid,owner):
    if not isinstance(pid,str) or not re.fullmatch('[a-f0-9]{20}',pid):raise ValueError('Invalid proposal ID')
    p=json.loads((STATE/(pid+'.json')).read_text())
    if p['owner']!=owner:raise PermissionError('Proposal belongs to another owner')
    return p

def contains(message,value):return bool(re.search(r'(?<![\w.-])'+re.escape(value)+r'(?![\w.-])',message,re.I))

def authorized(p,message):
    # An explicit natural-language request can authorize its exact prepared action.
    # Otherwise the owner may send the concrete apply instruction returned in preview.
    if re.fullmatch(r'homelab\s+apply\s+'+p['id']+r'\s+'+p['digest'][:12],re.sub(r'<@!?\d+>','',message).strip(),re.I):return True
    if re.search(r'\b(?:do not|don.t|never|without)\b|\b(?:plan|preview|explain|example|how|could|would|if)\b',message,re.I):return False
    if p['action']=='restart':return bool(re.search(r'\brestart\b',message,re.I) and contains(message,p['service']))
    target=contains(message,p['target']) or contains(message,HOSTS[target_name(p['target'])])
    return bool(target and contains(message,p['app']) and re.search(r'\b(?:install|deploy|set up)\b',message,re.I) and (p['published_port'] is None or contains(message,str(p['published_port']))))

def execute(body,owner,message,db=None):
    if not isinstance(body,dict) or set(body)-{'_service','action','target','service','app','published_port','proposal_id','enabled'}:raise ValueError('Unknown homelab fields')
    if body.get('_service')!='homelab':raise PermissionError('Signed homelab request required')
    action=body.get('action')
    if action=='status':return snapshot()
    if action=='dashboard':return kuma()
    if action=='host':return host_status(body.get('target'))
    if action=='services':return {'nodes':nodes(),'services':services()}
    if action=='catalog':return {'apps':CATALOG,'scope':'One replica on selected Pi, 0.5 CPU and 256 MiB limit, nonprivileged, no host mounts, no host networking. Redis is ephemeral and has no published port. Other apps can optionally publish an explicitly requested port >=1024. Broader setups require a separate reviewed operation.'}
    if action=='watch':
        if type(body.get('enabled')) is not bool:raise ValueError('enabled must be boolean')
        if not re.search(r'\b(?:updates|notifications|watch|monitoring)\b',message,re.I):raise PermissionError('Explicit owner request for monitoring updates required')
        disabling=bool(re.search(r'\b(?:stop|disable|off|pause)\b',message,re.I))
        if disabling==body['enabled']:raise PermissionError('Requested monitoring state does not match owner message')
        (STATE/'watch.json').write_text(json.dumps({'enabled':body['enabled'],'owner':owner})+'\n')
        return {'enabled':body['enabled'],'interval_seconds':60,'delivery':'Owner DM on status changes; initial snapshot establishes baseline'}
    if action=='proposal':return preview(load(body.get('proposal_id'),owner))
    if action=='apply':
        p=load(body.get('proposal_id'),owner)
        if p['status']!='prepared':return preview(p)|{'instruction':'Do not repeat this operation; reconcile the current service state.'}
        if time.time()-p['created']>3600:raise ValueError('Proposal expired; prepare again')
        if not authorized(p,message):return preview(p)|{'authorization_required':True,'instruction':'Owner must explicitly request this exact change or send: homelab apply '+p['id']+' '+p['digest'][:12]}
        existing=services()
        if p['action']=='restart':
            if not any(s['id']==p['service_id'] and s['name']==p['service'] and s['image']==p['image'] for s in existing):raise ValueError('Service changed; prepare again')
        elif any(s['name']==p['name'] for s in existing):raise ValueError('Service name already exists; refusing duplicate deployment')
        p['status']='attempting';save(p) # Persist before dispatch; ambiguous outcomes never auto-retry.
        try:
            result=run('Pi-Cluster-01',p['command'],timeout=50)
            p.update(status='accepted' if result['exit_code']==0 else 'failed',exit_code=result['exit_code'])
        except Exception as error:p.update(status='uncertain',error=type(error).__name__)
        save(p)
        return preview(p)|{'services':services(),'limitation':'Accepted means Swarm accepted the request; inspect replicas/health before claiming the application is ready.'}
    if action not in ('prepare_restart','prepare_deploy'):raise ValueError('Unsupported homelab action')
    p={'id':uuid.uuid4().hex[:20],'owner':owner,'created':time.time(),'status':'prepared'}
    if action=='prepare_restart':
        service=body.get('service');row=next((s for s in services() if s['name']==service),None)
        if not row:raise ValueError('Select an exact existing Swarm service name from services')
        p.update(action='restart',service=service,service_id=row['id'],image=row['image'],command='docker service update --force --detach=true '+shlex.quote(service),impact='Rolling replacement of this service tasks; brief service interruption is possible. Existing service configuration and mounts are retained.')
    else:
        app=body.get('app');target=target_name(body.get('target'));port=body.get('published_port')
        if app not in CATALOG or target not in HOSTS:raise ValueError('Select a catalog app and enrolled target')
        if port is not None and (type(port)!=int or not 1024<=port<=65535):raise ValueError('Published port must be 1024–65535 or absent')
        if app=='redis' and port is not None:raise ValueError('Redis is internal-only; no unauthenticated host port')
        image=CATALOG[app]['image']
        extract="import json,sys; x=json.load(sys.stdin); print(json.dumps([{'Descriptor':m.get('Descriptor',{})} for m in (x if isinstance(x,list) else [x])]))"
        manifest=json.loads(checked('Pi-Cluster-01','docker manifest inspect --verbose '+shlex.quote(image)+' | python3 -c '+shlex.quote(extract),timeout=40))
        candidates=manifest if isinstance(manifest,list) else [manifest]
        descriptor=next((m['Descriptor'] for m in candidates if m.get('Descriptor',{}).get('platform',{}).get('architecture')=='arm64' and m.get('Descriptor',{}).get('platform',{}).get('os')=='linux'),None)
        if not descriptor or not re.fullmatch('sha256:[a-f0-9]{64}',descriptor.get('digest','')):raise ValueError('No verified Linux ARM64 image manifest')
        pinned=image.split(':')[0]+'@'+descriptor['digest'];name='hqbot-'+app+'-'+p['id'][:8]
        args=['docker','service','create','--detach=true','--name',name,'--label','hq.managed=true','--label','hq.proposal='+p['id'],'--replicas','1','--constraint','node.hostname=='+NODES[target],'--limit-cpu','0.5','--limit-memory','256m','--restart-condition','on-failure']
        if port is not None:args+=['--publish',f'published={port},target={CATALOG[app]["port"]},protocol=tcp,mode=host']
        args+=[pinned]
        p.update(action='deploy',app=app,target=target,name=name,image=pinned,published_port=port,command=shlex.join(args),impact='New isolated Swarm service. No host files or existing services changed. No persistent storage; data may be lost when its task is replaced. Published port, if selected, binds on the target Pi.')
    p['digest']=hashlib.sha256(json.dumps(p,sort_keys=True).encode()).hexdigest();save(p)
    return preview(p)|{'apply_instruction':'If the current owner message explicitly requests this exact change, call apply. Otherwise present this plan and ask for: homelab apply '+p['id']+' '+p['digest'][:12]}
