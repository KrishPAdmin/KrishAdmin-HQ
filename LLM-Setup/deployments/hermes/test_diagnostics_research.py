import json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch,Mock
import broker,diagnostics_service,web_research
sys.path.insert(0,str(Path('../paperclip/operations').resolve()))
import diagnostics_probe,ssh_access

class DiagnosticsTests(unittest.TestCase):
 def test_untrusted_target_check_or_extra_command_never_executes(self):
  with patch('diagnostics_service.subprocess.run') as run:
   for body in [{'target':'203.0.113.2','check':'gpu'},{'target':'amd-gpu','check':'gpu; id'},{'target':'nvidia-gpu','check':'gpu','command':'id'}]:
    with self.assertRaises(ValueError):diagnostics_service.execute(body)
   run.assert_not_called()
 def test_probe_invalid_mode_never_executes(self):
  with patch('diagnostics_probe.subprocess.run') as run:
   with self.assertRaises(ValueError):diagnostics_probe.collect('gpu --reset')
   run.assert_not_called()
 def test_process_table_excludes_arguments_environment(self):
  a={1:{'pid':1,'name':'worker','state':'S','ticks':100,'start_ticks':1,'rss_bytes':4096,'uid':1000,'sample_at':1}}
  b={1:a[1]|{'ticks':264,'sample_at':2},2:a[1]|{'pid':2}}
  rows=diagnostics_probe.process_delta(a,b,100,{1000:'tester'})
  self.assertEqual(rows,[{'pid':1,'name':'worker','state':'S','rss_bytes':4096,'user':'tester','cpu_percent':164.0}])
  self.assertNotIn('args',rows[0]);self.assertNotIn('environ',rows[0])
 def test_process_cpu_sampler_rejects_pid_reuse_and_negative_ticks(self):
  a={1:{'pid':1,'name':'worker','state':'S','ticks':100,'start_ticks':1,'rss_bytes':4096,'uid':1000,'sample_at':1}}
  self.assertEqual(diagnostics_probe.process_delta(a,{1:a[1]|{'start_ticks':2,'sample_at':2}},100,{}),[])
  self.assertEqual(diagnostics_probe.process_delta(a,{1:a[1]|{'ticks':0,'sample_at':2}},100,{})[0]['cpu_percent'],0)
 def test_amd_gpu_uses_password_only_without_putting_password_in_arguments(self):
  with patch('ssh_access.subprocess.run',return_value=Mock(returncode=0)) as run: ssh_access.amd_gpu('/usr/bin/python3 /usr/local/lib/paperclip/diagnostics_probe.py gpu')
  args=run.call_args.args[0];self.assertIn('PubkeyAuthentication=no',args);self.assertNotIn('-i',args);self.assertNotIn('password',run.call_args.kwargs['env'])
 def test_legacy_observer_cannot_be_reported_as_complete_diagnostics(self):
  with patch('diagnostics_service.subprocess.run',return_value=Mock(returncode=0,stdout='{"hostname":"old"}')):
   result=diagnostics_service.execute({'target':'nvidia-gpu','check':'gpu'})
  self.assertEqual(result['status'],'unavailable');self.assertIn('upgrade',result['reason'])

class WebResearchTests(unittest.TestCase):
 def test_research_instructions_are_not_used_as_search_subject(self):
  self.assertEqual(web_research.focused_query('Research the iPhone Duo specifications using current official sources. Cite the technical specification page in the final answer.'),'iPhone Duo specifications official')
 def test_short_managed_research_call_cannot_silently_return_roster(self):
  packet={'sources':[{'url':'https://example.com/specs','excerpt':'Published specifications.'}], 'search':{'status':'ok'},'status':'sources_collected'}
  replies=[{'agent':'jessica','text':'Find primary sources','backend':'amd-gpu','model':'manager','run_id':'one'},
           {'agent':'rachel','text':'Source-based result','backend':'nvidia-gpu','model':'researcher','run_id':'two'}]
  with patch('broker.collect_web',return_value=packet),patch('broker.audit'),patch.object(Path,'read_text',return_value='test-token'),patch('broker.request',side_effect=replies) as request:
   result=broker.team_request({'agent':'jessica','delegate_to':'rachel','kind':'research','search_query':'Current product specs'})
  self.assertEqual([c.args[0] for c in request.call_args_list],['http://jessica:8080/run','http://rachel:8080/run'])
  self.assertEqual(result['manager']['run_id'],'one');self.assertEqual(result['analysis']['run_id'],'two')
 def test_managed_research_without_question_does_not_claim_delegation(self):
  with patch('broker.request') as request:
   with self.assertRaises(ValueError):broker.team_request({'agent':'jessica','delegate_to':'rachel','kind':'research'})
   request.assert_not_called()
 def test_private_destination_blocked_before_connection(self):
  with patch('web_research.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]),patch('web_research.socket.socket') as sock:
   with self.assertRaises(ValueError):web_research.fetch('https://example.com/page')
   sock.assert_not_called()
 def test_credentials_and_plain_http_blocked(self):
  with patch('web_research.socket.getaddrinfo') as dns:
   for url in ['http://example.com','https://user:pass@example.com','https://example.com:22']:
    with self.assertRaises(ValueError):web_research.fetch(url)
   dns.assert_not_called()
 def test_search_outage_returns_no_evidence_not_fake_research(self):
  with patch('web_research.fetch',side_effect=OSError):result=web_research.collect('example')
  self.assertEqual(result['status'],'no_source_evidence');self.assertEqual(result['search']['status'],'failed')
 def test_rachel_fetches_before_inference_and_does_not_infer_without_sources(self):
  packet={'sources':[],'search':{'status':'failed'},'status':'no_source_evidence','evidence_sha256':'test'}
  with patch('broker.collect_web',return_value=packet) as collect,patch('broker.audit'),patch('broker.request') as request:
   r=broker.team_request({'action':'delegate','agent':'rachel','kind':'research','question':'Find current specs'})
  collect.assert_called_once();request.assert_not_called();self.assertIsNone(r['analysis']);self.assertEqual(r['status'],'research_incomplete')
if __name__=='__main__':unittest.main()
