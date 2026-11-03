import importlib.util,ipaddress,json,tempfile,unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('audit',Path(__file__).resolve().parents[1]/'scripts/network/network-audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
class AuditTests(unittest.TestCase):
 def setUp(self):self.cfg={'allowed_cidrs':['192.0.2.0/24'],'max_addresses':256,'exclude':['192.0.2.7/32']}
 def test_scope_rejects_escape_and_shell_text(self):
  for value in ['8.8.8.8','203.0.113.0/24','10.0.0.0/8','192.0.2.1;id','::1','198.51.100.202']:
   with self.subTest(value=value),self.assertRaises(ValueError):audit.scope(self.cfg,[value])
 def test_excluded_address(self):
  n,e=audit.scope(self.cfg,['192.0.2.0/24']);self.assertFalse(audit.in_scope('192.0.2.7',n,e));self.assertTrue(audit.in_scope('192.0.2.8',n,e))
 def test_address_budget(self):
  with self.assertRaises(ValueError):audit.scope(self.cfg,['192.0.2.0/24','192.0.2.1'])
 def test_udp_ambiguity_and_version_hint_preserved(self):
  xml='''<nmaprun><host><status state="up"/><address addr="192.0.2.2" addrtype="ipv4"/><ports><port protocol="udp" portid="161"><state state="open|filtered"/><service name="snmp" method="table"/></port></ports></host></nmaprun>'''
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'scan.xml';p.write_text(xml);h=audit.parse_nmap(p)[0]
  self.assertEqual(h['ports'][0]['state'],'open|filtered');self.assertEqual(h['ports'][0]['detection_method'],'table')
 def test_model_must_cite_real_evidence(self):
  r={'summary':'Test','recommendations':[{'priority':'low','observation':'Test','recommendation':'Review','evidence_ids':['invented']}],'limitations':[]}
  with self.assertRaises(ValueError):audit.validate_ai(r,{'H001'})
  r['recommendations'][0]['evidence_ids']=['H001'];self.assertEqual(audit.validate_ai(r,{'H001'}),r)
 def test_baseline_ignores_moving_symlink_and_changed_coverage(self):
  report={'scope':['192.0.2.0/24'],'profile':'standard','udp_enabled':False,'tcp_ports':'22,443','excluded':[],'service_detection':False,'scan_all_addresses':False,'hosts':[]}
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);folder=root/'20260101';folder.mkdir();(folder/'evidence.json').write_text(json.dumps(report));(root/'latest').symlink_to(folder)
   compared=audit.compare(report,root)
   self.assertEqual(compared['baseline'],str(folder/'evidence.json'))
   changed={**report,'excluded':['192.0.2.2/32']}
   self.assertNotIn('baseline',audit.compare(changed,root))
 def test_redacts_obvious_tokens(self):
  self.assertNotIn('abc123',audit.clean('Authorization: Bearer abc123'))
 def test_report_distinguishes_inference(self):
  r={'finished_at':'now','scope':['192.0.2.0/24'],'profile':'standard','udp_enabled':False,'hosts':[],'findings':[],'changes':{},'limitations':['No logins'],'warnings':[]}
  s=audit.markdown(r,None);self.assertIn('not a clean bill of health',s);self.assertIn('AI analysis disabled',s)
if __name__=='__main__':unittest.main()
