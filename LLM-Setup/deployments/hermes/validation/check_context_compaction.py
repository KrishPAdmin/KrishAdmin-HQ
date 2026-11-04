"""Native Hermes compaction of synthetic >100KB history; no Discord messages."""
import json,os,time
from pathlib import Path
from agent.context_compressor import ContextCompressor
os.environ['OPENAI_API_KEY']=Path('/run/access/identity').read_text().strip()
os.environ['OPENAI_BASE_URL']='http://broker:8080/v1'
history=[{'role':'system','content':'Keep the user requirement: all web collection runs on HQ; AMD-GPU is inference-only.'}]
for n in range(24):
    history.extend([{'role':'user','content':f'Checkpoint {n}: inspect the routine fixture records; no changes are authorized.'},
                    {'role':'assistant','content':'\n'.join(f'Fixture {n}-{i}: no incident found; preserve pending task KRI-FIXTURE and operator approval.' for i in range(70))}])
history.append({'role':'user','content':'Next: get current Toronto weather from a live source.'})
before=len(json.dumps(history));assert before>100000
compressor=ContextCompressor(model='qwen3.5:9b',provider='custom',base_url='http://broker:8080/v1',api_key=os.environ['OPENAI_API_KEY'],
    config_context_length=65536,threshold_tokens_cap=30000,protect_last_n=6,quiet_mode=True,abort_on_summary_failure=True)
started=time.monotonic();result=compressor.compress(history,current_tokens=45000,force=True)
after=len(json.dumps(result))
out={'history_bytes_before':before,'history_bytes_after':after,'messages_before':len(history),'messages_after':len(result),'seconds':round(time.monotonic()-started,2),'messages_sent':0,'configured_summary_model':'mixtral:8x22b-instruct-v0.1-q4_K_M'}
Path('/profile/validation-context-compaction.json').write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
assert after<before
assert 'Toronto' in json.dumps(result)
