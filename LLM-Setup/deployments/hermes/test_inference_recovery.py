import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import broker

class GPURecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);(self.root/'token').write_text('test-token')
        self.body={'model':'qwen3.5:9b','messages':[{'role':'user','content':'large prompt'}]}
        self.resident={'name':'qwen3.5:9b','size_vram':8000000000,'size':8000000000,'context_length':65536}
    def invoke(self,responses):
        real=Path
        def path(*parts):
            return self.root.joinpath(*parts[1:]) if parts[0]=='/locks' else real(*parts)
        with patch.object(broker,'Path',side_effect=path),patch.dict(broker.BACKENDS,{'nvidia-gpu':('http://test',str(self.root/'token'),None,'qwen3.5:9b')}),patch.object(broker,'request',side_effect=responses) as request,patch.object(broker,'audit',side_effect=lambda event,**kw:{'event':event,'time':'now',**kw}) as audit:
            try:result=broker.inference('operator',self.body)
            except broker.GPUUnavailable:result=None
            return result,request.call_args_list,audit.call_args_list
    def test_cpu_resident_fails_before_user_prompt(self):
        result,calls,audits=self.invoke([{'models':[{**self.resident,'size_vram':0}]}])
        self.assertIsNone(result);self.assertEqual(len(calls),1)
        self.assertEqual(audits[0].args[0],'inference_denied')
    def test_cold_cpu_load_never_evaluates_user_prompt(self):
        result,calls,_=self.invoke([{'models':[]},{'done':True},{'models':[{**self.resident,'size_vram':0}]}])
        self.assertIsNone(result)
        self.assertEqual(calls[1].args[1]['prompt'],'')
        self.assertFalse(any(c.args[0].endswith('/api/chat') for c in calls))
    def test_gpu_loss_after_generation_never_emits_success_receipt(self):
        result,_,audits=self.invoke([{'models':[self.resident]},{'done':True,'message':{'content':'answer'}},{'models':[]}])
        self.assertIsNone(result)
        self.assertFalse(any(c.args[0]=='inference' for c in audits))
    def test_verified_gpu_returns_real_receipt(self):
        result,_,_=self.invoke([{'models':[self.resident]},{'done':True,'message':{'content':'answer'},'eval_count':1},{'models':[self.resident]}])
        self.assertEqual(result['hq_receipt']['vram_bytes'],8000000000)
    def test_operational_gpu_failure_is_503(self):
        handler=object.__new__(broker.Handler)
        raw=json.dumps(self.body).encode();handler.headers={'Authorization':'Bearer test-token','Content-Length':str(len(raw))}
        handler.rfile=io.BytesIO(raw);handler.path='/v1/chat/completions'
        with patch.object(Path,'read_text',return_value='test-token'),patch.object(broker,'inference',side_effect=broker.GPUUnavailable('GPU unavailable')),patch.object(handler,'send') as send:
            handler.do_POST()
        self.assertEqual(send.call_args.args[0],503)
        self.assertEqual(send.call_args.args[1]['error']['code'],'gpu_unavailable')

if __name__=='__main__':unittest.main()
