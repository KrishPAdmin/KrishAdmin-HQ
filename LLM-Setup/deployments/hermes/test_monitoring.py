import copy,datetime,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from health_rules import assess
from monitor import advance,save,MAX_EVENTS
from reporting import markdown
import hq

NOW=datetime.datetime(2026,11,2,23,tzinfo=datetime.timezone.utc)

def packet():
    return {'collected_at':NOW.isoformat(),'snapshot_status':'fresh','snapshot_age_seconds':30,
        'gpu_api':[{'system':'amd-gpu','status':'reachable','acceleration':'gpu_residency_reported'}],
        'host_telemetry':{'amd-gpu':{'status':'observed'}},
        'hosts':{'amd-gpu':{'root_disk':{'used_percent':49},'memory':{'MemTotal_bytes':1000,'MemAvailable_bytes':700}}},
        'backups':{'checked_at_utc':NOW.isoformat(),'systems':[{'system':'n8n','status':'file_present',
            'latest_modified_utc':NOW.isoformat(),'database_restore':'passed','application_restore':'not_tested','off_host_copy':'not_configured'}]}}

class MonitoringTests(unittest.TestCase):
    def test_setup_gaps_do_not_claim_outage(self):
        result=assess(packet(),NOW)
        self.assertEqual(result['alerts'],[]);self.assertEqual(len(result['setup_items']),2)
        self.assertNotEqual(result['result'],'healthy')
    def test_missing_host_coverage_does_not_change_api_status(self):
        p=packet();p['host_telemetry']['amd-gpu']['status']='unavailable'
        result=assess(p,NOW)
        self.assertEqual([r['id'] for r in result['alerts']],['host_telemetry:amd-gpu'])
        self.assertEqual(p['gpu_api'][0]['status'],'reachable')
    def test_no_model_loaded_is_not_a_gpu_failure(self):
        p=packet();p['gpu_api'][0]['acceleration']='no_model_loaded'
        self.assertEqual(assess(p,NOW)['alerts'],[])
    def test_cpu_fallback_is_critical(self):
        p=packet();p['gpu_api'][0]['acceleration']='cpu_only'
        self.assertEqual(assess(p,NOW)['alerts'][0]['severity'],'critical')
    def test_thresholds_and_stale_metrics(self):
        p=packet();p['hosts']['amd-gpu']['root_disk']['used_percent']=92
        p['hosts']['amd-gpu']['memory']['MemAvailable_bytes']=40
        self.assertEqual({r['id']:r['severity'] for r in assess(p,NOW)['alerts']},{'root_disk:amd-gpu':'critical','memory:amd-gpu':'critical'})
        p['snapshot_age_seconds']=601;p['snapshot_status']='stale'
        self.assertEqual([r['id'] for r in assess(p,NOW)['alerts']],['host_snapshot:collector'])
    def test_backup_age_recomputed_not_trusted_from_old_label(self):
        p=packet();p['backups']['systems'][0].update(freshness='fresh',latest_modified_utc=(NOW-datetime.timedelta(hours=37)).isoformat())
        self.assertIn('backup_stale:n8n',[r['id'] for r in assess(p,NOW)['alerts']])
    def test_future_timestamps_are_not_fresh(self):
        p=packet();p['backups']['checked_at_utc']=(NOW+datetime.timedelta(minutes=1)).isoformat()
        self.assertIn('backup_metadata:collector',[r['id'] for r in assess(p,NOW)['alerts']])
    def test_events_deduplicated_and_recovery_recorded(self):
        alert={'id':'test:disk','severity':'warning','target':'test','message':'disk','next_step':'inspect'}
        first=advance({},[alert],'one',True);second=advance(first,[alert],'two',True)
        self.assertEqual(len(second['events']),1)
        final=advance(second,[],'three',True)
        self.assertEqual(final['events'][-1]['change'],'resolved')
    def test_failed_collection_never_resolves_previous_alerts(self):
        previous={'active_alerts':[{'id':'disk:test','severity':'critical'}]}
        failed=advance(previous,[{'id':'broker:local','severity':'critical'}],'now',False)
        self.assertEqual(len(failed['active_alerts']),2)
        self.assertFalse(any(e['change']=='resolved' for e in failed['events']))
    def test_history_is_bounded(self):
        previous={'events':[{'change':'old'}]*MAX_EVENTS}
        result=advance(previous,[{'id':'one','severity':'warning'}],'now',True)
        self.assertEqual(len(result['events']),MAX_EVENTS)
    def test_atomic_monitor_file_is_private(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'state.json';save(path,{'value':1})
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertEqual(json.loads(path.read_text()),{'value':1})
    def test_report_refuses_to_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'report.md';path.write_text('keep')
            with patch('sys.argv',['hq.py','report','--output',str(path)]),patch.object(hq,'call',return_value=packet()):
                with self.assertRaises(FileExistsError):hq.main()
            self.assertEqual(path.read_text(),'keep')
    def test_report_does_not_promote_database_restore_to_full_recovery(self):
        p=packet();p['assessment']=assess(p,NOW);text=markdown(p)
        self.assertIn('not_tested',text);self.assertIn('does not prove full application recovery',text)

if __name__=='__main__':unittest.main()
