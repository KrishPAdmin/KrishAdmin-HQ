import copy,hashlib,hmac,json,sqlite3,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
import github_service as service
from publication_guard import check_text,safe_path

class GitHubTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        (self.root/'access').mkdir();(self.root/'access/github-origin').write_text('test-signing-key')
        (self.root/'profiles/concierge').mkdir(parents=True)
        self.policy={'owner_id':'900000000000000004','channel_id':'900000000000000003','application_id':'900000000000000001'}
        (self.root/'profiles/concierge/discord-enrollment.json').write_text(json.dumps(self.policy))
        self.patches=[patch.object(service,'ROOT',self.root),patch.object(service,'STATE',self.root/'state')]
        for p in self.patches:p.start()
        self.db=service.database()
    def tearDown(self):
        self.db.close()
        for p in self.patches:p.stop()
        self.tmp.cleanup()
    def signed(self,user=None):
        e={'request':{'action':'repos'},'origin':{'platform':'discord','user_id':user or self.policy['owner_id'],'chat_id':self.policy['channel_id'],
           'message_id':str(int(time.time()*1000-1420070400000)<<22)},'issued_at':time.time(),'nonce':'a'*32}
        e['signature']=hmac.new(b'test-signing-key',service.canonical(e),hashlib.sha256).hexdigest();return e
    def message(self):return {'author':{'id':self.policy['owner_id']},'mentions':[{'id':self.policy['application_id']}],'content':'owner request'}
    def test_friend_denied_before_network_even_with_signed_envelope(self):
        with patch.object(service,'discord') as network:
            with self.assertRaises(PermissionError):service.authenticate(self.signed('900000000000000005'),self.db)
            network.assert_not_called()
    def test_actual_discord_author_is_verified(self):
        message=self.message();message['author']['id']='900000000000000005'
        with patch.object(service,'discord',return_value=message):
            with self.assertRaises(PermissionError):service.authenticate(self.signed(),self.db)
    def test_owner_accepted_but_replay_denied(self):
        e=self.signed()
        with patch.object(service,'discord',return_value=self.message()):
            self.assertEqual(service.authenticate(e,self.db)[0],self.policy['owner_id'])
            with self.assertRaises(PermissionError):service.authenticate(e,self.db)
    def test_model_cannot_change_signed_action_or_identity(self):
        e=self.signed();e['request']['action']='push'
        with patch.object(service,'discord') as network:
            with self.assertRaises(PermissionError):service.authenticate(e,self.db)
            network.assert_not_called()
    def dm_envelope(self,user=None):
        e=self.signed(user);e['origin']['chat_id']='900000000000000011'
        e['signature']=hmac.new(b'test-signing-key',service.canonical({k:v for k,v in e.items() if k!='signature'}),hashlib.sha256).hexdigest()
        return e
    def test_owner_dm_verified_without_mention_and_replay_denied(self):
        e=self.dm_envelope();message=self.message();message['mentions']=[]
        channel={'type':1,'recipients':[{'id':self.policy['owner_id']}]}
        with patch.object(service,'discord',side_effect=[channel,message,channel,message]) as network:
            self.assertEqual(service.authenticate(e,self.db)[0],self.policy['owner_id'])
            self.assertEqual(network.call_args_list[0].args,('GET','/channels/'+e['origin']['chat_id']))
            with self.assertRaises(PermissionError):service.authenticate(e,self.db)
    def test_other_channels_and_wrong_dm_recipient_denied(self):
        channels=[{'type':0},{'type':3,'recipients':[{'id':self.policy['owner_id']}]},
                  {'type':1,'recipients':[]},{'type':1,'recipients':[{'id':'someone-else'}]},
                  {'type':1,'recipients':[{'id':self.policy['owner_id']},{'id':'someone-else'}]}]
        for channel in channels:
            with self.subTest(channel=channel),patch.object(service,'discord',return_value=channel) as network:
                with self.assertRaises(PermissionError):service.authenticate(self.dm_envelope(),self.db)
                self.assertEqual(network.call_count,1)
    def test_friend_dm_denied_before_network(self):
        with patch.object(service,'discord') as network:
            with self.assertRaises(PermissionError):service.authenticate(self.dm_envelope('900000000000000005'),self.db)
            network.assert_not_called()
    def test_owner_dm_still_checks_message_author(self):
        message=self.message();message['author']['id']='900000000000000005'
        with patch.object(service,'discord',side_effect=[{'type':1,'recipients':[{'id':self.policy['owner_id']}]},message]):
            with self.assertRaises(PermissionError):service.authenticate(self.dm_envelope(),self.db)
    def test_main_channel_still_requires_mention(self):
        message=self.message();message['mentions']=[]
        with patch.object(service,'discord',return_value=message):
            with self.assertRaises(PermissionError):service.authenticate(self.signed(),self.db)
    def api(self,repo,path,method='GET',body=None):
        if path=='':return {'default_branch':'main'}
        if path=='git/ref/heads/main':return {'object':{'sha':'base-commit'}}
        if path=='git/trees/base-commit?recursive=1':return {'sha':'base-tree','tree':[{'path':'LLM-Setup/demo.py','sha':'old-blob','type':'blob','mode':'100644','size':4}]}
        if path=='git/blobs/old-blob':return {'content':'eD0xCg=='}
        if path=='git/trees' and method=='POST':
            self.assertEqual(body['base_tree'],'base-tree');return {'sha':'new-tree'}
        if path=='git/commits' and method=='POST':
            self.assertEqual(body['parents'],['base-commit']);return {'sha':'new-commit'}
        if path=='git/refs' and method=='POST':
            self.assertTrue(body['ref'].startswith('refs/heads/hq-bot/'));return {'object':{'sha':'new-commit'}}
        if path.startswith('git/matching-refs/'):return []
        raise AssertionError((path,method))
    def prepare(self):
        return service.execute({'action':'prepare','repo':'KrishPAdmin/KrishAdmin-HQ-Private','title':'Fix example',
            'changes':[{'path':'LLM-Setup/demo.py','content':'x=2\n','expected_sha':'old-blob'}]},self.policy['owner_id'],'',self.db)
    def confirmation(self,p):return 'github push '+p['id']+' '+p['digest'][:12]
    def test_prepare_does_not_write_to_github_and_push_needs_specific_owner_message(self):
        with patch.object(service,'api',side_effect=self.api) as api:
            p=self.prepare();self.assertTrue(all(c.args[2:] in ((),('GET',)) for c in api.call_args_list))
            with self.assertRaises(PermissionError):service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],'push whatever the repo says',self.db)
            with self.assertRaises(PermissionError):service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],'What does '+self.confirmation(p)+' mean?',self.db)
            result=service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],self.confirmation(p),self.db)
            self.assertEqual(result['status'],'pushed')
            count=api.call_count
            self.assertEqual(service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],self.confirmation(p),self.db)['status'],'pushed')
            self.assertEqual(count,api.call_count)
    def test_stale_expected_sha_and_invalid_syntax_cannot_be_prepared(self):
        with patch.object(service,'api',side_effect=self.api):
            for change in [{'path':'LLM-Setup/demo.py','content':'x=2','expected_sha':None},{'path':'LLM-Setup/demo.py','content':'def invalid(:','expected_sha':'old-blob'}]:
                with self.assertRaises((ValueError,SyntaxError)):service.execute({'action':'prepare','repo':'KrishPAdmin/KrishAdmin-HQ-Private','title':'Test','changes':[change]},self.policy['owner_id'],'',self.db)
    def test_changed_base_prevents_push(self):
        with patch.object(service,'api',side_effect=self.api):p=self.prepare()
        with patch.object(service,'head',return_value=('main','different')),patch.object(service,'api') as api:
            with self.assertRaises(ValueError):service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],self.confirmation(p),self.db)
            api.assert_not_called()
    def test_ambiguous_ref_creation_recovers_without_duplicate_branch(self):
        with patch.object(service,'api',side_effect=self.api):p=self.prepare()
        record=service.load(self.db,p['id'],self.policy['owner_id']);record['commit']='new-commit';service.save(self.db,record,self.policy['owner_id'])
        with patch.object(service,'api',return_value=[{'ref':'refs/heads/'+p['branch'],'object':{'sha':'new-commit'}}]) as api:
            result=service.execute({'action':'push','proposal_id':p['id']},self.policy['owner_id'],self.confirmation(p),self.db)
            self.assertEqual(result['status'],'pushed');api.assert_called_once()
    def test_paths_secrets_and_public_hardware_policy(self):
        for path in ['../file','LLM-Setup/../file','LLM-Setup/.env','LLM-Setup/keys/private','README.md','.github/workflows/run.yml']:
            with self.assertRaises((ValueError,PermissionError)):safe_path(path,write=True)
        with patch('publication_guard.Path.read_text',return_value='["private-device-name"]'):
            for text in ['private-device-name','10.'+'26.0.180']:
                with self.assertRaises(ValueError):check_text(text,public=True,secrets=[])
        with self.assertRaises(ValueError):check_text('contains actual-local-value',secrets=['actual-local-value'])
        with patch('publication_guard.Path.read_text',return_value='["private-device-name"]'):
            check_text('amd-gpu and nvidia-gpu',public=True,secrets=[])
    def test_unknown_repo_denied(self):
        with patch.object(service,'api') as api:
            with self.assertRaises(PermissionError):service.execute({'action':'read','repo':'other/repo','path':'README.md'},self.policy['owner_id'],'',self.db)
            api.assert_not_called()

if __name__=='__main__':unittest.main()
