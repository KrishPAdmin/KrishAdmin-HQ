#!/usr/bin/env python3
"""Approved nightly local backups and isolated restore checks; no deletion."""
import datetime,fcntl,json,os,shutil,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parent

def main():
    os.umask(0o077)
    with (ROOT/'state/backup-maintenance.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if shutil.disk_usage(ROOT).free<10*1024**3:
            raise SystemExit('Backup deferred: less than 10 GiB free; review retention and storage before retrying.')
        receipt={'started_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'steps':[]}
        commands=[('paperclip_backup',['python3',str(ROOT.parent/'paperclip/backup.py')]),
            ('paperclip_restore_check',['python3',str(ROOT/'verify_database_backup.py'),'paperclip']),
            ('n8n_backup',['sudo','-n','python3',str(ROOT.parent/'n8n/backup.py')]),
            ('n8n_restore_check',['sudo','-n','python3',str(ROOT/'verify_database_backup.py'),'n8n'])]
        try:
            for name,command in commands:
                result=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                receipt['steps'].append({'step':name,'status':'passed' if result.returncode==0 else 'failed'})
                if result.returncode:raise RuntimeError(name+' failed; inspect local backup receipts')
            receipt['status']='passed'
        except Exception as error:
            receipt['status']='failed';receipt['error_type']=type(error).__name__
            raise
        finally:
            receipt['finished_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            (ROOT/'state/backup-maintenance.json').write_text(json.dumps(receipt,indent=2)+'\n')
            subprocess.run(['sudo','-n','systemctl','start','hq-backup-observations.service'],check=False)
            subprocess.run(['systemctl','--user','start','hq-hermes-evidence.service'],check=False)
        print('Local backups and database restore checks passed; no archives deleted.')

if __name__=='__main__':main()
