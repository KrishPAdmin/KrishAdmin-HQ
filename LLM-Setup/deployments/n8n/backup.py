#!/usr/bin/env python3
"""Consistent local backup; resume exactly the application services already running."""
import datetime,fcntl,json,os,subprocess,tarfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent
def compose(*args,**kwargs):
    return subprocess.run(['docker','compose',*args],cwd=ROOT,check=True,**kwargs)

def main():
    os.umask(0o077)
    with (ROOT/'.backup.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        running=set(compose('ps','--status','running','--services',capture_output=True,text=True).stdout.split())
        if 'postgres' not in running:raise SystemExit('Database is not running; backup not started.')
        resume=[s for s in ('proxy','runners','n8n') if s in running]
        destination=ROOT/'backups'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        destination.mkdir(parents=True,mode=0o700)
        complete=False
        try:
            if resume:compose('stop',*resume,stdout=subprocess.DEVNULL)
            with (destination/'database.dump').open('wb') as out:
                compose('exec','-T','postgres','pg_dump','-U','postgres','-d','n8n','-Fc',stdout=out)
            container=compose('ps','-a','-q','n8n',capture_output=True,text=True).stdout.strip()
            if not container:raise RuntimeError('n8n container missing')
            with (destination/'n8n-data.tar').open('wb') as out:
                subprocess.run(['docker','cp',container+':/home/node/.n8n/.','-'],stdout=out,check=True)
            with tarfile.open(destination/'deployment-secrets.tar.gz','w:gz') as archive:
                for name in ('.env','compose.yaml','init-db.sh','nginx.conf','tls','README.md','images.lock.txt',
                             'backup.sh','backup.py','workflows','portal','connect-nvidia-gpu.py','trust'):
                    if (ROOT/name).exists():archive.add(ROOT/name,arcname=name)
            complete=True
        finally:
            if resume:compose('start',*resume,stdout=subprocess.DEVNULL)
            (destination/'backup-manifest.json').write_text(json.dumps({'complete':complete,
                'application_quiesced':True,'previously_running_services':resume,
                'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                'off_host_copy':False},indent=2)+'\n')
        print(destination)

if __name__=='__main__':main()
