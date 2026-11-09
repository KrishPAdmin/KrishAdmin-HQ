"""Run inside concierge via stdin; exercises its pinned native adapter, no Discord traffic."""
import asyncio,importlib.util,io,json,sys
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
from plugins.platforms.discord.adapter import DiscordAdapter

spec=importlib.util.spec_from_file_location('hq_delivery','/profile/plugins/hq-operations/delivery.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.patch_delivery(DiscordAdapter)

async def main():
    adapter=object.__new__(DiscordAdapter)
    adapter._client=object();adapter._last_self_message_id={};adapter._last_overflow_preview={};adapter._reply_to_mode='first'
    adapter._resolve_channel=AsyncMock();adapter._is_forum_parent=lambda c:False
    adapter._reply_reference_for_send=lambda *a:None
    adapter._record_response_async=AsyncMock(side_effect=lambda reply,result,*args:result)
    channel=SimpleNamespace(id=123)
    sent=[];edited=[]
    async def send(**kwargs):
        record=dict(kwargs)
        if 'file' in kwargs:record['bytes']=kwargs['file'].fp.getvalue()
        sent.append(record);return SimpleNamespace(id=456)
    async def edit(**kwargs):
        edited.append({**kwargs,'bytes':kwargs['attachments'][0].fp.getvalue()})
    channel.send=AsyncMock(side_effect=send)
    channel.get_partial_message=lambda _:SimpleNamespace(edit=AsyncMock(side_effect=edit))
    adapter._resolve_channel.return_value=channel
    adapter._nonconversational_messages=SimpleNamespace(mark_many=AsyncMock())
    footer='Paperclip report KRI-360: https://paperclip.example.invalid/KRI/issues/KRI-360'
    for text in ('short reply','Paragraph. '*450):
        sent.clear();result=await adapter.send('123',text)
        assert result.success and all('file' not in msg for msg in sent)
        assert all(len(msg['content'])<=2000 for msg in sent)
    long='Full detailed report. 😀\n'*1600+'\n'+footer
    sent.clear();result=await adapter.send('123',long,metadata={'thread_id':'789','notify':True})
    assert result.success and len(sent)==1 and sent[0]['bytes']==long.encode()
    assert module.units(sent[0]['content'])<=2000 and sent[0]['content'].endswith(footer)
    adapter._resolve_channel.assert_called_with('789')
    assert not sent[0]['allowed_mentions'].everyone
    result=await adapter.edit_message('123','456',long,finalize=True)
    assert result.success and len(edited)==1 and edited[0]['bytes']==long.encode()
    assert edited[0]['content'].endswith(footer)
    sent.clear();channel.send=AsyncMock(side_effect=TimeoutError)
    result=await adapter.send('123',long)
    assert not result.success and 'uncertain' in result.error and channel.send.call_count==1
    result=await adapter.send('123','x'*(module.MAX_REPORT_BYTES+1))
    assert not result.success and '5 MiB' in result.error
    print(json.dumps({'passed':True,'checks':['native short replies','native split replies','full Markdown bytes','footer and emoji budget','thread destination','mention suppression','stream final edit','uncertain upload no second send','oversize refusal'],'discord_network_calls':0}))

asyncio.run(main())
