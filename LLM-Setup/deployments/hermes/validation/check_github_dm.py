"""Run inside concierge against a recent real owner DM; read-only, no Discord sends."""
import importlib.util,json,sqlite3,sys
from pathlib import Path
from gateway.session_context import set_session_vars,clear_session_vars

policy=json.loads(Path('/profile/discord-enrollment.json').read_text())
db=sqlite3.connect('file:/profile/state.db?mode=ro',uri=True);db.row_factory=sqlite3.Row
row=db.execute("SELECT m.platform_message_id,s.chat_id,s.user_id,m.content FROM messages m JOIN sessions s ON m.session_id=s.id WHERE m.role='user' AND m.content=? AND s.user_id=? AND s.chat_type='dm' ORDER BY m.id DESC LIMIT 1",('are you able to access github repo krishadmin-hq?',policy['owner_id'])).fetchone()
assert row,'Need the actual recent owner DM; do not invent a Discord origin'
spec=importlib.util.spec_from_file_location('hq_dm_validation','/profile/plugins/hq-operations/__init__.py',submodule_search_locations=['/profile/plugins/hq-operations'])
plugin=importlib.util.module_from_spec(spec);sys.modules[spec.name]=plugin;spec.loader.exec_module(plugin)
def bind(user):
    return set_session_vars(platform='discord',user_id=user,chat_id=row['chat_id'],chat_type='dm',message_id=row['platform_message_id'])

tokens=bind(next(user for user in policy['allowed_users'] if user!=policy['owner_id']))
assert 'error' in json.loads(plugin.github({'action':'repos'}))
clear_session_vars(tokens)
tokens=bind(policy['owner_id'])
repos=json.loads(plugin.github({'action':'repos'}));assert len(repos.get('repositories',[]))==2,repos
checks=[]
for repo in repos['repositories']:
    status=json.loads(plugin.github({'action':'status','repo':repo['name']}));assert status.get('commit'),status
    content=json.loads(plugin.github({'action':'read','repo':repo['name'],'path':'LLM-Setup/README.md','limit':300}))
    assert content.get('blob_sha') and content.get('content'),content
    checks.append({'repo':repo['name'],'commit':status['commit'],'read_verified':True})
clear_session_vars(tokens)

from run_agent import AIAgent
events=[]
def completed(*args,**kwargs):
    if len(args)>=3:events.append({'tool':args[1],'arguments':args[2]})
agent=AIAgent(model='qwen3.5:9b',provider='custom',api_mode='chat_completions',base_url='http://broker:8080/v1',
    api_key=Path('/run/access/identity').read_text().strip(),enabled_toolsets=['hq_ops'],quiet_mode=True,
    skip_context_files=True,skip_memory=True,skip_background_review=True,max_iterations=5,max_tokens=1200,tool_complete_callback=completed)
tokens=bind(policy['owner_id'])
try:
    result=agent.run_conversation(row['content'],system_message=Path('/profile/SOUL.md').read_text())
finally:clear_session_vars(tokens)
out={'completed':result.get('completed'),'response':result.get('final_response'),'events':events,'repository_reads':checks,'friend_denied':True,'discord_messages_sent':0}
Path('/profile/validation-github-dm.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
assert out['completed'] and any(e['tool']=='hq_github' for e in events)
assert 'krishadmin-hq' in out['response'].lower()
assert not any(s in out['response'].lower() for s in ('cannot access','can\'t access','require explicit owner authentication','main private channel only'))
