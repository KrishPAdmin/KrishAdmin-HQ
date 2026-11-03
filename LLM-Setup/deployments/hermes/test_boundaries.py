import importlib.util,json,tempfile,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
import broker
ROOT=Path(__file__).resolve().parent

class PolicyTests(unittest.TestCase):
    def payload(self,backend):return {'model':broker.BACKENDS[backend][3],'messages':[{'role':'user','content':'test'}]}
    def test_amd_gpu_has_no_tools(self):
        body=self.payload('amd-gpu');body['tools']=[{'type':'function','function':{'name':'browse'}}]
        with self.assertRaises(PermissionError):broker.validate_inference('analyst',body)
    def test_amd_gpu_rejects_tool_transcripts(self):
        body=self.payload('amd-gpu');body['messages'].append({'role':'tool','content':'forbidden'})
        with self.assertRaises(PermissionError):broker.validate_inference('analyst',body)
    def test_identity_cannot_switch_model(self):
        with self.assertRaises(PermissionError):broker.validate_inference('analyst',self.payload('nvidia-gpu'))
    def test_nvidia_gpu_cannot_request_arbitrary_tool(self):
        body=self.payload('nvidia-gpu');body['tools']=[{'function':{'name':'terminal'}}]
        with self.assertRaises(PermissionError):broker.validate_inference('concierge',body)
    def test_amd_gpu_evidence_allowed(self):self.assertEqual(broker.validate_inference('analyst',self.payload('amd-gpu')),'amd-gpu')
    def test_research_no_private_or_unapproved_origin(self):
        with patch.object(Path,'read_text',return_value='["docs.python.org"]'),patch('broker.socket.getaddrinfo') as dns:
            for url in ['http://docs.python.org/','https://127.0.0.1/','https://docs.python.org.evil.example/','https://user:secret@docs.python.org/']:
                with self.assertRaises(PermissionError):broker.research([url])
            dns.assert_not_called()
    def test_dns_rebinding_private_address_denied(self):
        with patch.object(Path,'read_text',return_value='["docs.python.org"]'),patch('broker.socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(PermissionError):broker.research(['https://docs.python.org/'])
    def test_live_analyst_cannot_collect(self):
        for route,body in [('/status',{}),('/research',{'urls':['https://docs.python.org/']}),('/task',{'action':'submit'}),('/files',{'action':'list'}),('/analyze',{}),('/team',{'action':'roster'}),('/knowledge',{'section':'index'}),('/draft',{}),('/compute',{}),('/calculate',{'expression':'1+1'}),('/diagnostics',{'target':'amd-gpu','check':'gpu'})]:
            req=urllib.request.Request('http://127.0.0.1:18880'+route,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+(ROOT/'access/analyst').read_text().strip()})
            with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
            self.assertEqual(caught.exception.code,403)
    def test_live_anonymous_denied(self):
        req=urllib.request.Request('http://127.0.0.1:18880/status',data=b'{}')
        with self.assertRaises(urllib.error.HTTPError) as caught:urllib.request.urlopen(req)
        self.assertEqual(caught.exception.code,403)

if __name__=='__main__':unittest.main(verbosity=2)
