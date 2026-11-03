import datetime, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'agents'))
import operations

class OperationsTests(unittest.TestCase):
    def test_missing_snapshot_never_claims_healthy(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(operations.snapshot(Path(d)/'missing')['status'],'unavailable')
    def test_snapshot_stale_and_future_are_not_fresh(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'health.json'
            for age,status in ((60,'fresh'),(601,'stale'),(-60,'stale')):
                p.write_text(json.dumps({'checked_at_utc':(operations.now()-datetime.timedelta(seconds=age)).isoformat()}))
                self.assertEqual(operations.snapshot(p)['status'],status)
            p.write_text('{broken'); self.assertEqual(operations.snapshot(p)['status'],'unavailable')
    def test_discovery_uses_fixed_scope_and_reports_only_positive_observations(self):
        attempts=[]
        def connect(target,timeout):
            attempts.append(target)
            raise OSError('no reply')
        with patch.object(operations.socket,'create_connection',side_effect=connect):
            result=operations.discover()
        self.assertEqual(result['systems'],[])
        self.assertEqual(len(attempts),254*len(operations.PORTS))
        self.assertTrue(all(operations.ipaddress.ip_address(host) in operations.NETWORK for host,port in attempts))
        self.assertIn('does not prove',result['limitations'])
    def test_report_flags_api_failure_without_inventing_hardware_health(self):
        r=operations.report({'checked_at_utc':'now','gpu':{'systems':[{'system':'nvidia-gpu','checks':{'models':{'http_status':503}}}]},'host':{'status':'unavailable'}})
        self.assertIn('FAILED / incomplete',r);self.assertIn('unavailable',r)
    def test_unknown_operation_fails_before_any_collection(self):
        env={'PAPERCLIP_AGENT_ID':'a','PAPERCLIP_COMPANY_ID':'c','PAPERCLIP_RUN_ID':'r','PAPERCLIP_API_URL':'http://localhost','PAPERCLIP_API_KEY':'test','HQ_OPERATIONS_MODE':'reboot'}
        with patch.dict(os.environ,env),patch.object(operations,'gpu_health') as gpu:
            a=operations.OperationsAgent()
            with self.assertRaisesRegex(RuntimeError,'Unknown operations mode'):a.infer([])
            gpu.assert_not_called()
    def test_artifacts_with_credentials_are_withheld(self):
        from artifacts import attachments
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);(p/'leak.txt').write_text('private-test-credential')
            class Fake:
                def private_values(self):return ['private-test-credential']
                def require_active_run(self):pass
            with self.assertRaisesRegex(RuntimeError,'credential'): attachments(Fake(),p)
    def test_coordinator_network_request_routes_without_model(self):
        import department,local_agent
        env={'PAPERCLIP_AGENT_ID':'a','PAPERCLIP_COMPANY_ID':'c','PAPERCLIP_RUN_ID':'r','PAPERCLIP_API_URL':'http://localhost','PAPERCLIP_API_KEY':'test'}
        with patch.dict(os.environ,env):a=local_agent.Agent()
        a.issue={'id':'i','title':'Scan my network'};calls=[]
        def api(method,path,body=None):
            calls.append((method,path,body))
            if method=='GET':return []
            if method=='POST' and path=='/companies/c/issues':return {'id':'child','status':'todo','identifier':'KRI-test'}
            return {}
        with patch.object(a,'api',side_effect=api),patch.object(department,'config',return_value={'targets':{'network':'n'}}),patch.object(a,'infer') as infer:
            department.coordinate(a);infer.assert_not_called()
        created=[x[2] for x in calls if x[0]=='POST' and x[1]=='/companies/c/issues']
        self.assertEqual(created[0]['assigneeAgentId'],'n')
    def test_pi_health_handoff_never_launches_model(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('pi_runtime',Path(__file__).parent/'pi-worker/pi_runtime.py')
        pi=importlib.util.module_from_spec(spec);spec.loader.exec_module(pi)
        env={'PAPERCLIP_AGENT_ID':'a','PAPERCLIP_COMPANY_ID':'c','PAPERCLIP_RUN_ID':'r','PAPERCLIP_API_URL':'http://localhost','PAPERCLIP_API_KEY':'test'}
        with patch.dict(os.environ,env): a=pi.PiAgent()
        a.issue={'id':'9587f9ee-4c8e-5cdb-82f7-a3884153e971','parentId':'p'}
        with tempfile.TemporaryDirectory() as d:
            with patch.object(pi,'Path',return_value=Path(d)),patch.object(a,'internal_handoff',return_value=True),patch.object(a,'api',return_value={'description':'[HQ routine: gpu-health]'}),patch.object(a,'require_active_run'),patch.object(a,'attachments',return_value=['report-link']),patch.object(operations,'gpu_health',return_value={'systems':[]}),patch.object(pi.subprocess,'Popen') as launch:
                text,model,elapsed=a.infer([{'content':'collect'}])
                launch.assert_not_called()
                self.assertTrue((Path(d)/a.issue['id']/'cluster-health.json').exists())
                self.assertIn('report-link',text)
                self.assertEqual(model,'deterministic-gpu-api-collector')
    def test_failure_escalation_is_bounded_and_idempotent(self):
        import escalation
        from unittest.mock import Mock
        a=Mock();a.company_id='company';a.agent_id='local';a.issue={'id':'i','identifier':'KRI-1','title':'health','description':'private task body'}
        cfg={'targets':{'codex':'external'},'codex_ready':True,'escalate_failures':True}
        a.api.side_effect=[[],{'id':'child','identifier':'KRI-2'}]
        with patch.object(escalation.Path,'read_text',return_value=json.dumps(cfg)), patch('operator_policy.policy',return_value={'autoEscalate':True,'externalAI':'ask'}):
            result=escalation.escalate(a,'timeout')
        self.assertEqual(result['id'],'child')
        body=a.api.call_args.args[2]
        self.assertNotIn('private task body',body['description']);self.assertIn('Do not change remote infrastructure',body['description'])
        a.api.reset_mock();a.api.side_effect=None
        a.api.return_value=[{'id':'child','parentId':'i','createdByAgentId':'local','assigneeAgentId':'external','status':'in_review'}]
        with patch.object(escalation.Path,'read_text',return_value=json.dumps(cfg)), patch('operator_policy.policy',return_value={'autoEscalate':True,'externalAI':'ask'}):
            self.assertEqual(escalation.escalate(a,'timeout')['id'],'child')
        a.api.assert_called_once()
    def test_codex_cannot_escalate_to_itself(self):
        import escalation
        from unittest.mock import Mock
        a=Mock();a.agent_id='external'
        cfg={'targets':{'codex':'external'},'codex_ready':True,'escalate_failures':True}
        with patch.object(escalation.Path,'read_text',return_value=json.dumps(cfg)), patch('operator_policy.policy',return_value={'autoEscalate':True,'externalAI':'ask'}):
            self.assertIsNone(escalation.escalate(a,'failure'))
        a.api.assert_not_called()
    def test_host_targets_reject_out_of_scope_hosts_users_and_keys(self):
        import importlib.util
        sys.path.append(str(Path(__file__).parent/'operations'))
        spec=importlib.util.spec_from_file_location('host_refresh',Path(__file__).parent/'operations/refresh.py')
        refresh=importlib.util.module_from_spec(spec);spec.loader.exec_module(refresh)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'keys').mkdir()
            valid={'host':'192.0.2.50','user':'paperclip-observer','key':str(root/'keys/observer')}
            with patch.object(refresh,'ROOT',root):
                (root/'targets.json').write_text(json.dumps({'pve':valid}))
                self.assertEqual(refresh.targets()['pve'],valid)
                for changes in ({'host':'8.8.8.8'},{'user':'-oProxyCommand=bad'},{'key':'/etc/passwd'}):
                    (root/'targets.json').write_text(json.dumps({'pve':{**valid,**changes}}))
                    with self.assertRaises(ValueError):refresh.targets()
if __name__=='__main__':unittest.main()
