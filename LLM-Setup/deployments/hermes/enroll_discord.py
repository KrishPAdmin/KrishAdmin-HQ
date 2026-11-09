#!/usr/bin/env python3
"""Interactive owner enrollment with visible local input and redacted diagnostics."""
import json,os,re,subprocess,urllib.request,urllib.error
import yaml
from pathlib import Path
ROOT=Path(__file__).resolve().parent

class EnrollmentError(Exception):
    """Only locally constructed, secret-free diagnostics may be displayed."""

class DiscordAPIError(EnrollmentError):
    def __init__(self,step,status,code=None):
        self.status=status
        text=f'{step}: Discord returned HTTP {status}'
        if code is not None:text+=f' (Discord code {code})'
        if status==401:
            hint='Discord rejected the credential. Use the token from this application\'s Bot page, not its Application ID, Public Key or OAuth2 Client Secret. If you reset the token, only the newest token works.'
        elif status==403 and step=='Channel access check':
            hint='Confirm the bot was invited to your server, then grant it View Channel in the private channel\'s permissions. Check category permission overrides too.'
        elif status in (403,404) and step=='Server membership check':
            hint='The bot cannot access this server. Confirm the Server ID and finish the bot invitation into that server.'
        elif status==404 and step=='Channel access check':
            hint='Copy the ID of the actual server text channel again, and confirm the bot can see that channel.'
        elif status==429:
            hint='Discord is rate-limiting this request. Wait before trying again; do not reset the token for this error.'
        elif status==403:
            hint='Discord refused this request. This alone does not prove the token is wrong. Share this step and status with the assistant, without the token.'
        elif status>=500:
            hint='Discord reported a server-side error. Retry later; do not reset the token for this error.'
        else:hint='Share this step and status with the assistant, without the token.'
        super().__init__(text+'.\n'+hint)

def discord_api(path,token,step):
    req=urllib.request.Request('https://discord.com/api/v10'+path,headers={
        'Authorization':'Bot '+token,
        'User-Agent':'DiscordBot (https://github.com/NousResearch/hermes-agent, 1.0)'})
    try:
        with urllib.request.urlopen(req,timeout=15) as r:return json.load(r)
    except urllib.error.HTTPError as error:
        code=None
        try:
            payload=json.loads(error.read(8192))
            candidate=payload.get('code') if isinstance(payload,dict) else None
            if type(candidate) is int:code=candidate
        except (ValueError,OSError):pass
        # Never echo error bodies, request objects, headers or credentials.
        raise DiscordAPIError(step,error.code,code) from None
    except (urllib.error.URLError,TimeoutError):
        raise EnrollmentError(step+': could not reach Discord securely. Check gateway internet/DNS connectivity.') from None

def identifier(label,default=None):
    value=input(label+(f' [{default}]' if default else '')+': ').strip() or default or ''
    if not re.fullmatch(r'\d{17,22}',value):raise ValueError('Expected a numeric Discord ID')
    return value

def owner_identifier(values,default=None):
    for attempt in range(3):
        owner=identifier('Your Discord USER ID (right-click your own profile)',default)
        if owner not in (values['guild_id'],values['application_id'],values.get('channel_id')):return owner
        print('Your user ID must differ from the server, application and channel IDs. Copy User ID from your own profile, not the server icon.')
        default=None
    raise EnrollmentError('The user ID is still an application/server/channel ID. Copy User ID from your own Discord profile and rerun.')

def invite_url(values):
    return 'https://discord.com/oauth2/authorize?client_id='+values['application_id']+'&permissions=117760&scope=bot%20applications.commands&guild_id='+values['guild_id']+'&disable_guild_select=true'

def save_draft(values):
    draft=ROOT/'profiles/concierge/discord-enrollment-draft.json'
    draft.write_text(json.dumps(values,indent=2)+'\n');draft.chmod(0o600)

def verify_discord_access(values,token):
    for attempt in range(5):
        if input('After inviting the bot and granting channel access, press Enter to verify (q to stop): ').strip().lower()=='q':
            raise EnrollmentError('Enrollment paused. Your IDs are saved; the bot has not been started.')
        try:guild=discord_api('/guilds/'+values['guild_id'],token,'Server membership check')
        except DiscordAPIError as error:
            if error.status not in (403,404):raise
            print(str(error))
            try:
                guilds=discord_api('/users/@me/guilds?limit=100',token,'Joined-server check')
                print('Servers this bot has joined (up to 100):')
                for item in guilds:print('  '+str(item['id'])+' — '+json.dumps(item.get('name','')))
                if not guilds:print('  None. Complete the invitation in your browser first.')
            except EnrollmentError:print('Joined-server list unavailable; verify the invitation in Discord.')
            values['guild_id']=identifier('Correct server ID, or Enter to keep it and retry',values['guild_id'])
            if values['owner_id']==values['guild_id']:values['owner_id']=owner_identifier(values)
            save_draft(values)
            print('Invite the bot to that server: '+invite_url(values))
            continue
        print('Bot membership confirmed in server '+json.dumps(guild.get('name',''))+'.')
        try:channel=discord_api('/channels/'+values['channel_id'],token,'Channel access check')
        except DiscordAPIError as error:
            if error.status not in (403,404):raise
            print(str(error))
            print('In Discord: right-click the private channel > Edit Channel > Permissions > add the KrishAdmin HQ bot MEMBER.')
            print('Allow View Channel, Send Messages, Read Message History, Embed Links and Attach Files; save changes. Administrator is not required.')
            print('Keep this terminal open while you make the change; the token remains in memory for this retry.')
            values['channel_id']=identifier('Correct channel ID, or Enter to keep it and retry',values['channel_id'])
            if values['owner_id']==values['channel_id']:values['owner_id']=owner_identifier(values)
            save_draft(values)
            continue
        if str(channel.get('guild_id'))!=values['guild_id']:
            raise EnrollmentError('The selected channel belongs to a different server. Copy the Server ID and channel ID from the same server.')
        if channel.get('type')!=0:
            raise EnrollmentError('Choose a normal server text channel, not a category, forum or thread.')
        print('Channel access confirmed for '+json.dumps(channel.get('name',''))+'.')
        return channel
    raise EnrollmentError('Access is still unavailable after five checks. IDs are saved; fix Discord membership/channel permissions before rerunning.')

def validated_application(application_id):
    print('Paste the BOT TOKEN below, then press Enter. Your paste will be visible in this terminal.')
    print('Submitting sends the token to Discord over HTTPS for authentication. It is not sent to the AI models.')
    for attempt in range(3):
        token=input('Bot token (visible): ').strip()
        if not token or any(c.isspace() for c in token) or token.startswith(('"',"'")):
            print('No usable token received. Paste only the token, without quotes or a Bot prefix.')
            continue
        try:app=discord_api('/oauth2/applications/@me',token,'Bot token validation')
        except DiscordAPIError as error:
            if error.status!=401:raise
            print(str(error));continue
        if str(app['id'])!=application_id:
            raise EnrollmentError('The token is valid, but belongs to a different application. Use the Application ID and Bot token from the same Developer Portal application.')
        print('Bot token accepted; application ID matches.')
        return token
    raise EnrollmentError('Token validation stopped after three attempts. Your non-secret IDs are saved for the next run.')

def main():
    os.umask(0o077)
    print('Create KrishAdmin HQ at https://discord.com/developers/applications first. Enable Message Content Intent on its Bot page.')
    draft=ROOT/'profiles/concierge/discord-enrollment-draft.json'
    prior=json.loads(draft.read_text()) if draft.exists() else {}
    if prior.get('owner_id') and prior.get('owner_id')==prior.get('guild_id'):
        print('Saved setup problem: Server ID and User ID are identical. Check BOTH: Copy Server ID from the server icon; Copy User ID from your own profile.')
    values={k:identifier(label,prior.get(k)) for k,label in [('application_id','Application ID'),('guild_id','Private SERVER ID (right-click server icon)'),('channel_id','Private hq-commands channel ID')]}
    values['owner_id']=owner_identifier(values,prior.get('owner_id'))
    saved=ROOT/'profiles/concierge/discord-enrollment.json'
    enrolled=json.loads(saved.read_text()) if saved.exists() else {}
    # Preserve explicitly granted users when re-enrolling this same private server.
    users=enrolled.get('allowed_users',[]) if enrolled.get('guild_id')==values['guild_id'] else []
    values['allowed_users']=list(dict.fromkeys([values['owner_id'],*users]))
    save_draft(values)
    token=validated_application(values['application_id'])
    print('\nOpen this invite while signed into your Discord account:')
    print(invite_url(values))
    print('Grant the bot access only to the selected private channel. Do not grant Administrator.')
    verify_discord_access(values,token)
    users=enrolled.get('allowed_users',[]) if enrolled.get('guild_id')==values['guild_id'] else []
    values['allowed_users']=list(dict.fromkeys([values['owner_id'],*users]))
    values['respond_without_mention']=bool(enrolled.get('respond_without_mention') is True and enrolled.get('guild_id')==values['guild_id'] and enrolled.get('channel_id')==values['channel_id'])
    path=ROOT/'access/discord-token';path.write_text(token+'\n');path.chmod(0o600)
    home=ROOT/'profiles/concierge';(home/'discord-enrollment.json').write_text(json.dumps(values,indent=2)+'\n')
    cfg=yaml.safe_load((home/'config.yaml').read_text())
    cfg['platforms']['discord']['enabled']=True
    cfg['platforms']['discord']['extra'].update({'dm_policy':'allowlist','allow_from':values['allowed_users'],'group_policy':'allowlist','group_allow_from':values['allowed_users'],
        'allowed_channels':[values['channel_id']],'allowed_users':values['allowed_users'],
        'allow_admin_from':[],'group_allow_admin_from':[],'user_allowed_commands':['status','hq-workspace'],
        'group_user_allowed_commands':sorted({'status',*(p.parent.name for p in (home/'skills').glob('hq-*/SKILL.md'))})})
    cfg['discord']['allowed_channels']=[values['channel_id']]
    free_channels=[values['channel_id']] if values['respond_without_mention'] else []
    cfg['discord']['free_response_channels']=free_channels
    cfg['platforms']['discord']['extra']['free_response_channels']=free_channels
    (home/'config.yaml').write_text(json.dumps(cfg,indent=2)+'\n')
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'--profile','discord','up','-d','discord-egress','concierge'],check=True)
    print('\nSaved locally and started the gateway. In the private channel, mention @KrishAdmin HQ and ask for current lab status.')
    print('Tell the assistant whether it replied so the live message/authorization checks can be completed.')

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\nCancelled.')
    except EnrollmentError as e:print('Enrollment stopped: '+str(e));raise SystemExit(1)
    except Exception as e:print('Enrollment stopped: '+type(e).__name__+'. Check the application, token and channel permissions; error details omit credentials.');raise SystemExit(1)
