import datetime,hashlib,json,os,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import backup_observer,broker

class ObservationTests(unittest.TestCase):
    def test_database_proof_only_applies_to_exact_dump(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);folder=root/'one';folder.mkdir();dump=folder/'database.dump';dump.write_bytes(b'example')
            proof={'database_sha256':hashlib.sha256(b'example').hexdigest(),'database_restore':'passed','archive_integrity':'passed'}
            (folder/'restore-validation.json').write_text(json.dumps(proof))
            now=datetime.datetime.now(datetime.timezone.utc)
            row=backup_observer.summarize('n8n',root,'*/database.dump',now)
            self.assertEqual(row['database_restore'],'passed');self.assertFalse(row['restore_verified'])
            dump.write_bytes(b'changed')
            self.assertEqual(backup_observer.summarize('n8n',root,'*/database.dump',now)['database_restore'],'not_tested')

    def test_incomplete_new_backup_does_not_hide_complete_backup(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in ('old','new'):
                folder=root/name;folder.mkdir();(folder/'database.dump').write_bytes(name.encode())
            (root/'new/backup-manifest.json').write_text('{"complete": false}')
            row=backup_observer.summarize('n8n',root,'*/database.dump',datetime.datetime.now(datetime.timezone.utc))
            self.assertEqual(row['bytes'],3)
            (root/'old/database.dump').unlink()
            self.assertEqual(backup_observer.summarize('n8n',root,'*/database.dump',datetime.datetime.now(datetime.timezone.utc))['status'],'no_file_observed')

    def test_old_backups_are_stale_not_missing(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'one').mkdir();p=root/'one/database.dump';p.write_bytes(b'dump');os.utime(p,(1,1))
            row=backup_observer.summarize('n8n',root,'*/database.dump',datetime.datetime.now(datetime.timezone.utc))
            self.assertEqual(row['status'],'file_present');self.assertEqual(row['freshness'],'stale')

    def test_reachable_gpu_and_missing_host_measurements_remain_separate(self):
        snapshot={'checked_at_utc':broker.now(),'hq':{},'remote_hosts':{'amd-gpu':{'status':'unavailable','reason':'SSH authentication failed'}}}
        with patch.object(Path,'read_text',return_value=json.dumps(snapshot)),patch.object(broker,'audit'),patch.object(broker,'gpu',side_effect=lambda name:{'system':name,'status':'reachable'}):
            result=broker.evidence('health')
        self.assertEqual(result['gpu_api'][1]['status'],'reachable')
        self.assertEqual(result['coverage']['amd-gpu'],'host_telemetry_unavailable')
        self.assertEqual(result['host_telemetry']['amd-gpu']['reason'],'SSH authentication failed')

if __name__=='__main__':unittest.main()
