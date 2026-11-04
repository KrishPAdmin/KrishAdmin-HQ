"""Idempotent local deployment preparation; never prints secrets."""
import json,os,secrets
from pathlib import Path
from team import TEAM
ROOT=Path(__file__).resolve().parent
IMAGE='nousresearch/hermes-agent@sha256:d27689bc6e8581ec884a7227c9101fdaebf6c853cff8859020dac14f21452b4d'

def main():
    os.umask(0o077)
    for name in ('access','state','validation','config','observations','profiles','plugin'):(ROOT/name).mkdir(exist_ok=True)
    for name in ('concierge','health','backup','triage','analyst','operator','paperclip','worker','github-origin',*TEAM):
        p=ROOT/'access'/name
        if not p.exists():p.write_text(secrets.token_urlsafe(32)+'\n')
    p=ROOT/'config/research-origins.json'
    if not p.exists():p.write_text(json.dumps(['hermes-agent.nousresearch.com','docs.discord.com','docs.python.org','pve.proxmox.com','docs.n8n.io'],indent=2)+'\n')
    common={'image':IMAGE,'restart':'unless-stopped','init':True,'user':'1000:1000','read_only':True,
        'tmpfs':['/tmp:rw,noexec,nosuid,size=256m'],'cap_drop':['ALL'],'security_opt':['no-new-privileges:true'],
        'pids_limit':128,'mem_limit':'1g','cpus':1.0,'networks':['private'],
        'logging':{'driver':'json-file','options':{'max-size':'10m','max-file':'3'}},
        'healthcheck':{'test':['CMD','python','-c',"import urllib.request; urllib.request.urlopen('http://localhost:8080/health',timeout=3)"],'interval':'20s','timeout':'5s','retries':3,'start_period':'45s'}}
    services={}
    for profile in ('health','backup','triage','analyst','concierge'):
        home=ROOT/'profiles'/profile;home.mkdir(exist_ok=True)
        model='qwen2.5:72b-instruct-q8_0' if profile=='analyst' else 'qwen3.5:9b'
        config={'group_sessions_per_user':True,'thread_sessions_per_user':True,'model':{'default':model,'provider':'custom','base_url':'http://broker:8080/v1','context_length':32768 if profile=='analyst' else 65536},
            'platform_toolsets':{'cli':[],'discord':['hq_ops'] if profile=='concierge' else []},
            'plugins':{'enabled':['hq-operations','discord-platform'] if profile=='concierge' else []},
            'agent':{'max_turns':12},'compression':{'enabled':False},'memory':{'memory_enabled':False,'user_profile_enabled':False},
            'tools':{'tool_search':{'enabled':'off'}},'timeouts':{'tools':{'sequential_call':540,'concurrent_batch':540}},
            'platforms':{'discord':{'enabled':False,'extra':{'dm_policy':'disabled','group_policy':'allowlist','group_allow_from':[],
                'allow_admin_from':[],'group_allow_admin_from':[],'user_allowed_commands':['status'],'group_user_allowed_commands':['status']}}},
            'discord':{'require_mention':True,'history_backfill':False,'auto_thread':False},
            'display':{'tool_progress':'off'}}
        cfg=home/'config.yaml'
        if not cfg.exists():cfg.write_text(json.dumps(config,indent=2)+'\n')
        if profile=='concierge':
            config=json.loads(cfg.read_text())
            config['mcp_servers']={name:{'command':'python','args':['/app/mcp_server.py',name],'tools':{'include':names,'resources':False,'prompts':False},'timeout':540} for name,names in {'research':['search','read_page','weather'],'workbench':['check_system','review_file','plan_automation']}.items()}
            config['platform_toolsets']['discord']=['hq_ops','mcp-research','mcp-workbench']
            config['agent']['max_turns']=12
            config['compression']={'enabled':True,'threshold':0.75,'threshold_tokens':30000,'target_ratio':0.2,'protect_last_n':6,'proactive_prune_tokens':22000,'progress_notices':True}
            config['auxiliary']={'compression':{'provider':'custom','base_url':'http://broker:8080/v1','model':TEAM['jessica']['model'],'api_key_env':'OPENAI_API_KEY','timeout':520,'no_progress_timeout':520,'context_length':65536}}
            cfg.write_text(json.dumps(config,indent=2)+'\n')
            continue
        services[profile]={**common,'entrypoint':['python','/app/worker.py'],
            'environment':{'HERMES_HOME':'/profile','HQ_PROFILE':profile,'PYTHONPATH':'/opt/hermes','PYTHONDONTWRITEBYTECODE':'1'},
            'volumes':['./worker.py:/app/worker.py:ro','./capabilities.py:/app/capabilities.py:ro',f'./profiles/{profile}:/profile',f'./access/{profile}:/run/access/identity:ro','./access/worker:/run/access/worker:ro']}
    for name,role in TEAM.items():
        home=ROOT/'profiles'/name;home.mkdir(exist_ok=True)
        (home/'role.json').write_text(json.dumps(role,indent=2)+'\n')
        services[name]={**common,'mem_limit':'256m','entrypoint':['python','/app/team_worker.py'],
            'environment':{'HQ_PROFILE':name,'PYTHONDONTWRITEBYTECODE':'1'},
            'volumes':['./team_worker.py:/app/team_worker.py:ro','./team.py:/app/team.py:ro','./capabilities.py:/app/capabilities.py:ro',
                f'./profiles/{name}:/profile',f'./access/{name}:/run/access/identity:ro','./access/worker:/run/access/worker:ro']}
    (ROOT/'profiles/concierge/cache/documents/drafts').mkdir(parents=True,exist_ok=True)
    services['files']={**common,'mem_limit':'768m','entrypoint':['python','/app/file_service.py'],
        'volumes':['./file_service.py:/app/file_service.py:ro','./profiles/concierge/cache/documents:/uploads:ro','./access/worker:/run/access/worker:ro']}
    services['broker']={**common,'entrypoint':['python','/app/broker.py'],'mem_limit':'512m',
        'ports':['127.0.0.1:18880:8080'],'networks':{'private':{},'egress':{},'paperclip':{'aliases':['hq-hermes-broker']}},
        'volumes':['./broker.py:/app/broker.py:ro','./task_updates.py:/app/task_updates.py:ro','./profiles/concierge/discord-enrollment.json:/discord-enrollment.json:ro','./web_research.py:/app/web_research.py:ro','./health_rules.py:/app/health_rules.py:ro','./capabilities.py:/app/capabilities.py:ro','./team.py:/app/team.py:ro',
            './docs:/knowledge:ro','./profiles/concierge/cache/documents/drafts:/drafts','./access:/run/access:ro','./state:/state','./config:/config:ro',
            './observations:/observations:ro','./run/diagnostics:/diagnostic-socket:ro','/var/lib/hq-observations:/backup-observations:ro','../paperclip/data/hq-locks:/locks',
            '../../secrets/nvidia-gpu-api.txt:/run/secrets/nvidia-gpu-token:ro','../../secrets/amd-gpu-api.txt:/run/secrets/amd-gpu-token:ro',
            '../../secrets/nvidia-gpu-server.crt:/run/secrets/nvidia-gpu-ca.crt:ro']}
    services['discord-egress']={**common,'entrypoint':['python','/app/discord_egress.py'],'mem_limit':'128m',
        'profiles':['discord'],'networks':['private','egress'],'volumes':['./discord_egress.py:/app/discord_egress.py:ro'],
        'healthcheck':{'disable':True}}
    services['concierge']={**common,'entrypoint':['python','/app/gateway_start.py'],'profiles':['discord'],
        'environment':{'HERMES_HOME':'/profile','XDG_STATE_HOME':'/profile/runtime-state','XDG_CACHE_HOME':'/profile/cache','PYTHONPATH':'/opt/hermes','PYTHONDONTWRITEBYTECODE':'1','DISCORD_PROXY':'http://discord-egress:8888'},
        'volumes':['./gateway_start.py:/app/gateway_start.py:ro','./mcp_server.py:/app/mcp_server.py:ro','./profiles/concierge:/profile',
            './plugin:/profile/plugins/hq-operations:ro','./access/concierge:/run/access/identity:ro',
            './access/discord-token:/run/access/discord-token:ro','./run/github:/github-socket:ro','./access/github-origin:/run/access/github-origin:ro'], 'healthcheck':{'disable':True}}
    (ROOT/'compose.yaml').write_text(json.dumps({'name':'hq-hermes','services':services,
        'networks':{'private':{'internal':True},'egress':{},'paperclip':{'external':True,'name':'hq-paperclip_default'}}},indent=2)+'\n')
    (ROOT/'release.json').write_text(json.dumps({'version':'v0.22.6','revision':'f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab','image':IMAGE},indent=2)+'\n')
    print('Prepared deployment, separate profiles and private credentials; Discord remains disabled until enrollment.')
if __name__=='__main__':main()
