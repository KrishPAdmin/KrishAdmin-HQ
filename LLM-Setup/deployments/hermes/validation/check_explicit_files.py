"""Pinned gateway integration: explicit file bytes and source-only delivery, no network."""
import asyncio,hashlib,importlib,json,sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from gateway.config import Platform,load_gateway_config
import gateway.run as run
from gateway.platforms.base import BasePlatformAdapter
from plugins.platforms.discord.adapter import DiscordAdapter
sys.path.insert(0,'/profile/plugins')
f=importlib.import_module('hq-operations.file_delivery');f.install()
async def main():
 p=Path('/profile/cache/documents/drafts/maintenance-check-123456789abc.py');p.write_bytes(b'print("attachment verified")\n')
 try:
  with patch('gateway.session_context.get_session_env',return_value='discord'):value=f.send_file({'file_id':p.name})
  messages=[{'role':'assistant','tool_calls':[{'id':'file1','type':'function','function':{'name':'hq_send_file','arguments':json.dumps({'file_id':p.name})}}]}, {'role':'tool','tool_call_id':'file1','content':value}]
  tags,_=run._collect_auto_append_media_tags(messages)
  assert tags==['MEDIA:'+str(p)],tags
  paths,clean=BasePlatformAdapter.extract_media('Maintenance file.\n'+tags[0])
  assert paths[0][0]==str(p),(paths,clean)
  a=DiscordAdapter(load_gateway_config().platforms[Platform.DISCORD]);a._client=object()
  sent=[]
  async def send(**kwargs):
   sent.append(kwargs['files'][0].fp.read());return SimpleNamespace(id=123,attachments=[SimpleNamespace(id=456)])
  ch=SimpleNamespace(id=900000000000000006,filesize_limit=8*1024*1024,guild=None,send=AsyncMock(side_effect=send))
  a._resolve_channel=AsyncMock(return_value=ch)
  result=await a.send_document(str(ch.id),str(p),caption='Maintenance verification')
  assert result.success and sent==[p.read_bytes()],(result,sent)
  a._resolve_channel.assert_called_with(str(ch.id))
  print(json.dumps({'passed':True,'checks':['explicit send tool','automatic current-turn attachment','Python extension recognized','native Discord attachment bytes','original destination preserved'],'network_messages':0}))
 finally:p.unlink(missing_ok=True)
asyncio.run(main())
