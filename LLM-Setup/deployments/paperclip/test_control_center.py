import hashlib,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent/'agents'))
import codex_guard,operator_policy,connected_tools,local_agent

class ControlTests(unittest.TestCase):
 def test_missing_or_invalid_policy_blocks_external_dispatch(self):
  with tempfile.TemporaryDirectory() as d,patch.object(operator_policy,'ROOT',Path(d)):
   self.assertEqual(operator_policy.policy('company')['externalAI'],'disabled')
   (Path(d)/'company.json').write_text('{bad')
   self.assertFalse(operator_policy.policy('company')['autoEscalate'])
 def test_packet_contains_only_selected_task_fields(self):
  text=codex_guard.packet_for({'title':'Test','description':'password=private-value\napi_key=sk-abcdefghijklmnopqrstuv','private_history':'DO-NOT-SEND','attachments':['PRIVATE-ATTACHMENT']})
  self.assertNotIn('private-value',text);self.assertNotIn('sk-abcdefghijklmnopqrstuv',text)
  self.assertNotIn('DO-NOT-SEND',text);self.assertNotIn('PRIVATE-ATTACHMENT',text)
 def fake(self):
  a=Mock();a.agent_id='codex';a.company_id='company';a.run_id='run';a.issue=None
  issue={'id':'9587f9ee-4c8e-5cdb-82f7-a3884153e971','assigneeAgentId':'codex','status':'todo','title':'Synthetic task','description':'Reply READY','responsibleUserId':'human'}
  def api(method,path,body=None):
   if path=='/heartbeat-runs/run':return {'contextSnapshot':{'issueId':issue['id']}}
   if method=='GET' and path.endswith('/interactions'):return []
   if method=='GET' and path=='/issues/'+issue['id']:return issue
   if method=='POST' and path.endswith('/interactions'):return {'id':'confirmation','status':'pending'}
   return {}
  a.api.side_effect=api;return a,issue
 def test_pending_approval_never_contacts_codex_worker(self):
  a,i=self.fake()
  with patch.object(codex_guard.local_agent,'Agent',return_value=a),patch.object(codex_guard,'policy',return_value={'externalAI':'ask'}),patch.object(codex_guard.sys,'stdin',io.StringIO('PRIVATE NATIVE PROMPT MUST NOT BE FORWARDED')),patch.object(codex_guard.urllib.request,'urlopen') as network:
   self.assertEqual(codex_guard.main(),0);network.assert_not_called()
  creation=next(c.args[2] for c in a.api.call_args_list if c.args[0]=='POST' and c.args[1].endswith('/interactions'))
  self.assertEqual(creation['resolverPolicy'],'human_only');self.assertIn('Exact packet',creation['payload']['detailsMarkdown'])
  self.assertNotIn('PRIVATE NATIVE PROMPT',creation['payload']['detailsMarkdown'])
 def test_disabled_policy_blocks_even_an_assigned_task(self):
  a,i=self.fake()
  with patch.object(codex_guard.local_agent,'Agent',return_value=a),patch.object(codex_guard,'policy',return_value={'externalAI':'disabled'}),patch.object(codex_guard.sys,'stdin',io.StringIO('ignored')),patch.object(codex_guard.urllib.request,'urlopen') as network:
   codex_guard.main();network.assert_not_called()
  self.assertFalse(any(c.args[0]=='POST' and c.args[1].endswith('/interactions') for c in a.api.call_args_list))
  self.assertTrue(any(c.args[0]=='PATCH' and c.args[2].get('status')=='blocked' for c in a.api.call_args_list))
 def test_changed_task_requires_a_different_packet_hash(self):
  a={'title':'Task','description':'original'};b={**a,'description':'changed'}
  self.assertNotEqual(hashlib.sha256(codex_guard.packet_for(a).encode()).digest(),hashlib.sha256(codex_guard.packet_for(b).encode()).digest())
 def test_mcp_discovery_excludes_writes_and_control_plane_tools(self):
  tools=[{'name':'safe','risk':'read','providerType':'mcp_remote_http'},{'name':'send_mail','risk':'write','providerType':'mcp_remote_http'},{'name':'control_plane','risk':'read','providerType':'paperclip_self'}]
  a=Mock();a.api_base='http://localhost'
  with patch.object(local_agent,'request',return_value=tools):self.assertEqual([x['name'] for x in connected_tools.visible_tools(a,{'X-Paperclip-Tool-Gateway-Token':'private'})],['safe'])
 def test_gateway_credentials_never_enter_local_model_messages(self):
  a=Mock();a.headers={};a.issue={'id':'issue'};a.company_id='company';a.api.side_effect=[{'token':'PRIVATE-GATEWAY-TOKEN','sessionId':'s'},{},{}]
  results=[{'message':{'role':'assistant','content':'','tool_calls':[{'function':{'name':'read_item','arguments':{}}}]}},{'done':True,'message':{'role':'assistant','content':'Observed item'},'prompt_eval_count':4,'eval_count':2}]
  seen=[]
  def model(body):seen.append(json.loads(json.dumps(body)));return results.pop(0)
  with patch.object(connected_tools,'visible_tools',return_value=[{'name':'read_item','description':'Read item','parametersSchema':{'type':'object'}}]),patch.object(connected_tools,'call',return_value={'result':'synthetic item'}):
   result=connected_tools.complete(a,{'messages':[{'role':'system','content':'Do work'},{'role':'user','content':'Read item'}]},model)
  self.assertEqual(result['message']['content'],'Observed item');self.assertNotIn('PRIVATE-GATEWAY-TOKEN',json.dumps(seen))
 def test_mcp_invented_tool_is_not_executed(self):
  a=Mock();a.headers={};a.issue={'id':'issue'};a.api.return_value={'token':'secret','sessionId':'s'}
  with patch.object(connected_tools,'visible_tools',return_value=[{'name':'read_item','description':'read'}]),patch.object(connected_tools,'call') as call:
   with self.assertRaisesRegex(RuntimeError,'outside its permitted'):
    connected_tools.complete(a,{'messages':[{'role':'system','content':'Do work'}]},lambda b:{'message':{'tool_calls':[{'function':{'name':'delete_everything','arguments':{}}}]}})
   call.assert_not_called()
if __name__=='__main__':unittest.main()
