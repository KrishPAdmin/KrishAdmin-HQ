import contextlib,io,json,unittest,urllib.error
from unittest.mock import patch
import enroll_discord as enrollment

class EnrollmentTests(unittest.TestCase):
    def error(self,status,body):
        return urllib.error.HTTPError('https://discord.com/api/v10/test',status,'rejected',{},io.BytesIO(body))

    def test_authentication_error_does_not_expose_body_or_token(self):
        secret='PRIVATE_TEST_TOKEN_DO_NOT_DISPLAY'
        error=self.error(401,json.dumps({'code':0,'message':secret}).encode())
        with patch.object(enrollment.urllib.request,'urlopen',side_effect=error):
            with self.assertRaises(enrollment.DiscordAPIError) as caught:
                enrollment.discord_api('/oauth2/applications/@me',secret,'Bot token validation')
        message=str(caught.exception)
        self.assertIn('Bot token validation',message);self.assertIn('HTTP 401',message)
        self.assertNotIn(secret,message)

    def test_channel_access_error_identifies_permissions(self):
        with patch.object(enrollment.urllib.request,'urlopen',side_effect=self.error(403,b'{"code":50001}')):
            with self.assertRaises(enrollment.DiscordAPIError) as caught:
                enrollment.discord_api('/channels/123','fake','Channel access check')
        self.assertIn('50001',str(caught.exception));self.assertIn('View Channel',str(caught.exception))

    def test_non_json_response_is_not_echoed(self):
        with patch.object(enrollment.urllib.request,'urlopen',side_effect=self.error(403,b'<html>PRIVATE_TEST_BODY</html>')):
            with self.assertRaises(enrollment.DiscordAPIError) as caught:
                enrollment.discord_api('/oauth2/applications/@me','fake','Bot token validation')
        self.assertNotIn('PRIVATE_TEST_BODY',str(caught.exception))

    def test_rejected_token_can_be_reentered_without_reentering_ids(self):
        output=io.StringIO()
        with contextlib.redirect_stdout(output),patch('builtins.input',side_effect=['fake-rejected','fake-accepted']),patch.object(enrollment,'discord_api',side_effect=[enrollment.DiscordAPIError('Bot token validation',401),{'id':'123'}]):
            self.assertEqual(enrollment.validated_application('123'),'fake-accepted')
        self.assertIn('accepted',output.getvalue());self.assertNotIn('fake-accepted',output.getvalue());self.assertNotIn('fake-rejected',output.getvalue())

    def test_rate_limit_is_not_retried_automatically(self):
        with contextlib.redirect_stdout(io.StringIO()),patch('builtins.input',return_value='fake') as prompt,patch.object(enrollment,'discord_api',side_effect=enrollment.DiscordAPIError('Bot token validation',429)):
            with self.assertRaises(enrollment.DiscordAPIError):enrollment.validated_application('123')
            self.assertEqual(prompt.call_count,1)

    def test_mismatched_application_is_clear(self):
        with contextlib.redirect_stdout(io.StringIO()),patch('builtins.input',return_value='fake'),patch.object(enrollment,'discord_api',return_value={'id':'456'}):
            with self.assertRaisesRegex(enrollment.EnrollmentError,'different application'):enrollment.validated_application('123')

    def values(self):
        return {'application_id':'900000000000000007','guild_id':'900000000000000008',
                'owner_id':'900000000000000009','channel_id':'900000000000000010'}

    def test_server_id_cannot_be_used_as_owner_id(self):
        values=self.values()
        with contextlib.redirect_stdout(io.StringIO()),patch('builtins.input',side_effect=[values['guild_id'],values['owner_id']]):
            self.assertEqual(enrollment.owner_identifier(values),values['owner_id'])

    def test_channel_access_can_be_fixed_without_reentering_token(self):
        values=self.values();guild={'name':'test'};channel={'name':'hq','type':0,'guild_id':values['guild_id']}
        responses=[guild,enrollment.DiscordAPIError('Channel access check',403,50001),guild,channel]
        output=io.StringIO()
        with contextlib.redirect_stdout(output),patch('builtins.input',side_effect=['','','']),patch.object(enrollment,'save_draft'),patch.object(enrollment,'discord_api',side_effect=responses) as api:
            self.assertEqual(enrollment.verify_discord_access(values,'PRIVATE_TEST_TOKEN'),channel)
            self.assertTrue(all(call.args[1]=='PRIVATE_TEST_TOKEN' for call in api.call_args_list))
        self.assertNotIn('PRIVATE_TEST_TOKEN',output.getvalue())
        self.assertIn('Channel access confirmed',output.getvalue())

    def test_missing_server_membership_is_checked_before_channel(self):
        values=self.values()
        with contextlib.redirect_stdout(io.StringIO()),patch('builtins.input',side_effect=['','','q']),patch.object(enrollment,'save_draft'),patch.object(enrollment,'discord_api',side_effect=[enrollment.DiscordAPIError('Server membership check',403,50001),[]]) as api:
            with self.assertRaisesRegex(enrollment.EnrollmentError,'paused'):enrollment.verify_discord_access(values,'fake')
            self.assertTrue(all(not call.args[0].startswith('/channels/') for call in api.call_args_list))

    def test_channel_from_another_server_rejected(self):
        values=self.values()
        with contextlib.redirect_stdout(io.StringIO()),patch('builtins.input',return_value=''),patch.object(enrollment,'discord_api',side_effect=[{'name':'test'},{'guild_id':'900000000000000011','type':0}]):
            with self.assertRaisesRegex(enrollment.EnrollmentError,'different server'):enrollment.verify_discord_access(values,'fake')

if __name__=='__main__':unittest.main()
