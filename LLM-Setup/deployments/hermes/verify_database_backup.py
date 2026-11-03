#!/usr/bin/env python3
"""Restore a local dump into disposable, networkless PostgreSQL; never start apps."""
import argparse,datetime,gzip,hashlib,json,os,subprocess,tarfile,time,uuid
from pathlib import Path

BASE=Path(__file__).resolve().parent.parent
DATABASES={'n8n':'homelab-n8n-postgres-1','paperclip':'hq-paperclip-db-1'}

def docker(*args,**kw):
    return subprocess.run(['docker',*args],check=True,capture_output=True,**kw)

def validate(system,folder):
    os.umask(0o077)
    dump=folder/'database.dump'
    if not dump.is_file():raise ValueError('Missing database.dump')
    with dump.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    image=json.loads(docker('inspect',DATABASES[system]).stdout)[0]['Image']
    name='hq-restore-check-'+uuid.uuid4().hex[:12]
    receipt={'database_sha256':sha,'database_restore':'failed','application_restore':'not_tested',
             'network':'none','production_database_modified':False,'image_id':image}
    try:
        docker('run','-d','--name',name,'--network','none','--memory','1g','--cpus','1',
               '--tmpfs','/var/lib/postgresql:rw,nosuid,size=768m',
               '--tmpfs','/var/lib/postgresql/data:rw,nosuid,size=768m',
               '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','PGDATA=/var/lib/postgresql/data/check',image)
        deadline=time.monotonic()+60
        while True:
            check=subprocess.run(['docker','exec',name,'pg_isready','-U','postgres'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            if check.returncode==0:break
            if time.monotonic()>deadline:raise RuntimeError('Temporary database did not become ready')
            time.sleep(1)
        docker('exec',name,'createdb','-U','postgres','restored')
        with dump.open('rb') as source:
            docker('exec','-i',name,'pg_restore','-U','postgres','--exit-on-error','--no-owner','--no-privileges','-d','restored',stdin=source)
        query="SELECT count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"
        count=int(docker('exec',name,'psql','-U','postgres','-d','restored','-Atc',query).stdout)
        if count<1:raise RuntimeError('No application tables restored')
        receipt.update(database_restore='passed',restored_public_table_count=count)
        archives=[folder/'n8n-data.tar',folder/'deployment-secrets.tar.gz'] if system=='n8n' else [folder/'instance.tar.gz']
        for path in archives:
            if not path.is_file():raise RuntimeError('Matching application archive missing')
            # Read every byte, including gzip trailers. No extraction or contents printed.
            with (gzip.open(path,'rb') if path.name.endswith('.gz') else path.open('rb')) as f:
                while f.read(1024*1024):pass
            with tarfile.open(path) as archive:
                for member in archive:
                    if member.isfile():
                        with archive.extractfile(member) as f:
                            while f.read(1024*1024):pass
        receipt['archive_integrity']='passed'
    except Exception as error:
        receipt['error_type']=type(error).__name__
        raise
    finally:
        # Only the uniquely named temporary container can be removed here.
        cleanup=subprocess.run(['docker','rm','-fv',name],capture_output=True)
        receipt['temporary_container_removed']=cleanup.returncode==0
        receipt['validated_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        (folder/'restore-validation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt

def main():
    parser=argparse.ArgumentParser();parser.add_argument('system',choices=DATABASES)
    parser.add_argument('--folder',type=Path);args=parser.parse_args()
    folder=args.folder or max((BASE/args.system/'backups').glob('*/database.dump'),key=lambda p:p.stat().st_mtime).parent
    try:print(json.dumps(validate(args.system,folder),indent=2))
    except Exception as error:raise SystemExit('Restore validation failed: '+type(error).__name__+'. See private restore-validation.json; no dump contents printed.') from None

if __name__=='__main__':main()
