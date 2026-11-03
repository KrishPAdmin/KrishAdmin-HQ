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
if __name__ == '__main__': print(json.dumps(collect(), indent=2))
PAPERCLIP_READONLY_PROBE
chown root:root /usr/local/lib/paperclip/host_probe.py
chmod 644 /usr/local/lib/paperclip/host_probe.py
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
