#!/usr/bin/env python3
"""Run on NVIDIA-GPU: replace only the managed Ollama container using native CDI.

Keeps the prior container stopped for rollback and the existing model volume.
No image pull, driver changes, host reboot, or Docker daemon restart.
"""
import datetime,json,os,subprocess
from pathlib import Path

def run(*args):
    return subprocess.check_output(args,text=True).strip()

def main():
    os.umask(0o077)
    name='homelab-fast-ollama'
    old=json.loads(run('docker','inspect',name))[0]
    assert old['Config']['Labels'].get('homelab.fast-ai')=='docker-run-v1'
    assert old['HostConfig']['NetworkMode']=='homelab-fast-ai'
    assert old['HostConfig']['Binds']==['homelab-fast-ai-models:/root/.ollama']
    if any(d.get('PathOnHost')=='nvidia.com/gpu=all' for d in old['HostConfig'].get('Devices',[])):
        print('Already configured for native CDI');return
    image=old['Image']
    run('docker','run','--rm','--network','none','--device','nvidia.com/gpu=all',
        '--entrypoint','nvidia-smi',image,'--query-gpu=name','--format=csv,noheader')
    stamp=datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    previous=name+'-before-cdi-'+stamp
    archive=Path.home()/'nvidia-gpu-cdi-recovery'/stamp;archive.mkdir(parents=True,mode=0o700)
    (archive/'container.json').write_text(json.dumps(old,indent=2)+'\n')
    run('docker','stop',name)
    run('docker','rename',name,previous)
    run('docker','update','--restart=no',previous)
    run('docker','network','disconnect','homelab-fast-ai',previous)
    try:
        args=['docker','run','-d','--name',name,'--label','homelab.fast-ai=docker-run-v1',
              '--restart','unless-stopped','--device','nvidia.com/gpu=all',
              '--network','homelab-fast-ai','--network-alias','ollama',
              '-v','homelab-fast-ai-models:/root/.ollama']
        for value in old['Config']['Env']:
            if value.startswith('OLLAMA_'):args.extend(['-e',value])
        args.append(image)
        run(*args)
        print(run('docker','exec',name,'nvidia-smi','--query-gpu=name,temperature.gpu','--format=csv,noheader'))
        run('docker','exec','homelab-fast-proxy','nginx','-s','reload')
    except Exception:
        subprocess.run(['docker','rm','-f',name],capture_output=True)
        run('docker','rename',previous,name)
        run('docker','network','connect','--alias','ollama','homelab-fast-ai',name)
        run('docker','update','--restart=unless-stopped',name)
        run('docker','start',name)
        run('docker','exec','homelab-fast-proxy','nginx','-s','reload')
        raise
    print('CDI migration complete; rollback container: '+previous)
    print('Private configuration snapshot: '+str(archive))

if __name__=='__main__':main()
