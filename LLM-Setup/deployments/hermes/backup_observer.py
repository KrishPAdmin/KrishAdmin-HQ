#!/usr/bin/env python3
"""Root-owned scheduled exporter: backup metadata only, no archive contents."""
import datetime,hashlib,json,os,tempfile
from pathlib import Path

BASE=Path('/home/operator/krishadmin-hq/deployments')
OUTPUT=Path('/var/lib/hq-observations/backup-status.json')
SOURCES=[('paperclip',BASE/'paperclip/backups','*/database.dump'),
         ('paperclip-generated',BASE/'paperclip/data/instances/default/data/backups','*.sql.gz'),
         ('n8n',BASE/'n8n/backups','*/database.dump')]

def summarize(name,folder,pattern,now):
    row={'system':name,'restore_verified':False,'application_restore':'not_tested',
         'database_restore':'not_tested','freshness_target_hours':36,'off_host_copy':'not_configured'}
    try:
        with os.scandir(folder) as scan:next(scan,None)
        entries=[]
        for p in folder.glob(pattern):
            if not p.is_file() or p.is_symlink():continue
            manifest=p.parent/'backup-manifest.json'
            if manifest.exists() and not json.loads(manifest.read_text()).get('complete'):continue
            entries.append(p)
        latest=max(entries,key=lambda p:p.stat().st_mtime) if entries else None
        if latest is None:return row|{'status':'no_file_observed'}
        info=latest.stat();age=now.timestamp()-info.st_mtime
        row.update(status='file_present',latest_modified_utc=datetime.datetime.fromtimestamp(info.st_mtime,datetime.timezone.utc).isoformat(),
            bytes=info.st_size,age_hours=round(age/3600,2),freshness='fresh' if 0<=age<=36*3600 else 'stale')
        receipt=latest.parent/'restore-validation.json'
        if name!='paperclip-generated' and receipt.exists():
            proof=json.loads(receipt.read_text())
            with latest.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
            if proof.get('database_sha256')==sha:
                row['database_restore']=proof.get('database_restore','not_tested')
                row['validated_at_utc']=proof.get('validated_at_utc')
                row['archive_integrity']=proof.get('archive_integrity','not_tested')
    except PermissionError:row.update(status='unavailable',reason='metadata access denied')
    except (OSError,ValueError):row.update(status='unavailable',reason='metadata inspection failed')
    return row

def main():
    now=datetime.datetime.now(datetime.timezone.utc)
    result={'checked_at_utc':now.isoformat(),'systems':[summarize(*source,now) for source in SOURCES],
        'limitations':'36-hour local freshness target. Database restore validation is separate from full application recovery. Off-host backups are not configured.'}
    OUTPUT.parent.mkdir(mode=0o755,parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=OUTPUT.parent)
    with os.fdopen(fd,'w') as f:json.dump(result,f,indent=2);f.write('\n')
    os.chmod(tmp,0o644);os.replace(tmp,OUTPUT)

if __name__=='__main__':main()
