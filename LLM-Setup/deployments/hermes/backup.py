#!/usr/bin/env python3
"""Consistent private backup of this pilot, with an isolated extraction/integrity check."""
import datetime,hashlib,json,os,sqlite3,subprocess,tarfile,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent
def dc(*args,**kwargs):return subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'--profile','discord',*args],check=True,**kwargs)
def main():
    os.umask(0o077);dest=ROOT/'backups';dest.mkdir(exist_ok=True)
    running=dc('ps','--services','--status','running',capture_output=True,text=True).stdout.split()
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ');archive=dest/(stamp+'.tar.gz')
    notification_timer='hq-hermes-task-notifications.timer'
    notify_active=subprocess.run(['systemctl','--user','is-active','--quiet',notification_timer]).returncode==0
    github_active=subprocess.run(['systemctl','--user','is-active','--quiet','hq-hermes-github.service']).returncode==0
    try:
        if github_active:subprocess.run(['systemctl','--user','stop','hq-hermes-github.service'],check=True)
        # The host notifier also writes tasks.db; quiesce it before archiving SQLite.
        subprocess.run(['systemctl','--user','stop',notification_timer,'hq-hermes-task-notifications.service'],check=True)
        if running:dc('stop',*running)
        selected=[p for p in ROOT.iterdir() if p.is_file() and p.suffix in ('.py','.yaml','.json','.md')]
        selected += [ROOT/x for x in ('access','config','state','profiles','plugin','systemd','docs')]
        with tarfile.open(archive,'w:gz') as tar:
            for p in selected:tar.add(p,arcname=p.name,filter=lambda item:None if '__pycache__' in item.name or '/logs/' in item.name else item)
            for unit in ('hq-hermes-evidence.service','hq-hermes-evidence.timer','hq-hermes-monitor.service','hq-hermes-monitor.timer','hq-hermes-diagnostics.service','hq-hermes-task-notifications.service','hq-hermes-task-notifications.timer','hq-hermes-github.service'):
                path=Path.home()/'.config/systemd/user'/unit
                if path.exists():tar.add(path,arcname='systemd-user/'+unit)
    finally:
        try:
            if running:dc('start',*running)
        finally:
            if github_active:subprocess.run(['systemctl','--user','start','hq-hermes-github.service'],check=True)
            if notify_active:subprocess.run(['systemctl','--user','start',notification_timer],check=True)
    with tempfile.TemporaryDirectory(prefix='hermes-restore-check-') as tmp:
        restore=Path(tmp)
        with tarfile.open(archive) as tar:tar.extractall(restore,filter='data')
        for file in (ROOT/'access').iterdir():
            if file.is_file():assert file.read_bytes()==(restore/'access'/file.name).read_bytes()
        checks=[]
        for db in restore.rglob('*.db'):
            try:
                with sqlite3.connect(db) as conn:assert conn.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
                checks.append(str(db.relative_to(restore)))
            except sqlite3.DatabaseError:raise RuntimeError('Restored database failed integrity check') from None
    receipt={'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'bytes':archive.stat().st_size,
        'isolated_extraction':'passed','credential_roundtrip':'passed','sqlite_integrity':checks,
        'limits':'File/database restore validation only. Restored gateway was never started; live recovery/reboot test remains separate.'}
    (ROOT/'validation/backup-restore.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
if __name__=='__main__':main()
