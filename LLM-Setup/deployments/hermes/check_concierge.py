import json,sys,time
from pathlib import Path
from run_agent import AIAgent
events=[];started=time.monotonic();submit='--submit' in sys.argv;alerts='--alerts' in sys.argv;files='--files' in sys.argv;team='--team' in sys.argv
a=AIAgent(model='qwen3.5:9b',provider='custom',api_mode='chat_completions',base_url='http://broker:8080/v1',
    api_key=Path('/run/access/identity').read_text().strip(),enabled_toolsets=['hq_ops'],quiet_mode=True,
    skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=8,max_tokens=1000,
    tool_complete_callback=lambda *args,**kwargs:events.append({'args':str(args)[:200],'kwargs':str(kwargs)[:200]}))
names=[t.get('function',t).get('name') for t in a.tools]
assert set(names)=={'hq_status','hq_task','hq_research','hq_analyze','hq_files','hq_knowledge','hq_draft','hq_team','hq_calculate','hq_diagnostics','hq_github'},names
r=a.run_conversation('Use hq_files validate for doc_012345abcdef_qa_review.py, then delegate its code review to Louis using hq_team with that file_id. After his review, save a corrected Python draft with hq_draft. Do not execute it. Briefly report the actual model/backend and draft path.' if files else 'Delegate a three-item deployment checklist to Harvey with hq_team. Keep the final response brief and identify the actual model/backend.' if team else 'Submit exactly one read-only health task using hq_task. Description: Validate current lab health evidence after approved NVIDIA-GPU GPU recovery. Return the real Paperclip task ID and link.' if submit else 'Call hq_status exactly once with view alerts. Report active observation warnings separately from setup gaps, and summarize recent changes if any. Do not submit a task.' if alerts else 'Call hq_status exactly once and report snapshot freshness and unavailable coverage. Do not submit a task.',
    system_message=Path('/profile/SOUL.md').read_text()+' Use the HQ tool for actual evidence. Keep the answer brief.')
result={'tools':names,'completed':r.get('completed'),'response':r.get('final_response'),'tool_events':events,'seconds':round(time.monotonic()-started,3)}
Path('/profile/concierge-validation'+('-task' if submit else '-alerts' if alerts else '-files' if files else '-team' if team else '')+'.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result))
assert r.get('completed') and events,'No successful actual tool call observed'
if alerts:assert any("'view': 'alerts'" in event['args'] for event in events),'Alert view was not used'

if files:
    assert all(any(name in event["args"] for event in events) for name in ("hq_files","hq_team","hq_draft")), "Missing file review pipeline tool calls"
if team:assert any("hq_team" in event["args"] for event in events), "Named specialist was not called"
