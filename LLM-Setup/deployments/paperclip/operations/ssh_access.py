#!/usr/bin/env python3
"""Password transport for the explicitly configured AMD-GPU account; never log secrets."""
import os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def amd_gpu(command,timeout=45,input=None):
    env={**os.environ,'SSH_ASKPASS':str(ROOT/'ssh_access.py'),'SSH_ASKPASS_REQUIRE':'force','DISPLAY':'hq:0','HQ_SSH_ASKPASS':'amd-gpu'}
    args=['/usr/bin/ssh','-F','/dev/null','-o','PubkeyAuthentication=no','-o','PreferredAuthentications=password','-o','NumberOfPasswordPrompts=1','-o','StrictHostKeyChecking=yes','-o','ClearAllForwardings=yes','-o','ConnectTimeout=5','-o','ServerAliveInterval=5','-o','ServerAliveCountMax=2','-o','UserKnownHostsFile='+str(Path.home()/'.ssh/known_hosts'),'krishadmin@198.51.100.202',command]
    return subprocess.run(args,input=input,stdin=subprocess.DEVNULL if input is None else None,capture_output=True,text=True,timeout=timeout,env=env,start_new_session=True)

if __name__=='__main__':
    if os.environ.get('HQ_SSH_ASKPASS')!='amd-gpu' or len(sys.argv)!=2 or 'password' not in sys.argv[1].lower():raise SystemExit(1)
    sys.stdout.write((ROOT/'keys/amd-gpu-password').read_text().rstrip('\n')+'\n')
