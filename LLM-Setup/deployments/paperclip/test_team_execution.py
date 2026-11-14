import sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).parent/'agents'))
from hermes_team_bridge import TeamAgent,execution_requested

class TeamExecutionTests(unittest.TestCase):
    def test_human_followup_requests_execution(self):
        issue={'title':'Review software','description':'Review the code'}
        self.assertFalse(execution_requested(issue,[]))
        self.assertTrue(execution_requested(issue,[{'authorUserId':'owner','body':'Can you execute the coding job?'}]))
        self.assertFalse(execution_requested(issue,[{'authorAgentId':'model','body':'Execute the coding job'}]))

    def test_explicit_plan_only_and_draft_contract_remain_advisory(self):
        self.assertFalse(execution_requested({'title':'Build software','description':'Plan only. Do not execute.'},[]))
        self.assertFalse(execution_requested({'title':'Create script','description':'[HQ task kind=automation]\nCreate script'},[]))
        self.assertTrue(execution_requested({'title':'Develop accounting software','description':'Louis needs to develop this under Jessica supervision'},[]))

    def test_existing_child_is_reconciled_not_duplicated(self):
        agent=object.__new__(TeamAgent);agent.issue={'id':'parent'}
        child={'id':'child','identifier':'KRI-999','status':'in_progress'}
        agent.execution_children=Mock(return_value=[child]);agent.api=Mock()
        result=agent.delegate_coding([{'content':'implement'}],[])
        self.assertIn('KRI-999',result[0]);agent.api.assert_not_called()

    def test_finished_child_evidence_reaches_supervisor(self):
        agent=object.__new__(TeamAgent);agent.issue={'id':'parent'}
        agent.execution_children=Mock(return_value=[{'id':'child','status':'done'}])
        agent.api=Mock(return_value=[{'body':'Actual files attached; 20 tests passed'}])
        messages=[{'content':'implement'}]
        self.assertIsNone(agent.delegate_coding(messages,[]))
        self.assertIn('20 tests passed',messages[-1]['content'])

    def test_pending_execution_cannot_be_marked_as_finished_analysis(self):
        agent=object.__new__(TeamAgent);agent.issue={'id':'parent'}
        agent.agent_id='supervisor'
        agent.coding_child={'id':'child','status':'todo','assigneeAgentId':'coder'}
        agent.require_active_run=Mock();agent.api=Mock()
        agent.review('Execution queued')
        payload=agent.api.call_args.args[2]
        self.assertEqual(payload['status'],'blocked');self.assertEqual(payload['blockedByIssueIds'],['child'])
        self.assertEqual(payload['unblockDescriptor']['owner'],{'agentId':'supervisor'})

if __name__=='__main__':unittest.main()
