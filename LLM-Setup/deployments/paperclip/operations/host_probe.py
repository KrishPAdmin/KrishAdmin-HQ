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
