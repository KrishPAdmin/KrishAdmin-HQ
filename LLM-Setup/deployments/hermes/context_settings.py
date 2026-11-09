"""Validated context allocations shared by HQ runtimes. Tokens are not input bytes."""
import json,os
from pathlib import Path

CONFIG=Path(os.environ.get('HQ_CONTEXT_CONFIG',str(Path(__file__).resolve().parent/'config/context-windows.json')))
DEFAULTS={'concierge':65536,'jessica':65536,'harvey':8192,'mike':65536,'louis':32768,'rachel':65536,'donna':65536,
          'analyst':32768,'health':65536,'backup':65536,'triage':65536,
          'paperclip-coordinator':8192,'paperclip-nvidia-gpu':8192,'paperclip-amd-gpu':8192,'pi':16384}
MAXIMUM={name:262144 for name in DEFAULTS}
MAXIMUM.update(jessica=65536,harvey=8192,louis=32768,analyst=32768,**{'paperclip-amd-gpu':32768})
MINIMUM={name:4096 for name in DEFAULTS}
MINIMUM.update({name:65536 for name in ('concierge','health','backup','triage')})

def defaults():return {'version':1,'contexts':dict(DEFAULTS),'experimental':[]}

def validate(value):
    if not isinstance(value,dict) or set(value)!={'version','contexts','experimental'} or value['version']!=1:raise ValueError('Invalid context configuration schema')
    contexts=value['contexts'];experimental=value['experimental']
    if not isinstance(contexts,dict) or set(contexts)!=set(DEFAULTS):raise ValueError('Context configuration must contain every known target exactly once')
    if not isinstance(experimental,list) or any(name not in DEFAULTS for name in experimental):raise ValueError('Invalid experimental context targets')
    for name,tokens in contexts.items():
        if type(tokens) is not int or tokens%1024 or not MINIMUM[name]<=tokens<=MAXIMUM[name]:
            raise ValueError(f'{name}: use a multiple of 1024 between {MINIMUM[name]} and {MAXIMUM[name]} tokens')
        if tokens>max(DEFAULTS[name],65536) and name not in experimental:raise ValueError(f'{name}: more than 65536 tokens requires --experimental; VRAM fit is not established')
    return value

def load(path=None):
    path=Path(path or CONFIG)
    if not path.exists():return defaults()
    with path.open() as stream:return validate(json.load(stream))

def window(name,settings=None):return (settings or load())['contexts'][name]

def target_for(role,model,backend):
    if role=='concierge' and backend=='amd-gpu':return 'jessica'
    if role in DEFAULTS:return role
    return 'analyst' if backend=='amd-gpu' else 'concierge'

def prompt_budget(name,settings=None):
    # Conservative UTF-8 byte cap leaves space for instructions and output.
    ceiling={'jessica':56000,'harvey':6000}.get(name,24000)
    return min(ceiling,max(1024,window(name,settings)-2048))

def compression(settings=None):
    settings=settings or load();threshold=min(30000,min(window('concierge',settings),window('jessica',settings))//2)
    return {'enabled':True,'threshold':0.75,'threshold_tokens':threshold,'target_ratio':0.2,'protect_last_n':6,
            'proactive_prune_tokens':min(22000,int(threshold*0.75)),'progress_notices':True}
