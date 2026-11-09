import json,unittest
from unittest.mock import patch
import broker

class StatusReportTests(unittest.TestCase):
    def body(self):
        return {'model':'qwen3.5:9b','tools':[{'function':{'name':'hq_status'}}],
                'messages':[{'role':'assistant','content':'Old incorrect claim: temperature tools unavailable; GPU broken.'},
                            {'role':'user','content':'can you give me a status update, and give me the temps my systems are sitting at'}]}
    def test_current_request_always_collects_status_and_temperatures(self):
        r=broker.measured_status(self.body())
        self.assertEqual([json.loads(c['function']['arguments'])['view'] for c in r['choices'][0]['message']['tool_calls']],['full','temperatures'])
    def test_current_values_not_old_history_or_model_claims(self):
        b=self.body();request=broker.measured_status(b)['choices'][0]['message'];b['messages'].append(request)
        values=[{'collected_at':'now','hosts':{'hq':{'memory':{'MemTotal_bytes':16*2**30,'MemAvailable_bytes':12*2**30},'root_disk':{'used_percent':35}}},'assessment':{'alerts':[]},'gpu_api':[]},
                {'measurements':{'amd-gpu':{'checked_at_utc':'now','checks':{'amd':{'status':'observed','output':json.dumps({'card0':{'Temperature (Sensor edge) (C)':'26'},'card1':{'Temperature (Sensor edge) (C)':'31'}})}}}}}]
        for call,value in zip(request['tool_calls'],values):b['messages'].append({'role':'tool','tool_call_id':call['id'],'content':json.dumps(value)})
        with patch('broker.audit'):text=broker.measured_status(b)['choices'][0]['message']['content']
        for expected in ('12.0/16.0 GiB RAM available (25.0% used)','card0: edge 26.0 °C','card1: edge 31.0 °C'):self.assertIn(expected,text)
        self.assertNotIn('GPU broken',text)
    def test_unrelated_or_explanatory_requests_keep_model_route(self):
        for prompt in ('Research temperature sensors','Why did the old status and temperatures response fail?','Create a task to repair status and temps'):
            b=self.body();b['messages'][-1]['content']=prompt;self.assertIsNone(broker.measured_status(b))
    def test_errors_do_not_become_success(self):
        b=self.body();request=broker.measured_status(b)['choices'][0]['message'];b['messages'].append(request)
        for call in request['tool_calls']:b['messages'].append({'role':'tool','tool_call_id':call['id'],'content':'{"error":503}'})
        with patch('broker.audit'):text=broker.measured_status(b)['choices'][0]['message']['content']
        self.assertIn('Status collection failed',text);self.assertIn('Temperature collection failed',text)

if __name__=='__main__':unittest.main()
