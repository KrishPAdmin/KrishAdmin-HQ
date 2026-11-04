"""Run inside concierge: native MCP/model/attachment integration, no Discord sends.

Attachment events below are fixtures, not a claim of a real user upload.
"""
import asyncio,json,sys,time,os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
os.environ['DISCORD_BOT_TOKEN']=Path('/run/access/discord-token').read_text().strip()
from tools.mcp_tool_discovery import discover_mcp_tools
discover_mcp_tools()
from run_agent import AIAgent

mode=sys.argv[1] if len(sys.argv)>1 else 'discovery'
events=[]
def completed(*args,**kwargs):
    if len(args)>=3:events.append({'tool':args[1],'arguments':args[2]})
agent=AIAgent(model='qwen3.5:9b',provider='custom',api_mode='chat_completions',base_url='http://broker:8080/v1',
    api_key=Path('/run/access/identity').read_text().strip(),enabled_toolsets=['hq_ops','mcp-research','mcp-workbench'],quiet_mode=True,
    skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=8,max_tokens=1400,tool_complete_callback=completed)
names=[t.get('function',t).get('name') for t in agent.tools]
expected={'mcp__research__search','mcp__research__read_page','mcp__workbench__check_system','mcp__workbench__review_file','mcp__workbench__plan_automation'}
assert expected.issubset(names),names
assert len(names)==17,names
from gateway.platform_registry import platform_registry
from gateway.config import Platform,load_gateway_config
adapter=platform_registry.create_adapter('discord',load_gateway_config().platforms[Platform.DISCORD])
assert adapter is not None
loaded=type(adapter)
assert getattr(loaded._collect_attachment_media,'_hq_bounded',False),'Actual gateway adapter was not patched'

if mode=='discovery':
    print(json.dumps({'tools':names,'actual_discord_adapter_bounded':True,'messages_sent':0}));sys.exit(0)
if mode=='weather':
    prompt='Can you search how the weather is in Toronto, Canada now? If you do not know, ask Jessica and her team to work on it. Include a source and the weather timestamp.'
elif mode=='file':
    async def fixture():
        # Exercise the actual adapter's authenticated Attachment.read -> cache -> file_id handoff.
        from gateway.config import Platform,load_gateway_config
        adapter=loaded(load_gateway_config().platforms[Platform.DISCORD])
        content=b'def average(values):\n    return sum(values) / len(values)\n'
        att=SimpleNamespace(filename='hq-validation-review.py',content_type='text/plain',size=len(content),read=AsyncMock(return_value=content))
        urls,types,inlined,note=await adapter._collect_attachment_media([att])
        att.read.assert_awaited_once();assert len(urls)==1 and not any(inlined)
        assert content.decode() not in note and Path(urls[0]).name in note
        return Path(urls[0]).name
    file_id=asyncio.run(fixture())
    prompt='Review the uploaded Python file for bugs using AMD-GPU, including a syntax check. Keep the answer short. Uploaded file_id: '+file_id
elif mode=='research':
    prompt='Research how Python asyncio TaskGroup handles child task failures using current official documentation. Use AMD-GPU for the analysis, cite the source URL, and keep the answer under 180 words.'
elif mode=='checker':
    prompt='Run the AMD-GPU checker workflow with GPU and processes checks and interpret the fresh results using AMD-GPU. Include the actual compute receipt; do not create a Paperclip task.'
elif mode=='automation':
    prompt='Ask Louis to design a small idempotent disk-space checker automation for internal work. Include dry-run behavior and validation. Use AMD-GPU, keep it concise, and do not deploy it.'
else:raise ValueError('Unknown validation mode')
start=time.monotonic()
result=agent.run_conversation(prompt,system_message=Path('/profile/SOUL.md').read_text())
out={'mode':mode,'completed':result.get('completed'),'response':result.get('final_response'),'events':events,'seconds':round(time.monotonic()-start,2),'messages_sent':0,'attachment_source':'synthetic native adapter event' if mode=='file' else None}
Path('/profile/validation-cloud-'+mode+'.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
assert out['completed'] and out['response'] and events
if mode=='weather':assert any(e['tool']=='mcp__research__weather' for e in events)
elif mode=='file':
    assert any(e['tool'] in ('mcp__workbench__review_file','hq_analyze') and e['arguments'].get('file_id')==file_id for e in events)
    Path('/profile/cache/documents',file_id).unlink(missing_ok=True)
elif mode=='research':
    assert any(e['tool']=='hq_research' for e in events)
    assert 'docs.python.org' in out['response']
elif mode=='checker':
    assert any(e['tool'] in ('mcp__workbench__check_system','hq_diagnostics') for e in events)
    assert not any(x in out['response'].lower() for x in ('gpu healthy','no leak detected','no thermal throttling observed','safe operating range','above 70','observed and healthy','normal operating range','not currently serving')), 'Unsupported diagnostic conclusion'
elif mode=='automation':assert any(e['tool']=='mcp__workbench__plan_automation' or e['tool']=='hq_team' for e in events)
