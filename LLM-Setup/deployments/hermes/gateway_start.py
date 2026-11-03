"""Load secrets only into the Discord gateway process, after explicit enrollment."""
import json,os,re,sys
from pathlib import Path
config=json.loads(Path('/profile/discord-enrollment.json').read_text())
os.environ['OPENAI_API_KEY']=Path('/run/access/identity').read_text().strip()
os.environ['OPENAI_BASE_URL']='http://broker:8080/v1'
os.environ['DISCORD_BOT_TOKEN']=Path('/run/access/discord-token').read_text().strip()
users=list(dict.fromkeys([config['owner_id'],*config.get('allowed_users',[])]))
if not users or any(not isinstance(user,str) or not re.fullmatch(r'\d{17,22}',user) for user in users):
    raise SystemExit('Invalid Discord user allowlist; gateway not started.')
os.environ['DISCORD_ALLOWED_USERS']=','.join(users)
os.environ['DISCORD_ALLOWED_CHANNELS']=config['channel_id']
os.environ['DISCORD_ALLOW_ALL_USERS']='false'
os.environ['DISCORD_REQUIRE_MENTION']='true'
os.environ['DISCORD_FREE_RESPONSE_CHANNELS']=config['channel_id'] if config.get('respond_without_mention') is True else ''
os.environ['DISCORD_HISTORY_BACKFILL']='false'
os.execv(sys.executable,[sys.executable,'-m','hermes_cli.main','gateway','run'])
