"""Reject credential material before a GitHub write. Never print matching values."""
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parent
PATTERNS=[r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
          r'\bgh[pousr]_[A-Za-z0-9]{30,}\b',r'\bgithub_pat_[A-Za-z0-9_]{40,}\b',
          r'\bAKIA[A-Z0-9]{16}\b',r'\bmfa\.[A-Za-z0-9_-]{40,}',
          r'\b[A-Za-z0-9_-]{23,30}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{25,}\b']

def secret_values():
    values=set()
    for directory in (ROOT/'access',ROOT.parent/'paperclip/worker-secrets',ROOT.parent.parent/'secrets',ROOT.parent/'paperclip/operations/keys'):
        if directory.exists():
            for p in directory.iterdir():
                if p.is_file() and p.suffix!='.pub' and not p.is_symlink() and p.stat().st_size<20000:
                    try:
                        value=p.read_text().strip()
                        if len(value)>=5 and '\n' not in value:values.add(value)
                    except (OSError,UnicodeError):pass
    for p in (ROOT.parent/'paperclip/.env',ROOT.parent/'n8n/.env'):
        if p.exists():
            for line in p.read_text().splitlines():
                key,_,value=line.partition('=')
                if re.search(r'TOKEN|SECRET|PASSWORD|API_KEY',key,re.I):
                    value=value.strip().strip('\"\'')
                    if len(value)>=5:values.add(value)
    for p in (ROOT.parent/'paperclip/admin-credentials.json',):
        if p.exists():
            value=json.loads(p.read_text()).get('password','')
            if value:values.add(value)
    return values

def check_text(text,public=False,secrets=None):
    if not isinstance(text,str):raise ValueError('Only text changes are supported')
    if any(re.search(pattern,text) for pattern in PATTERNS):raise ValueError('Credential-like material blocked')
    if any(value in text for value in (secret_values() if secrets is None else secrets)):
        raise ValueError('Protected local credential blocked')
    if public:
        terms=json.loads((ROOT/'config/publication-private-terms.json').read_text())
        if any(term.casefold() in text.casefold() for term in terms):
            raise ValueError('Public content must use generic amd-gpu/nvidia-gpu aliases')
    if public and re.search(r'\b(?:10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(?:1[6-9]|2\d|3[01])\.\d+\.\d+)\b',text):
        raise ValueError('Private network address blocked from public content')

def safe_path(path,write=False):
    if not isinstance(path,str) or not path or len(path)>240 or '\\' in path or '\x00' in path:
        raise ValueError('Invalid repository path')
    parts=path.split('/')
    if path.startswith('/') or any(x in ('','.','..') for x in parts):raise ValueError('Invalid repository path')
    if any(x.lower() in ('access','secrets','worker-secrets','keys','tls','.git','state','backups','logs','cache') for x in parts):
        raise PermissionError('Credential or runtime paths are blocked')
    if any(x.lower().startswith('.env') and not x.lower().endswith('.example') for x in parts):raise PermissionError('Environment secrets are blocked')
    if re.search(r'(?:credentials|session\.cookies|\.pem$|\.key$|\.sqlite|\.db$)',path,re.I):raise PermissionError('Sensitive file path blocked')
    if write and (parts[0] in ('.github','.gitmodules') or not path.startswith('LLM-Setup/')):
        raise PermissionError('Writes are limited to LLM-Setup; workflow changes are blocked')
    return path
