"""Credential handling stays on HQ; no secrets returned to a model."""
import json, socket, time
from pathlib import Path
import paramiko
import requests
import socketio
ROOT=Path(__file__).resolve().parent
HOSTS={'Pi-Cluster-01':'192.0.2.90','Pi-Cluster-02':'192.0.2.91','Pi-Cluster-03':'192.0.2.92'}

ALIASES={'pi90':'Pi-Cluster-01','pi91':'Pi-Cluster-02','pi92':'Pi-Cluster-03'}

def target_name(value):
    return ALIASES.get(value,value)

def password():
    import sys
    if '/usr/local/lib' not in sys.path:sys.path.insert(0,'/usr/local/lib')
    from hq_vault_client import credential
    return credential('pi-cluster')

def connect(target,enroll=False):
    target=target_name(target)
    client=paramiko.SSHClient();client.load_system_host_keys(str(Path.home()/'.ssh/known_hosts'))
    keys=ROOT/'state/homelab/known_hosts'
    if keys.exists():client.load_host_keys(str(keys))
    if enroll:client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOSTS[target],username='krishadmin',password=password(),allow_agent=False,look_for_keys=False,timeout=8,banner_timeout=8,auth_timeout=8)
    if enroll:client.save_host_keys(str(keys));keys.chmod(0o600)
    return client

def run(target,command,timeout=25):
    with connect(target) as client:
        channel=client.get_transport().open_session(timeout=8);channel.settimeout(timeout);channel.exec_command(command)
        output=bytearray();errors=bytearray();end=time.monotonic()+timeout
        while True:
            if channel.recv_ready():output.extend(channel.recv(4096))
            if channel.recv_stderr_ready():errors.extend(channel.recv_stderr(4096))
            if len(output)+len(errors)>64000:channel.close();raise RuntimeError('Remote output exceeded limit')
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():break
            if time.monotonic()>end:channel.close();raise TimeoutError('Remote command timed out; verify state before retrying')
            time.sleep(.02)
        code=channel.recv_exit_status();channel.close()
        secret=password()
        return {'exit_code':code,'output':output.decode(errors='replace').replace(secret,'[redacted]'),'stderr':errors.decode(errors='replace').replace(secret,'[redacted]')}

def kuma():
    session=requests.Session();session.verify='/etc/ssl/certs/ca-certificates.crt'
    client=socketio.Client(http_session=session,logger=False,engineio_logger=False,reconnection=False,request_timeout=12)
    monitors={};heartbeats={}
    @client.on('monitorList')
    def monitor_list(data):monitors.update(data)
    @client.on('heartbeatList')
    def heartbeat_list(mid,beats,*rest):
        if beats:heartbeats[str(mid)]=beats[-1]
    @client.on('heartbeat')
    def heartbeat(beat):heartbeats[str(beat.get('monitorID'))]=beat
    try:
        client.connect('https://status.example.invalid',transports=['polling'],wait_timeout=15)
        result=client.call('login',{'username':'krishadmin','password':password(),'token':''},timeout=15)
        if not result.get('ok'):raise PermissionError('Uptime Kuma login rejected')
        # monitorList and heartbeatList arrive asynchronously following login.
        client.call('getMonitorList',timeout=15)
        time.sleep(2)
        return {'checked_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'dashboard':'https://status.example.invalid/dashboard',
                'monitors':[{'id':str(mid),'name':row.get('name'),'active':row.get('active'),'type':row.get('type'),
                             'status':heartbeats.get(str(mid),{}).get('status'),'heartbeat_time':heartbeats.get(str(mid),{}).get('time'),
                             'ping_ms':heartbeats.get(str(mid),{}).get('ping')} for mid,row in monitors.items()],
                'status_codes':{'0':'down','1':'up','2':'pending','3':'maintenance'},'credentials_exposed':False}
    finally:
        if client.connected:client.disconnect()
        session.close()
