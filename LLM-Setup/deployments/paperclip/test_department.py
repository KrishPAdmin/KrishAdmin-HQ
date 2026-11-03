import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).parent / 'agents'))
import local_agent
import department

class DepartmentTests(unittest.TestCase):
 def setUp(self):
  self.env = patch.dict(os.environ, {'PAPERCLIP_AGENT_ID':'a','PAPERCLIP_COMPANY_ID':'c','PAPERCLIP_RUN_ID':'r','PAPERCLIP_API_URL':'http://localhost:3100','PAPERCLIP_API_KEY':'test','HQ_MODE':'coordinator','HQ_BACKEND':'nvidia-gpu'})
  self.env.start(); self.addCleanup(self.env.stop)
 def test_waiting_parent_comment_is_noop(self):
  a=local_agent.Agent(); task={'id':'i','status':'blocked','assigneeAgentId':'a'}
  with patch.object(a,'api',side_effect=[{'contextSnapshot':{'issueId':'i'}},task,local_agent.ApiError(422,'Issue is blocked by unresolved blockers')]), patch.object(a,'infer') as infer:
   a.run(); infer.assert_not_called()
 def test_other_422_errors_are_not_hidden(self):
  a=local_agent.Agent(); task={'id':'i','status':'blocked','assigneeAgentId':'a'}
  with patch.object(a,'api',side_effect=[{'contextSnapshot':{'issueId':'i'}},task,local_agent.ApiError(422,'Other validation error')]):
   with self.assertRaises(local_agent.ApiError): a.run()
 def test_plan_rejects_cycles_unknown_agents_and_empty_work(self):
  for steps in ([{'backend':'nvidia-gpu','instruction':'work','dependsOn':[0]}], [{'backend':'external','instruction':'work'}], []):
   with self.assertRaises(RuntimeError): department.validate_plan(steps, {'nvidia-gpu':'r'})
 def test_internal_handoff_requires_coordinator_provenance(self):
  a=local_agent.Agent(); a.issue={'id':'i','description':department.MARKER,'parentId':'p','createdByAgentId':'untrusted'}
  with patch.object(a,'api',return_value={'assigneeAgentId':'boss'}), patch.object(local_agent.Path,'read_text',return_value='{"coordinator":"boss"}'):
   self.assertFalse(a.internal_handoff())
   a.issue['createdByAgentId']='boss'; self.assertTrue(a.internal_handoff())
 def test_board_question_uses_records_without_model_invention(self):
  a=local_agent.Agent(); a.issue={'id':'i','identifier':'KRI-9','title':'What tasks are under review?'}
  rows=[{'identifier':'KRI-1','title':'Actual title','status':'in_review'}]
  with patch.object(a,'api',return_value=[]),patch.object(department,'config',return_value={'targets':{'nvidia-gpu':'r'}}),patch.object(department,'board_snapshot',return_value=rows),patch.object(a,'infer') as infer,patch.object(a,'review') as review:
   department.coordinate(a)
   infer.assert_not_called()
   self.assertIn('KRI-1',review.call_args.args[0]);self.assertIn('Actual title',review.call_args.args[0])
 def test_normalized_multiline_plan_round_trip(self):
  steps=[{'backend':'nvidia-gpu','instruction':'First line\nSecond line','dependsOn':[]}]
  normalized=json.dumps(steps).replace('\\n','\n')
  self.assertEqual(department.validate_plan(json.loads(normalized,strict=False),{'nvidia-gpu':'r'}),steps)
 def test_reentry_completes_missing_steps_without_duplicate_children(self):
  a=local_agent.Agent(); a.issue={'id':'i','title':'both GPUs'}
  steps=[{'backend':'nvidia-gpu','instruction':'compute','dependsOn':[]},{'backend':'amd-gpu','instruction':'review','dependsOn':[0]}]
  child={'id':'child1','parentId':'i','createdByAgentId':'a','title':'[Step 1] NVIDIA-GPU','description':department.MARKER,'status':'done'}
  calls=[]
  def api(method,path,body=None):
   calls.append((method,path,body))
   if method=='GET' and 'parentId=' in path: return [child]
   if method=='GET' and '/comments' in path: return [{'authorAgentId':'a','body':department.PLAN+json.dumps(steps)}]
   if method=='POST' and path=='/companies/c/issues': return {'id':'child2','status':'todo'}
   return {}
  with patch.object(a,'api',side_effect=api),patch.object(department,'config',return_value={'targets':{'nvidia-gpu':'r','amd-gpu':'m'}}),patch.object(a,'infer') as infer:
   department.coordinate(a); infer.assert_not_called()
  created=[c for c in calls if c[0]=='POST' and c[1]=='/companies/c/issues']
  self.assertEqual(len(created),1); self.assertEqual(created[0][2]['blockedByIssueIds'],['child1'])
  self.assertEqual(calls[-1][2]['blockedByIssueIds'],['child2'])

if __name__=='__main__': unittest.main()
