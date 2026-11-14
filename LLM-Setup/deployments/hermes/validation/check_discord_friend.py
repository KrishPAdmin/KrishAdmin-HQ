"""Run inside concierge: real ingress/auth code, synthetic events, no messages sent."""
import asyncio,datetime,json,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import discord
from gateway.config import Platform,load_gateway_config
from gateway.pairing import PairingStore
from gateway.run import GatewayRunner
from plugins.platforms.discord.adapter import DiscordAdapter

async def main():
 state=json.loads(Path('/profile/gateway_state.json').read_text())
 keys={'DISCORD_ALLOWED_USERS','DISCORD_ALLOWED_CHANNELS','DISCORD_ALLOW_ALL_USERS','DISCORD_REQUIRE_MENTION','DISCORD_HISTORY_BACKFILL','DISCORD_FREE_RESPONSE_CHANNELS'}
 for row in Path('/proc/'+str(state['pid'])+'/environ').read_bytes().split(b'\0'):
  if b'=' not in row:continue
  k,v=row.split(b'=',1)
  if k.decode() in keys:os.environ[k.decode()]=v.decode()
 r=object.__new__(GatewayRunner);r.config=load_gateway_config();r.pairing_store=PairingStore(profile='default');r.pairing_stores={'default':r.pairing_store};r._primary_profile_name='default';r._profile_adapters={}
 a=DiscordAdapter(r.config.platforms[Platform.DISCORD]);r.adapters={Platform.DISCORD:a}
 a._allowed_user_ids=a._get_allowed_users();a._allowed_role_ids=a._get_allowed_roles()
 a._client=SimpleNamespace(user=SimpleNamespace(id=900000000000000001,bot=True))
 a._text_batch_delay_seconds=0;a.handle_message=AsyncMock()
 guild=SimpleNamespace(id=900000000000000002,name='QA')
 results=[]
 cases=[('friend_plain','900000000000000005',900000000000000003,'Show current lab status',True),('friend_role','900000000000000005',900000000000000003,'<@&900000000000000013> Show current lab status',True),('friend_account','900000000000000005',900000000000000003,'<@900000000000000001> Show current lab status',True),('owner_plain','900000000000000004',900000000000000003,'Show current lab status',True),('stranger','900000000000000007',900000000000000003,'Show current lab status',False),('other_channel','900000000000000005',900000000000000007,'<@900000000000000001> Show current lab status',False)]
 for i,(name,uid,cid,text,expected) in enumerate(cases):
  a.handle_message.reset_mock()
  m=SimpleNamespace(id=900000000000000014+i,content=text,mentions=[],attachments=[],reference=None,created_at=datetime.datetime.now(datetime.timezone.utc),type=discord.MessageType.default,guild=guild,channel=SimpleNamespace(id=cid,name='QA',topic=None,guild=guild),author=SimpleNamespace(id=int(uid),name='QA',display_name='QA',bot=False))
  admitted,role=a._discord_message_admission(m,claim=False)
  handled=await a._handle_message(m,role_authorized=role,recovered=True) if admitted else False
  authorized=False
  if handled:
   event=a.handle_message.await_args.args[0];r._canonicalize(event.source,primary_home=Path('/profile'));authorized=r._is_user_authorized_for_source(event.source)
  assert bool(handled and authorized)==expected,name
  results.append({'case':name,'allowed':bool(handled and authorized),'passed':True})
 assert a.config.extra['dm_policy']=='disabled'
 result={'gateway':state['platforms']['discord']['state'],'free_response_channels':sorted(a._discord_free_response_channels()),'dm_policy':'disabled','checks':results,'messages_sent':0}
 Path('/profile/discord-friend-ingress-validation.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result))
asyncio.run(main())
