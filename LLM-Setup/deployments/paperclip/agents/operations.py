#!/usr/bin/env python3
"""Bounded observational operations. Task text cannot supply commands or targets."""
import concurrent.futures, datetime, ipaddress, json, os, socket, sys, time, uuid
from pathlib import Path
import local_agent

NETWORK = ipaddress.ip_network('192.0.2.0/24')
PORTS = (22,53,80,443,445,8006,8443,11434)

def now(): return datetime.datetime.now(datetime.timezone.utc)

def discover():
    def inspect(host):
        opened = []
        for port in PORTS:
            try:
                with socket.create_connection((str(host),port),timeout=.35): opened.append(port)
            except OSError: pass
        return {'address':str(host),'open_tcp_ports':opened} if opened else None
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        systems = [r for r in pool.map(inspect,NETWORK.hosts()) if r]
    return {'checked_at_utc':now().isoformat(),'network':str(NETWORK),'tcp_ports':list(PORTS),
            'systems':systems,'seconds':round(time.monotonic()-start,2),
            'limitations':'TCP connect discovery only. No reply does not prove a host is offline. No UDP, vulnerability checks or authentication attempts.'}

def snapshot(path=Path('/opt/hq-observations/host-health.json')):
    try:
        data = json.loads(path.read_text())
        age = (now()-datetime.datetime.fromisoformat(data['checked_at_utc'])).total_seconds()
        return {'status':'fresh' if 0 <= age <= 600 else 'stale','age_seconds':round(age),'data':data}
    except (OSError,ValueError,KeyError,TypeError):
        return {'status':'unavailable','reason':'Host snapshot missing or invalid; no host health claim can be made.'}

def gpu_health():
    sys.path.insert(0, "/opt/collectors")
    sys.path.insert(0, "/opt/worker")
    import cluster_health
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        systems = list(pool.map(cluster_health.inspect,cluster_health.TARGETS))
    return {'checked_at_utc':now().isoformat(),'systems':systems,
            'limitations':'API reachability and model residency only; no inference or hardware health is established.'}

def report(data):
    lines = ['# '+('Network discovery observations' if data.get('network') else 'System health observations'),'', 'Collected at '+data['checked_at_utc'], '']
    for system in data.get('gpu',{}).get('systems',[]):
        checks = system.get('checks',{})
        ok = len(checks)==2 and all(c.get('http_status')==200 and not c.get('error') for c in checks.values())
        lines.append('- GPU API '+system['system']+': '+('reachable' if ok else 'FAILED / incomplete'))
        for label,c in checks.items():
            lines.append('  - '+label+': '+(', '.join(m.get('name','unknown') for m in c.get('models',[])) or c.get('error','none loaded')))
    host = data.get('host',{})
    if host:
        lines.append('- Host snapshot: '+host['status']+'; age '+str(host.get('age_seconds','unknown'))+' seconds')
        hosts = [('hq', host.get('data',{}).get('hq',{}))]
        for name,value in host.get('data',{}).get('remote_hosts',{}).items():
            if value['status']=='observed': hosts.append((name,value['data']))
            else: lines.append('- '+name+' host diagnostics: UNKNOWN — '+value.get('reason','unavailable'))
        for name,observed in hosts:
            if not observed: continue
            disk = observed['root_disk']['used_percent']
            lines.append('- '+name+' root disk: '+str(disk)+'% used'+(' — WARNING: capacity above 85%' if disk>=85 else ''))
            memory = observed['memory']; total=memory.get('MemTotal_bytes',0)
            if total:
                available=round(100*memory.get('MemAvailable_bytes',0)/total,1)
                lines.append('- '+name+' memory available: '+str(available)+'%'+(' — WARNING: below 10%' if available<10 else ''))
            lines.append('- '+name+' load average: '+str(observed['load_average']))
            failed=observed.get('failed_services',{})
            if not failed.get('ok'): lines.append('- '+name+' failed-service check: UNKNOWN')
            elif failed.get('output','').strip(): lines.append('- '+name+' FAILED SERVICES: '+failed['output'].strip())
            else: lines.append('- '+name+' failed services: none observed')
            for vendor in ('nvidia','amd'):
                if vendor in observed:
                    value=observed[vendor]
                    lines.append('- '+name+' '+vendor+' metrics: '+(value.get('output','').strip() if value.get('ok') else 'UNKNOWN'))
            containers=observed.get('containers')
            if containers:
                lines += ['', '## '+name+' containers', '```text', containers.get('output','UNKNOWN').strip(), '```']
    network = data.get('network')
    if network:
        lines += ['', '## Network discovery',network['limitations']]
        lines += ['- '+s['address']+': TCP '+', '.join(map(str,s['open_tcp_ports'])) for s in network['systems']]
    if data.get('local_systems'):
        lines += ['', '## Configured local systems']
        lines += ['- '+x.get('name','Local system')+': '+x.get('status','unknown') for x in data['local_systems']]
    if data.get('execution'):
        from review_details import compute_markdown
        lines += ['',compute_markdown(data['execution'])]
    lines += ['', 'See attached JSON for measurements and limits. Observations do not authorize repairs. Missing or stale checks remain unknown.']
    return '\n'.join(lines)+'\n'

class OperationsAgent(local_agent.Agent):
    def require_active_run(self):
        try:
            active = self.api('GET', f'/heartbeat-runs/{self.run_id}').get('status') == 'running'
        except Exception:
            active = False
        if not active:
            # SystemExit bypasses generic failure handling: never mutate a cancelled task.
            raise SystemExit(2)

    def review(self, content):
        self.require_active_run()
        return super().review(content)

    def private_values(self):
        values = [os.environ.get('PAPERCLIP_API_KEY', '')]
        for name in ('nvidia-gpu-token', 'amd-gpu-token', 'pi-bridge-token'):
            path = Path('/run/secrets') / name
            if path.exists():
                values.append(path.read_text().strip())
        return [v for v in values if len(v) > 6]

    def infer(self,messages,schema=None):
        # Each invocation is fixed by agent configuration, never parsed shell commands.
        mode = os.environ.get('HQ_OPERATIONS_MODE','health')
        if mode not in ('health','network','diagnostics'): raise RuntimeError('Unknown operations mode')
        started = time.monotonic()
        data = {'checked_at_utc':now().isoformat(),'mode':mode}
        if mode != 'network': data.update(gpu=gpu_health(),host=snapshot())
        if mode != 'network':
            try:
                control = self.api('GET', f'/plugins/krishadmin.control-center/api/overview?companyId={self.company_id}')
                data['local_systems'] = []
                for target in control.get('systems', []):
                    if target.get('readAccess') == 'off':
                        data['local_systems'].append({'name':target['name'],'status':'disabled'})
                        continue
                    try:
                        result = self.api('POST', f'/plugins/krishadmin.control-center/api/issues/{self.issue["id"]}/inspect/{target["id"]}', {})
                        data['local_systems'].append(result)
                    except local_agent.ApiError as error:
                        data['local_systems'].append({'name':target['name'],'status':'awaiting_approval' if error.code == 428 else 'unavailable','reason':str(error)})
            except local_agent.ApiError:
                data['local_systems'] = [{'name':'Control Center','status':'unavailable','reason':'Local-system access registry could not be read.'}]

        if mode == 'network': data['network']=discover()
        self.execution_evidence = {'kind':'Deterministic Python tool / CPU', 'model_inference':False,
            'location':'HQ 192.0.2.180 / Paperclip server container', 'model':None,
            'seconds':round(time.monotonic()-started,2), 'run_id':self.run_id,
            'input_tokens':0,'output_tokens':0,
            'note':'Network/API observation runs on HQ CPU. Querying GPU APIs does not invoke GPU inference.'}
        data['execution'] = self.execution_evidence
        workspace = Path('/paperclip/operations')/str(uuid.UUID(self.issue['id']))
        workspace.mkdir(parents=True,exist_ok=True)
        (workspace/'observations.json').write_text(json.dumps(data,indent=2)+'\n')
        (workspace/'report.md').write_text(report(data))
        from artifacts import attachments
        links = attachments(self,workspace)
        return report(data)+'\nDeliverables: '+', '.join(links),'deterministic-read-only-collector',0

if __name__ == '__main__':
    local_agent.Agent=OperationsAgent
    sys.exit(local_agent.main())
