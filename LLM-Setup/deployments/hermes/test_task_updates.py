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
    def test_benjamin_routes_through_louis_without_duplicate_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'paperclip-api').write_text('test-token')
            (root/'config.json').write_text(json.dumps({'company_id':'company','project_id':'project','team_agents':{'louis':'reviewer'}}))
            body={'action':'submit','kind':'coding','agent':'benjamin','description':'Build and test a script','request_id':'test:benjamin-coding'}
            issue={'id':'code-issue','identifier':'KRI-400','description':'[HQ task kind=coding]\nBuild and test a script\n\n[HQ Hermes request test:benjamin-coding]'}
            with patch.object(broker,'STATE',root),patch.object(broker,'TOKENS',root),patch.object(broker,'Path',return_value=root/'config.json'),patch.object(broker,'request',return_value=issue) as api,patch.object(broker,'audit'):
                broker.task(body);result=broker.task(body)
                self.assertEqual(api.call_args.args[1]['assigneeAgentId'],'reviewer')
                self.assertTrue(result['duplicate']);api.assert_called_once()
                with self.assertRaisesRegex(ValueError,'kind=coding'):
                    broker.task({**body,'kind':'plan'})

    def test_benjamin_roster_is_execution_only(self):
        role=broker.team_request({'action':'roster'})['agents']['benjamin']
        self.assertEqual(role['execution_mode'],'workspace');self.assertEqual(role['supervisor'],'louis')
        with self.assertRaisesRegex(ValueError,'hq_task'):
            broker.team_request({'action':'delegate','agent':'benjamin','kind':'plan','question':'Build software'})

    def test_owner_dm_stays_private_and_friend_dm_is_denied(self):
        policy={**POLICY,'maintenance_dm':{'owner_id':POLICY['owner_id'],'channel_id':'900000000000000006'}}
        origin={**ORIGIN,'chat_id':policy['maintenance_dm']['channel_id']}
        self.assertEqual(updates.origin_checked(origin,policy)['channel_id'],origin['chat_id'])
        for change in ({'user_id':'900000000000000005'},{'scope_id':POLICY['guild_id']},{'chat_id':'900000000000000007'}):
            with self.assertRaises(PermissionError):updates.origin_checked(origin|change,policy)

    def test_coding_request_routes_to_louis_and_keeps_explicit_kind(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'paperclip-api').write_text('test-token')
            (root/'config.json').write_text(json.dumps({'company_id':'company','project_id':'project','team_agents':{'louis':'coder'}}))
            body={'action':'submit','kind':'coding','description':'Build and test a script','request_id':'test:code-execution'}
            issue={'id':'code-issue','identifier':'KRI-400','description':'[HQ task kind=coding]\nBuild and test a script\n\n[HQ Hermes request test:code-execution]'}
            with patch.object(broker,'STATE',root),patch.object(broker,'TOKENS',root),patch.object(broker,'Path',return_value=root/'config.json'),patch.object(broker,'request',return_value=issue) as api,patch.object(broker,'audit'):
                broker.task(body)
                self.assertEqual(api.call_args.args[1]['assigneeAgentId'],'coder')
                self.assertTrue(api.call_args.args[1]['description'].startswith('[HQ task kind=coding]'))
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

    def test_long_unicode_result_preserves_final_link_and_recovery_marker(self):
        r=self.result();r['result_evidence']={'analysis':{'backend':'amd-gpu','model':'😀'*2500}}
        text=updates.render(r,ORIGIN['user_id'],'stable-marker')['content']
        self.assertLessEqual(len(text.encode('utf-16-le'))//2,1950)
        self.assertIn('Task update reference: stable-marker',text)
        self.assertTrue(text.endswith(updates.issue_url(r['task'])))

    def test_footer_uses_only_successful_correlated_current_turn_task_results(self):
        call={'role':'assistant','tool_calls':[{'id':'task-call','function':{'name':'hq_task'}}]}
        result={'role':'tool','tool_call_id':'task-call','content':json.dumps({'task':'KRI-320','url':updates.issue_url('KRI-320')})}
        messages=[{'role':'user','content':'Submit report'},call,result]
        self.assertTrue(updates.reply_footer(messages,'Submitted').endswith(updates.issue_url('KRI-320')))
        self.assertEqual(updates.reply_footer(messages+[{'role':'user','content':'Another question'}],'Answer'),'Answer')
        for bad in ({'error':'denied','task':'KRI-320','url':updates.issue_url('KRI-320')},
                    {'task':'KRI-320','url':'https://untrusted.example/'},[],{'task':'../../secret'}):
            self.assertEqual(updates.reply_footer(messages[:2]+[dict(result,content=json.dumps(bad))],'Answer'),'Answer')
        self.assertEqual(updates.reply_footer([messages[0],dict(result,tool_call_id='unknown')],'Answer'),'Answer')

    def test_multiple_task_footer_deduplicates_without_losing_tasks(self):
        messages=[{'role':'user','content':'Check tasks'}]
        for task in ('KRI-320','KRI-321','KRI-320'):
            messages.extend([{'role':'assistant','tool_calls':[{'id':task,'function':{'name':'hq_task'}}]},
                             {'role':'tool','tool_call_id':task,'content':json.dumps({'task':task,'url':updates.issue_url(task)})}])
        text=updates.reply_footer(messages,'Results')
        self.assertEqual(text.count(updates.issue_url('KRI-320')),1)
        self.assertTrue(text.endswith(updates.issue_url('KRI-321')))

if __name__=='__main__':unittest.main()
