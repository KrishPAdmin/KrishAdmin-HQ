import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import broker,file_service
from capabilities import prompt_for,calculate
from team import TEAM

class CapabilityTests(unittest.TestCase):
    def test_exact_financial_arithmetic(self):
        self.assertEqual(calculate('0.1+0.2')['result'],'0.3')
        self.assertEqual(calculate('(1250-900)/1250*100')['result'],'28.00')
    def test_calculator_cannot_execute_code_or_unbounded_powers(self):
        for text in ('__import__("os").system("id")','(1).__class__','2**100000','1/0','1e999999999','2**1e999999999'):
            with self.assertRaises(ValueError):calculate(text)
    def test_named_model_identities_cannot_switch_model(self):
        for name,role in TEAM.items():
            body={'model':role['model'],'messages':[{'role':'user','content':'test'}]}
            self.assertEqual(broker.validate_inference(name,body),role['backend'])
            body['model']='unapproved'
            with self.assertRaises(PermissionError):broker.validate_inference(name,body)
    def test_every_named_specialist_is_tool_free(self):
        for name,role in TEAM.items():
            body={'model':role['model'],'messages':[{'role':'user','content':'test'}],'tools':[{'function':{'name':'hq_status'}}]}
            with self.assertRaises(PermissionError):broker.validate_inference(name,body)
    def test_large_input_rejected_without_truncation(self):
        with self.assertRaisesRegex(ValueError,'no content was silently truncated'):prompt_for('code_review','review',{'text':'x'*60000})
    def test_upload_paths_and_symlinks_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(file_service,'ROOT',Path(d)):
            for name in ('/etc/passwd','../../access/discord-token','doc_aaaaaaaaaaaa_../secret.py'):
                with self.assertRaises(ValueError):file_service.upload(name)
            p=Path(d)/'doc_aaaaaaaaaaaa_test.py';p.symlink_to('/etc/passwd')
            with self.assertRaises(ValueError):file_service.upload(p.name)
    def test_secret_and_archive_files_rejected(self):
        with tempfile.TemporaryDirectory() as d,patch.object(file_service,'ROOT',Path(d)):
            for name in ('doc_aaaaaaaaaaaa_.env','doc_aaaaaaaaaaaa_secrets.zip'):
                p=Path(d)/name;p.write_text('test')
                with self.assertRaises(ValueError):file_service.upload(name)
    def test_uploaded_code_is_read_not_executed(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'test.py';p.write_text("raise RuntimeError('DO NOT EXECUTE')")
            self.assertIn('DO NOT EXECUTE',file_service.extract(p)['text'])
    def test_analysis_defaults_to_amd_gpu_and_preserves_file_scope(self):
        chunk={'file_id':'doc_aaaaaaaaaaaa_code.py','sha256':'hash','text':'print(1)','offset':0,'next_offset':8,'extracted_characters':100,'extraction_truncated':False,'validation':{'status':'passed'}}
        with patch.object(broker,'uploaded',return_value=chunk),patch.object(broker,'run_worker',return_value={'backend':'amd-gpu','run_id':'fixture'}) as run,patch.object(broker,'audit'):
            result=broker.analyze({'kind':'code_review','question':'review','file_id':chunk['file_id']})
            self.assertEqual(run.call_args.args[0],'analyst')
            self.assertEqual(result['evidence']['reviewed_span']['next_offset'],8)
    def test_team_roster_names_and_reporting_lines(self):
        result=broker.team_request({'action':'roster'})
        self.assertEqual(set(result['agents']),{'jessica','harvey','mike','louis','rachel','donna'})
        self.assertEqual(result['agents']['harvey']['reports_to'],'jessica')
    def test_named_delegation_uses_fixed_worker(self):
        result={'backend':'amd-gpu','model':TEAM['louis']['model'],'run_id':'test'}
        with patch.object(Path,'read_text',return_value='fake'),patch.object(broker,'request',return_value=result) as request,patch.object(broker,'audit'):
            broker.team_request({'action':'delegate','agent':'louis','kind':'code_review','question':'review','text':'print(1)'})
            self.assertEqual(request.call_args.args[0],'http://louis:8080/run')
    def test_unknown_agent_and_runbook_paths_rejected(self):
        with self.assertRaises(ValueError):broker.team_request({'action':'delegate','agent':'../../etc'})
        with self.assertRaises(ValueError):broker.knowledge({'section':'../../access/discord-token'})
    def test_python_syntax_validation_never_executes_code(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'code.py';p.write_text('raise RuntimeError("not executed")')
            self.assertEqual(file_service.validate_syntax(p)['status'],'passed')
            p.write_text('def invalid(:')
            self.assertEqual(file_service.validate_syntax(p)['status'],'failed')

if __name__=='__main__':unittest.main()
