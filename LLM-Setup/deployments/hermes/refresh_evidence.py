"""Copy bounded observations and backup metadata, never archive contents or credentials."""
import datetime,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def save(path,value):
    fd,tmp=tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd,'w') as f:json.dump(value,f,indent=2)
    os.chmod(tmp,0o600);os.replace(tmp,path)

def main():
    out=ROOT/'observations';out.mkdir(exist_ok=True)
    source=ROOT.parent/'paperclip/operations/snapshots/host-health.json'
    if source.exists():save(out/'host-health.json',json.loads(source.read_text()))
    metadata=Path('/var/lib/hq-observations/backup-status.json')
    if metadata.exists():
        value=json.loads(metadata.read_text())
        age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(value['checked_at_utc'])).total_seconds()
        value['metadata_status']='fresh' if 0<=age<=600 else 'stale'
        save(out/'backup-status.json',value)
        print('Local observations and sanitized backup metadata refreshed.')
        return
    rows=[]
    for name,folder,pattern in [('paperclip',ROOT.parent/'paperclip/backups','*/database.dump'),
            ('paperclip-generated',ROOT.parent/'paperclip/data/instances/default/data/backups','*.sql.gz'),
            ('n8n',ROOT.parent/'n8n/backups','*')]:
        try:
            # pathlib.glob can hide EACCES; explicitly verify directory traversal first.
            with os.scandir(folder) as scan:next(scan,None)
            entries=[p for p in folder.glob(pattern) if p.is_file()]
            latest=max(entries,key=lambda p:p.stat().st_mtime) if entries else None
            rows.append({'system':name,'status':'file_present' if latest else 'no_file_observed',
                'latest_modified_utc':datetime.datetime.fromtimestamp(latest.stat().st_mtime,datetime.timezone.utc).isoformat() if latest else None,
                'bytes':latest.stat().st_size if latest else None,'restore_verified':False})
        except PermissionError:rows.append({'system':name,'status':'unavailable','reason':'metadata access denied','restore_verified':False})
    save(out/'backup-status.json',{'checked_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'systems':rows,
        'limitations':'Metadata only; no archive contents read. Freshness thresholds and off-host coverage not yet configured.'})
    print('Local observation and backup metadata refreshed.')
if __name__=='__main__':main()
