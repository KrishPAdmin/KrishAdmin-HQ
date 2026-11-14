#!/usr/bin/env python3
"""Operator CLI: no plaintext secret output or secrets in process arguments."""
import argparse,getpass,json,os,ssl,sys,urllib.request
from pathlib import Path
sys.path.insert(0,'/usr/local/lib/hq-vault')
from vault_common import api,login,read_secret,BASE,CA,VaultError
p=argparse.ArgumentParser(description='HQ vault administration; never put a password in a command argument.')
p.add_argument('command',choices=['status','unlock','list','put','enroll','catalog','snapshot'])
p.add_argument('name',nargs='?');p.add_argument('--recovery-file',type=Path);p.add_argument('--output',type=Path)
a=p.parse_args()
if os.geteuid()!=0:raise SystemExit('Run with sudo; credentials are owned by the host operator.')
try:
 if a.command=='status':
  s=api('sys/seal-status');print(json.dumps({k:s[k] for k in ['initialized','sealed','version']},indent=2))
 elif a.command=='unlock':
  import time
  for attempt in range(50):
   try:sealed=api('sys/seal-status')['sealed'];break
   except VaultError:
    if attempt==49:raise
    time.sleep(.2)
  if sealed:
   key=json.loads(a.recovery_file.read_text())['keys_base64'][0] if a.recovery_file else getpass.getpass('Vault recovery key: ')
   s=api('sys/unseal',{'key':key})
   if s['sealed']:raise VaultError('More recovery shares required')
  import time
  from runtime_secrets import hydrate
  for attempt in range(20):
   try:hydrate();break
   except VaultError:
    if attempt==19:raise
    time.sleep(.5)
  print('Vault unlocked; runtime service credentials loaded.')
 else:
  t=login('operator')
  try:
   if a.command=='list':print('\n'.join(api('homelab/metadata',token=t,method='LIST')['data']['keys']))
   elif a.command=='enroll':
    from enrollment import enroll
    enroll(a.name,t)
   elif a.command=='catalog':
    from enrollment import publish
    print(json.dumps(publish(t),indent=2))
   elif a.command=='put':
    from enrollment import save,publish,valid_name
    valid_name(a.name)
    if not sys.stdin.isatty():raise VaultError('Use a private interactive terminal')
    secret=getpass.getpass('Credential value (hidden): ')
    if not secret:raise VaultError('Empty credential refused')
    save(a.name,t,secret);publish(t);print('Credential saved; existing service description preserved. Connector access must be explicitly configured.')
   else:
    if not a.output:raise VaultError('--output is required')
    req=urllib.request.Request(BASE+'sys/storage/raft/snapshot',headers={'X-Vault-Token':t})
    with urllib.request.urlopen(req,context=ssl.create_default_context(cafile=CA),timeout=30) as response:
     fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
     with os.fdopen(fd,'wb') as out:
      while chunk:=response.read(1024*1024):out.write(chunk)
    print('Encrypted vault snapshot saved.')
  finally:api('auth/token/revoke-self',{},t)
except (VaultError,OSError,ValueError):raise SystemExit('Vault operation failed. Check service status, unlock state and root-only configuration; no credential values were printed.')
