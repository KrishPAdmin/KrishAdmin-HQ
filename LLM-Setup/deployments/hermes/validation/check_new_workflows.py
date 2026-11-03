"""Run in concierge; actual model/tool loop, no Discord messages sent."""
import json,sys,time
from pathlib import Path
from run_agent import AIAgent
research='--research' in sys.argv;events=[]
def completed(*args,**kwargs):
 if len(args)>=3:events.append({'tool':args[1],'arguments':args[2]})
a=AIAgent(model='qwen3.5:9b',provider='custom',api_mode='chat_completions',base_url='http://broker:8080/v1',api_key=Path('/run/access/identity').read_text().strip(),enabled_toolsets=['hq_ops'],quiet_mode=True,skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=5,max_tokens=1200,tool_complete_callback=completed)
names=[t.get('function',t).get('name') for t in a.tools];assert 'hq_diagnostics' in names and len(names)==11
prompt='Tell Jessica to ask Rachel to research the iPhone Duo specifications. Use current official sources, and cite the technical specification page. Keep the final answer under 200 words.' if research else 'Use hq_diagnostics to check AMD-GPU GPU and ROCm versions. Report the actual collected facts, timestamp and any unavailable coverage. Keep it short; do not create a Paperclip task.'
start=time.monotonic();r=a.run_conversation(prompt,system_message=Path('/profile/SOUL.md').read_text());out={'completed':r.get('completed'),'response':r.get('final_response'),'tools':names,'events':events,'seconds':round(time.monotonic()-start,2)}
Path('/profile/validation-'+('managed-research' if research else 'ssh-diagnostics')+'.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
assert r.get('completed') and events
if research:
 assert any(e['tool']=='hq_team' and e['arguments'].get('agent')=='jessica' and e['arguments'].get('delegate_to')=='rachel' for e in events)
 assert 'apple.com' in out['response'] and '/iphone-duo/' in out['response'], 'Missing actual source citation'
 assert not any(s in out['response'].lower() for s in ('now in progress','will report back','will search','cannot browse','526gb')), 'Incorrect completion or numeric claim'
else:assert any(e['tool']=='hq_diagnostics' and e['arguments'].get('target')=='amd-gpu' for e in events)
