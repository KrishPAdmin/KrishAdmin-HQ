import json,sqlite3,unittest,tempfile
from pathlib import Path
from unittest.mock import patch
import task_updates as updates
import notify_tasks as notifier
import broker

POLICY={'owner_id':'900000000000000004','allowed_users':['900000000000000005'],
        'channel_id':'900000000000000003','guild_id':'900000000000000002','application_id':'900000000000000001'}
ORIGIN={'platform':'discord','chat_id':POLICY['channel_id'],'user_id':POLICY['owner_id']}

class NotificationTests(unittest.TestCase):
    def test_bridge_submission_retry_keeps_one_issue_and_watch(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'paperclip-api').write_text('test-token')
            (root/'policy.json').write_text(json.dumps(POLICY));(root/'config.json').write_text(json.dumps({'company_id':'company','project_id':'project','agents':{'health':'worker'}}))
            body={'action':'submit','kind':'health','description':'Check health','request_id':'test:notification','_discord_origin':ORIGIN}
            issue={'id':'issue-one','identifier':'KRI-320','description':'[HQ Hermes request test:notification]'}
            def paths(name):return root/({'/config/paperclip.json':'config.json','/discord-enrollment.json':'policy.json'}[name])
            with patch.object(broker,'STATE',root),patch.object(broker,'TOKENS',root),patch.object(broker,'Path',side_effect=paths),patch.object(broker,'request',return_value=issue) as api,patch.object(broker,'audit'):
                first=broker.task(body);second=broker.task(body)
                self.assertTrue(first['discord_updates']);self.assertTrue(second['duplicate']);self.assertIn('/issues/',first['url']);api.assert_called_once()
            with sqlite3.connect(root/'tasks.db') as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM task_watches').fetchone()[0],1)
    def database(self):
        db=sqlite3.connect(':memory:');db.row_factory=sqlite3.Row;updates.schema(db)
        updates.subscribe(db,'issue-one',updates.origin_checked(ORIGIN,POLICY));db.commit();return db
    def row(self,db):return db.execute('SELECT * FROM task_watches').fetchone()
    def result(self,status='in_review'):
        return {'task':'KRI-320','status':status,'agent_comment':'Result needs review.'}
    def test_recipient_policy_rejects_foreign_user_channel_and_server(self):
        for extra in ({'user_id':'123'},{'chat_id':'123'},{'scope_id':'123'},{'platform':'slack'}):
            with self.assertRaises(PermissionError):updates.origin_checked(ORIGIN|extra,POLICY)
        friend=updates.origin_checked(ORIGIN|{'user_id':'900000000000000005'},POLICY)
        self.assertEqual(friend['channel_id'],POLICY['channel_id'])
    def test_duplicate_subscription_is_durable_and_unique(self):
        db=self.database();updates.subscribe(db,'issue-one',updates.origin_checked(ORIGIN,POLICY))
        self.assertEqual(db.execute('SELECT COUNT(*) FROM task_watches').fetchone()[0],1)
    def test_no_message_until_result_and_no_repeat_on_poll(self):
        db=self.database()
        with patch.object(notifier,'call',return_value=self.result('todo')),patch.object(notifier,'discord') as send:
            self.assertEqual(notifier.process(db,self.row(db),POLICY,[]),'waiting');send.assert_not_called()
        with patch.object(notifier,'call',return_value=self.result()),patch.object(notifier,'discord',return_value={'id':'12345'}) as send:
            self.assertEqual(notifier.process(db,self.row(db),POLICY,[]),'delivered')
            self.assertEqual(notifier.process(db,self.row(db),POLICY,[]),'unchanged')
            send.assert_called_once();self.assertEqual(send.call_args.args[0],'POST')
    def test_later_status_edits_existing_message_and_closes_done(self):
        db=self.database()
        with patch.object(notifier,'call',return_value=self.result()),patch.object(notifier,'discord',return_value={'id':'12345'}):notifier.process(db,self.row(db),POLICY,[])
        with patch.object(notifier,'call',return_value=self.result('done')),patch.object(notifier,'discord',return_value={'id':'12345'}) as send:
            notifier.process(db,self.row(db),POLICY,[])
            self.assertEqual(send.call_args.args[:2],('PATCH','/channels/'+POLICY['channel_id']+'/messages/12345'))
            self.assertEqual(self.row(db)['closed'],1)
    def test_lost_post_response_is_reconciled_after_restart(self):
        db=self.database()
        with patch.object(notifier,'call',return_value=self.result()),patch.object(notifier,'discord',side_effect=TimeoutError):
            with self.assertRaises(TimeoutError):notifier.process(db,self.row(db),POLICY,[])
        row=self.row(db);self.assertIsNotNone(row['pending']);self.assertIsNotNone(row['attempted_at'])
        found={'id':'12345','author':{'id':POLICY['application_id']},'content':'Task update reference: '+notifier.marker_for(row)}
        with patch.object(notifier,'call') as query,patch.object(notifier,'discord',side_effect=[[found],{'id':'12345'}]) as send:
            notifier.process(db,row,POLICY,[]);query.assert_not_called()
            self.assertEqual([c.args[0] for c in send.call_args_list],['GET','PATCH'])
    def test_failure_retries_same_nonce_and_payload(self):
        db=self.database()
        with patch.object(notifier,'call',return_value=self.result()),patch.object(notifier,'discord',side_effect=notifier.DiscordError(429,30)) as first:
            with self.assertRaises(notifier.DiscordError):notifier.process(db,self.row(db),POLICY,[])
        nonce=first.call_args.args[2]['nonce']
        with patch.object(notifier,'discord',side_effect=[[],{'id':'12345'}]) as retry:
            notifier.process(db,self.row(db),POLICY,[])
            self.assertEqual(retry.call_args.args[2]['nonce'],nonce)
    def test_permission_removed_before_delivery_does_not_send(self):
        db=self.database()
        with patch.object(notifier,'discord') as send:
            with self.assertRaises(PermissionError):notifier.process(db,self.row(db),POLICY|{'owner_id':'123','allowed_users':[]},[])
            send.assert_not_called()
    def test_completed_is_not_automatic_pass_and_links_are_canonical(self):
        for status in ('in_review','done','blocked','cancelled'):
            p=updates.render(self.result(status),ORIGIN['user_id'],'marker')
            self.assertNotIn('checks passed',p['content'].lower());self.assertIn('/KRI/issues/KRI-320',p['content'])
            self.assertEqual(p['allowed_mentions']['parse'],[])
    def test_prior_idle_snapshot_is_separated_from_actual_compute(self):
        r=self.result();r['result_evidence']={'analysis':{'backend':'amd-gpu','model':'qwen72','seconds':93},'evidence':{'gpu_api':[{'loaded_models':[]}],'assessment':{'result':'no_active_observation_alerts'}}}
        content=updates.render(r,ORIGIN['user_id'],'marker')['content']
        self.assertIn('**AMD-GPU**',content);self.assertIn('before this analysis',content);self.assertNotIn('currently running',content)
    def test_output_redacts_secrets_and_suppresses_unwanted_mentions(self):
        r=self.result();r['agent_comment']='@everyone password: sensitive secret-token-value'
        p=updates.render(r,ORIGIN['user_id'],'marker',['secret-token-value'])
        self.assertNotIn('@everyone',p['content']);self.assertNotIn('sensitive',p['content']);self.assertNotIn('secret-token-value',p['content'])

if __name__=='__main__':unittest.main()
