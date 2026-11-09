#!/usr/bin/env python3
"""Operator-assisted per-user OAuth enrollment with loopback callback and PKCE."""
import argparse,base64,hashlib,json,secrets,time,urllib.parse
from http.server import BaseHTTPRequestHandler,HTTPServer
from pathlib import Path
from google_workspace import ROOT,SCOPES,http,save_account,account_path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user',required=True,help='Enrolled Discord user ID')
    p.add_argument('--client',required=True,type=Path,help='Private Google Desktop OAuth client JSON path')
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--replace',action='store_true',help='Explicitly replace this user’s existing account')
    args=p.parse_args()
    policy=json.loads((ROOT/'profiles/concierge/discord-enrollment.json').read_text())
    if args.user not in {policy['owner_id'],*policy.get('allowed_users',[])}:p.error('User is not enrolled in Discord')
    if account_path(args.user).exists() and not args.replace:p.error('Account already connected; use --replace deliberately')
    client=json.loads(args.client.read_text()).get('installed')
    if not client or not client.get('client_id') or not client.get('client_secret'):p.error('A Desktop OAuth client is required')
    state=secrets.token_urlsafe(32);verifier=secrets.token_urlsafe(64)
    challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')
    redirect='http://127.0.0.1:'+str(args.port)+'/callback';answer={}
    class Callback(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            url=urllib.parse.urlsplit(self.path);query=urllib.parse.parse_qs(url.query)
            if url.path!='/callback' or query.get('state')!=[state]:
                self.send_response(400);self.end_headers();self.wfile.write(b'Invalid OAuth callback.');return
            answer.update(code=query.get('code',[None])[0],error=query.get('error',[None])[0])
            self.send_response(200);self.end_headers();self.wfile.write(b'Authorization received. Check the HQ terminal for the verified account before using the bot.')
    with HTTPServer(('127.0.0.1',args.port),Callback) as server:
        server.timeout=2
        url='https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode({'client_id':client['client_id'],'redirect_uri':redirect,
            'response_type':'code','scope':' '.join(SCOPES),'access_type':'offline','prompt':'consent select_account','state':state,
            'code_challenge':challenge,'code_challenge_method':'S256'})
        print('If your browser is on another computer, first forward its localhost port '+str(args.port)+' to HQ with SSH.',flush=True)
        print('This enrollment binds the selected Google account to Discord user '+args.user+'.',flush=True)
        print(url,flush=True)
        deadline=time.monotonic()+600
        while not answer and time.monotonic()<deadline:server.handle_request()
    if not answer.get('code'):raise SystemExit('OAuth not completed; no account saved.')
    token=http('https://oauth2.googleapis.com/token','POST',{'client_id':client['client_id'],'client_secret':client['client_secret'],
        'code':answer['code'],'code_verifier':verifier,'redirect_uri':redirect,'grant_type':'authorization_code'},form=True)
    if not token.get('refresh_token') or not set(SCOPES)<=set(token.get('scope','').split()):raise SystemExit('Required consent or refresh token missing; no account saved.')
    profile=http('https://gmail.googleapis.com/gmail/v1/users/me/profile',headers={'Authorization':'Bearer '+token['access_token']})
    print('Google account selected: '+profile['emailAddress'])
    # This operator confirmation prevents accidentally binding one person's
    # account to another enrolled Discord identity during assisted setup.
    if input('Type the Google account address to confirm this user/account binding: ').strip().lower()!=profile['emailAddress'].lower():
        raise SystemExit('Binding not confirmed; no account saved.')
    save_account(args.user,{'email':profile['emailAddress'],'client_id':client['client_id'],'client_secret':client['client_secret'],
        'access_token':token['access_token'],'refresh_token':token['refresh_token'],'expires_at':time.time()+token['expires_in'],'scopes':SCOPES})
    print('Connected. Ask the bot for Workspace status in a private DM. No email or calendar changes were made.')

if __name__=='__main__':main()
