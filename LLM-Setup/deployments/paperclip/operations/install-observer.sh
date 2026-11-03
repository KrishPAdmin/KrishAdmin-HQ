#!/bin/sh
# Run as root on a Linux host you want Paperclip to observe. No sudo privileges are granted to the observer.
set -eu
if ! id paperclip-observer >/dev/null 2>&1; then useradd --create-home --shell /bin/sh paperclip-observer; fi
install -d -m 755 /usr/local/lib/paperclip
cat > /usr/local/lib/paperclip/host_probe.py <<'PAPERCLIP_READONLY_PROBE'
#!/usr/bin/env python3
"""Fixed read-only Linux observations, usable locally or over verified SSH."""
import datetime, json, os, shutil, socket, subprocess
from pathlib import Path

def command(args, timeout=8):
    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return {'ok': r.returncode == 0, 'output': r.stdout[:12000], 'exit_code': r.returncode}
    except (OSError, subprocess.TimeoutExpired) as e:
        return {'ok': False, 'error': type(e).__name__}

def collect():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        if key in ('MemTotal', 'MemAvailable', 'SwapTotal', 'SwapFree'):
            memory[key + '_bytes'] = int(value.split()[0]) * 1024
    disk = shutil.disk_usage('/')
    result = {'checked_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'hostname': socket.gethostname(), 'uptime_seconds': float(Path('/proc/uptime').read_text().split()[0]),
              'load_average': list(os.getloadavg()), 'logical_cpus': os.cpu_count(), 'memory': memory,
              'root_disk': {'total_bytes': disk.total, 'free_bytes': disk.free, 'used_percent': round(disk.used/disk.total*100,1)},
              'failed_services': command(['systemctl','--failed','--no-legend','--plain']),
              'limitations': 'Root filesystem only; no SMART, RAID, backup integrity or inference benchmark.'}
    if shutil.which('nvidia-smi'):
        result['nvidia'] = command(['nvidia-smi','--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total','--format=csv,noheader'])
    if shutil.which('rocm-smi'):
        result['amd'] = command(['rocm-smi','--showtemp','--showuse','--showmemuse','--json'])
    return result
if __name__ == '__main__':
    original=os.environ.get('SSH_ORIGINAL_COMMAND','')
    if original.startswith('diagnostics '):
        from diagnostics_probe import collect as diagnose,CHECKS
        check=original.removeprefix('diagnostics ')
        if check not in CHECKS:raise SystemExit('Unsupported fixed diagnostic check')
        print(json.dumps(diagnose(check)))
    elif original in ('','probe','python3 -'):
        print(json.dumps(collect(), indent=2))
    else:raise SystemExit('Unsupported observer command')
PAPERCLIP_READONLY_PROBE
chown root:root /usr/local/lib/paperclip/host_probe.py
chmod 644 /usr/local/lib/paperclip/host_probe.py
cat > /usr/local/lib/paperclip/diagnostics_probe.py <<'PAPERCLIP_DIAGNOSTICS_PROBE'
#!/usr/bin/env python3
"""Fixed local diagnostics. No shell, model-selected arguments, or network commands."""
import datetime,json,os,platform,shutil,subprocess,sys,time
from pathlib import Path
CHECKS=('overview','gpu','processes','services','storage')

def process_snapshot(root=Path('/proc')):
    rows={};skipped=0
    for p in root.iterdir():
        if not p.name.isdigit() or int(p.name)==os.getpid():continue
        try:
            raw=(p/'stat').read_text();head,tail=raw.rsplit(')',1);fields=tail.split()
            rows[int(p.name)]={'pid':int(p.name),'name':head.split('(',1)[1][:48],
                'state':fields[0],'ticks':int(fields[11])+int(fields[12]),'start_ticks':int(fields[19]),
                'rss_bytes':max(0,int(fields[21]))*os.sysconf('SC_PAGE_SIZE'),'uid':p.stat().st_uid,'sample_at':time.monotonic()}
        except (OSError,ValueError,IndexError):skipped+=1
    return rows,skipped

def process_delta(first,second,ticks_per_second,users):
    rows=[]
    for pid,b in second.items():
        a=first.get(pid)
        if not a or a['start_ticks']!=b['start_ticks'] or b['sample_at']<=a['sample_at']:continue
        elapsed=b['sample_at']-a['sample_at']
        rows.append({k:b[k] for k in ('pid','name','state','rss_bytes')}|{
            'user':users.get(b['uid'],str(b['uid'])),'cpu_percent':round(max(0,b['ticks']-a['ticks'])/ticks_per_second/elapsed*100,1)})
    return rows

def process_sample():
    users={}
    for line in Path('/etc/passwd').read_text().splitlines():
        fields=line.split(':')
        if len(fields)>2 and fields[2].isdigit():users[int(fields[2])]=fields[0]
    started=time.monotonic();first,skipped1=process_snapshot();time.sleep(1);second,skipped2=process_snapshot()
    rows=process_delta(first,second,os.sysconf('SC_CLK_TCK'),users)
    metadata={'status':'observed' if rows else 'unavailable','sample_seconds':round(time.monotonic()-started,3),
        'metric':'CPU tick delta during this sample; 100% = one logical CPU',
        'sampled_processes':len(rows),'skipped_or_exited':skipped1+skipped2,'collector_pid_excluded':os.getpid()}
    return {name:{**metadata,'rows':sorted(rows,key=lambda r:(-r[metric],r['pid']))[:40],'truncated':len(rows)>40}
            for name,metric in [('cpu_processes','cpu_percent'),('memory_processes','rss_bytes')]}

def run(argv):
    env={'PATH':'/usr/sbin:/usr/bin:/sbin:/bin:/opt/rocm/bin','LANG':'C','LC_ALL':'C','HOME':'/nonexistent'}
    exe=shutil.which(argv[0],path=env['PATH'])
    if not exe:return {'status':'unavailable','reason':'command_not_installed','command':argv[0]}
    try:
        p=subprocess.run([exe,*argv[1:]],env=env,capture_output=True,text=True,timeout=10)
        text=p.stdout[:9000]
        if argv[0]=='ps':text='\n'.join(text.splitlines()[:41])
        return {'status':'observed' if p.returncode==0 else 'unavailable','exit_code':p.returncode,'command':argv,'output':text,'truncated':len(p.stdout)>len(text)}
    except (OSError,subprocess.TimeoutExpired) as e:return {'status':'unavailable','command':argv[0],'reason':type(e).__name__}

def collect(check):
    if check not in CHECKS:raise ValueError('Unsupported fixed diagnostic check')
    out={'schema_version':1,'check':check,'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'hostname':platform.node(),'kernel':platform.release(),'executor':'fixed local read-only probe','checks':{}}
    if check=='overview':
        out['checks']={'uptime':run(['uptime']),'memory':run(['free','-b']),'cpu_sample':run(['vmstat','-w','1','2'])}
    elif check=='gpu':
        if shutil.which('nvidia-smi'):
            out['checks']['nvidia']=run(['nvidia-smi','--query-gpu=index,name,driver_version,pci.bus_id,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw','--format=csv,noheader'])
        if shutil.which('rocm-smi',path='/usr/bin:/bin:/opt/rocm/bin'):
            out['checks']['amd']=run(['rocm-smi','--showdriverversion','--showproductname','--showtemp','--showuse','--showmemuse','--json'])
        versions={}
        for path in ['/sys/module/nvidia/version','/sys/module/amdgpu/version','/opt/rocm/.info/version']:
            try:versions[path]=Path(path).read_text()[:200].strip()
            except OSError:pass
        out['driver_versions']=versions
        if not out['checks']:out['checks']['gpu']={'status':'unavailable','reason':'No supported nvidia-smi or rocm-smi binary installed'}
    elif check=='processes':
        out['checks']=process_sample()
        out['limitations']='One-second CPU sample, 100% equals one logical CPU; at most 40 rows per ranking. Only processes present in both snapshots are ranked; exited/new/unreadable processes can be missed. Collector process excluded. RSS is resident memory, not unique memory. State S means sleeping at the final instant, not session or idle throughout the sample. CPU usage/process names do not prove GPU use or active inference. No full command lines or environments.'
    elif check=='services':
        out['checks']={'failed_units':run(['systemctl','--failed','--no-pager','--no-legend','--plain']),
                      'service_states':run(['systemctl','show','ollama.service','docker.service','ssh.service','--property=Id,LoadState,ActiveState,SubState,Result','--no-pager'])}
    else:
        out['checks']={'filesystems':run(['df','-l','-hT','-x','tmpfs','-x','devtmpfs']),'inodes':run(['df','-l','-i','-x','tmpfs','-x','devtmpfs']),
                      'block_devices':run(['lsblk','--json','--output','NAME,TYPE,SIZE,FSTYPE,MOUNTPOINTS,RO'])}
    statuses=[v['status'] for v in out['checks'].values()];out['status']='observed' if all(s=='observed' for s in statuses) else 'partial' if 'observed' in statuses else 'unavailable'
    out.setdefault('limitations','Fixed unprivileged local commands only. No repair, driver installation/reset, logs, network discovery, or complete hardware certification.')
    return out

if __name__=='__main__':
    if len(sys.argv)!=2 or sys.argv[1] not in CHECKS:raise SystemExit('Expected one fixed diagnostic check')
    print(json.dumps(collect(sys.argv[1])))
PAPERCLIP_DIAGNOSTICS_PROBE
chown root:root /usr/local/lib/paperclip/diagnostics_probe.py
chmod 644 /usr/local/lib/paperclip/diagnostics_probe.py
install -d -m 700 -o paperclip-observer -g paperclip-observer /home/paperclip-observer/.ssh
cat > /home/paperclip-observer/.ssh/paperclip-authorized-key <<'PAPERCLIP_OBSERVER_PUBLIC_KEY'
restrict,from="192.0.2.180,198.51.100.21",command="/usr/bin/python3 /usr/local/lib/paperclip/host_probe.py" ssh-ed25519 REPLACE_WITH_YOUR_OBSERVER_PUBLIC_KEY paperclip-readonly-observer
PAPERCLIP_OBSERVER_PUBLIC_KEY
touch /home/paperclip-observer/.ssh/authorized_keys
if ! grep -Fq 'paperclip-readonly-observer' /home/paperclip-observer/.ssh/authorized_keys; then
    cat /home/paperclip-observer/.ssh/paperclip-authorized-key >> /home/paperclip-observer/.ssh/authorized_keys
fi
chown paperclip-observer:paperclip-observer /home/paperclip-observer/.ssh/authorized_keys
chmod 600 /home/paperclip-observer/.ssh/authorized_keys
printf '%s\n' 'Read-only observer installed. No root or sudo access granted.'
