import os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parent/'agents'))
from review_details import build_review,compute_markdown,readable_result
import local_agent

class ReviewDetailsTests(unittest.TestCase):
    def setUp(self):self.issue={'id':'i','identifier':'KRI-262','title':'Network Scan','description':'Scan my network and verify logs'}
    def test_network_review_calls_out_unfinished_log_verification(self):
        content='TCP connect discovery only\n- 192.0.2.1: TCP 22\n- 192.0.2.1: TCP 22\n- 192.0.2.2: TCP 443'
        e={'kind':'Python / CPU','model_inference':False,'location':'HQ'}
        r=build_review(self.issue,content,e)
        self.assertIn('2 addresses',r['payload']['prompt'])
        self.assertIn('NOT verified',r['payload']['prompt'])
        self.assertIn('Partial completion',r['summary'])
        self.assertEqual(r['payload']['acceptLabel'],'Accept discovery only')
        for section in ('Original request','Findings','Missing work and limits','Compute used','What each choice means','Result and evidence'):self.assertIn(section,r['payload']['detailsMarkdown'])
        self.assertIn('None — no model inference',r['payload']['detailsMarkdown'])
    def test_historical_unknown_compute_is_not_guessed(self):
        text=compute_markdown();self.assertIn('Not recorded',text);self.assertNotIn('NVIDIA-GPU',text)
    def test_duplicate_machine_json_is_removed_but_artifact_links_survive(self):
        text=readable_result('Findings\n## Compute used\n\n| Field | Value |\n| Model | none |\n\nDeliverables: [report.md](/report)\nobservations.json: {"big":"duplicate"}\nMore real findings')
        self.assertIn('[report.md]',text);self.assertIn('More real findings',text)
        self.assertNotIn('duplicate',text);self.assertNotIn('| Model',text)
    def test_schema_text_limits(self):
        i={**self.issue,'title':'t'*1000,'description':'d'*50000}
        r=build_review(i,'Evidence\n'*10000)
        self.assertLessEqual(len(r['title']),240);self.assertLessEqual(len(r['summary']),1000)
        self.assertLessEqual(len(r['payload']['prompt']),1000);self.assertLessEqual(len(r['payload']['detailsMarkdown']),20000)
    def test_future_review_includes_evidence_in_decision_payload(self):
        env={'PAPERCLIP_AGENT_ID':'a','PAPERCLIP_COMPANY_ID':'c','PAPERCLIP_RUN_ID':'r','PAPERCLIP_API_URL':'http://localhost','PAPERCLIP_API_KEY':'test'}
        with patch.dict(os.environ,env):a=local_agent.Agent()
        a.issue={**self.issue,'responsibleUserId':'owner'}
        a.execution_evidence={'kind':'Deterministic Python tool / CPU','model_inference':False,'location':'HQ','run_id':'r'}
        with patch.object(a,'internal_handoff',return_value=False),patch.object(a,'api',side_effect=[{'id':'decision'},{}]) as api:
            a.review('TCP connect discovery only\n- 192.0.2.1: TCP 22')
        payload=api.call_args_list[0].args[2]
        self.assertEqual(payload['addresseeUserId'],'owner');self.assertEqual(payload['continuationPolicy'],'none')
        self.assertIn('Compute used',payload['payload']['detailsMarkdown'])
        self.assertIn('Request log verification',payload['payload']['rejectLabel'])
        self.assertIn('## Compute used',api.call_args_list[1].args[2]['comment'])
if __name__=='__main__':unittest.main()
