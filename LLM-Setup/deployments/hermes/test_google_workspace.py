import json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import google_workspace as google
from test_github import GitHubTests

class WorkspaceOriginTests(GitHubTests):
    def envelope(self):
        import hashlib,hmac
        e=self.signed();e['origin']['chat_id']='900000000000000012';e['request']={'_service':'workspace','action':'status'}
        e['signature']=hmac.new(b'test-signing-key',__import__('github_service').canonical({k:v for k,v in e.items() if k!='signature'}),hashlib.sha256).hexdigest()
        return e
    def test_workspace_requires_verified_one_to_one_dm(self):
        import github_service as service
        e=self.envelope()
        for channel in [{'type':0},{'type':3},{'type':1,'recipients':[{'id':'someone-else'}]}]:
            with patch.object(service,'discord',return_value=channel):
                with self.assertRaises(PermissionError):service.authenticate(e,self.db,workspace=True)
        with patch.object(service,'discord',side_effect=[{'type':1,'recipients':[{'id':self.policy['owner_id']}]},self.message()]):
            self.assertEqual(service.authenticate(e,self.db,workspace=True)[0],self.policy['owner_id'])
    def test_workspace_shared_channel_denied_before_network(self):
        import github_service as service
        with patch.object(service,'discord') as net:
            with self.assertRaises(PermissionError):service.authenticate(self.signed(),self.db,workspace=True)
            net.assert_not_called()

class GoogleActionsTests(unittest.TestCase):
    user='900000000000000004';other='900000000000000005'
    def setUp(self):
        self.db=sqlite3.connect(':memory:');self.addCleanup(self.db.close)
        self.patch=patch.object(google,'account',return_value={'email':'user@example.com'})
        self.patch.start();self.addCleanup(self.patch.stop)
    def call(self,body,message='',user=None):
        return google.execute({'_service':'workspace',**body},user or self.user,message,self.db)
    def draft(self):
        return self.call({'action':'draft_email','to':'recipient@example.com','subject':'Review','text':'Draft only.'})
    def test_preview_does_not_send_and_confirmation_must_be_exact(self):
        with patch.object(google,'api') as api:
            p=self.draft();api.assert_not_called()
            for text in ('yes','please send','Explain '+p['confirmation']):
                with self.assertRaises(PermissionError):self.call({'action':'confirm','proposal_id':p['proposal_id']},text)
            api.assert_not_called()
    def test_other_user_cannot_read_or_confirm_proposal(self):
        p=self.draft()
        for action in ('proposal','confirm'):
            with self.assertRaises(PermissionError):self.call({'action':action,'proposal_id':p['proposal_id']},p['confirmation'],self.other)
    def test_account_replacement_invalidates_pending_write(self):
        p=self.draft()
        with patch.object(google,'account',return_value={'email':'different@example.com'}),patch.object(google,'api') as api:
            with self.assertRaises(ValueError):self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])
            api.assert_not_called()
    def test_confirmed_send_occurs_once(self):
        p=self.draft()
        with patch.object(google,'api',return_value={'id':'sent1'}) as api:
            self.assertEqual(self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])['status'],'completed')
            self.assertEqual(self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])['status'],'already_completed')
            api.assert_called_once()
    def test_uncertain_send_is_never_retried(self):
        p=self.draft()
        with patch.object(google,'api',side_effect=TimeoutError) as api:
            with self.assertRaises(TimeoutError):self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])
            with self.assertRaises(ValueError):self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])
            api.assert_called_once()
    def test_extra_identity_and_service_fields_rejected(self):
        with self.assertRaises(ValueError):self.call({'action':'mail_list','user':self.other})
        with self.assertRaises(PermissionError):google.execute({'action':'status'},self.user,'',self.db)
    def test_event_preview_and_confirmed_create(self):
        event={'summary':'Work block','start':'2026-11-10T09:00:00-05:00','end':'2026-11-10T10:00:00-05:00','timezone':'America/New_York','recurrence':'RRULE:FREQ=WEEKLY;COUNT=4'}
        with patch.object(google,'api',return_value={'id':'event1'}) as api:
            p=self.call({'action':'propose_event','event':event});api.assert_not_called()
            self.call({'action':'confirm','proposal_id':p['proposal_id']},p['confirmation'])
            args=api.call_args.args;self.assertEqual(args[3],'POST');self.assertEqual(len(args[4]['id']),32)
    def test_invalid_times_or_attendees_rejected(self):
        event={'summary':'Test','start':'2026-11-10T10:00:00','end':'2026-11-10T11:00:00'}
        with self.assertRaises(ValueError):google.event_payload(event)
        event.update(start='2026-11-10T10:00:00Z',end='2026-11-10T09:00:00Z')
        with self.assertRaises(ValueError):google.event_payload(event)
        event.update(end='2026-11-10T11:00:00Z',attendees=['someone@example.com'])
        with self.assertRaises(ValueError):google.event_payload(event)
    def test_email_header_injection_rejected(self):
        for updates in ({'to':'one@example.com\nBcc:other@example.com'},{'subject':'Hi\nBcc:other@example.com'}):
            with self.assertRaises(ValueError):self.call({'action':'draft_email','to':'one@example.com','subject':'Hi','text':'Body',**updates})
    def test_account_paths_cannot_cross_users_or_traverse(self):
        with self.assertRaises(PermissionError):google.account_path('../other')
        self.assertNotEqual(google.account_path(self.user),google.account_path(self.other))

if __name__=='__main__':unittest.main()
