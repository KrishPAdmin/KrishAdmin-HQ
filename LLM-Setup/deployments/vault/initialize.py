"""One-time root-only enrollment. No secret values are printed."""
import json,os
from pathlib import Path
from vault_common import api
os.umask(0o077)
recovery=Path('/var/lib/private/hq-vault-recovery/initialization.json')
if api('sys/init')['initialized']:
 data=json.loads(recovery.read_text())
 if 'root_token' not in data:raise SystemExit('Enrollment complete; use the operator CLI.')
else:
 data=api('sys/init',{'secret_shares':1,'secret_threshold':1},method='PUT');recovery.write_text(json.dumps(data))
if api('sys/seal-status')['sealed']:api('sys/unseal',{'key':data['keys_base64'][0]})
token=data['root_token']
import time
for attempt in range(20):
 try:mounts=api('sys/mounts',token=token)['data'];break
 except Exception:time.sleep(.5)
else:raise RuntimeError('Vault did not become ready')
if 'homelab/' not in mounts:api('sys/mounts/homelab',{'type':'kv','options':{'version':'2'}},token)
if 'approle/' not in api('sys/auth',token=token)['data']:api('sys/auth/approle',{'type':'approle'},token)
policies={
 'hq-connector':'\n'.join('path "homelab/data/'+name+'" { capabilities = ["read"] }' for name in ['pi-cluster','amd-gpu-ssh']),
 'hq-runtime':'\n'.join('path "homelab/data/'+name+'" { capabilities = ["read"] }' for name in ['nvidia-gpu-api','amd-gpu-api']),
 'hq-operator':'path "homelab/*" { capabilities = ["create", "read", "update", "delete", "list"] }\npath "sys/storage/raft/snapshot" { capabilities = ["read"] }\npath "sys/seal" { capabilities = ["update", "sudo"] }'
}
for role,policy in policies.items():
 api('sys/policies/acl/'+role,{'policy':policy},token,method='PUT')
 api('auth/approle/role/'+role,{'token_policies':[role],'token_ttl':'5m','token_max_ttl':'15m','secret_id_num_uses':0,'secret_id_ttl':0,'token_bound_cidrs':['127.0.0.1/32']},token)
 rid=api('auth/approle/role/'+role+'/role-id',token=token)['data']['role_id']
 sid=api('auth/approle/role/'+role+'/secret-id',{},token)['data']['secret_id']
 Path('/etc/hq-vault/'+role.removeprefix('hq-')+'.json').write_text(json.dumps({'role_id':rid,'secret_id':sid}))
# Migrate values in memory; nothing is included in logs or command arguments.
base=Path('/home/operator/krishadmin-hq')
rows={}
for line in Path('/home/operator/.codex/secrets/.passwords').read_text().splitlines():
 label,sep,value=line.partition(':')
 if sep and label.strip().lower()=='pi cluster':rows['pi-cluster']=value.strip()
if not rows.get('pi-cluster'):raise RuntimeError('Pi cluster credential missing')
for name,path in {'amd-gpu-ssh':base/'deployments/paperclip/operations/keys/amd-gpu-password','nvidia-gpu-api':base/'secrets/nvidia-gpu-api.txt','amd-gpu-api':base/'secrets/amd-gpu-api.txt'}.items():
 rows[name]=path.read_text().strip()
for name,value in rows.items():
 if not value:raise RuntimeError('Empty credential refused')
 api('homelab/data/'+name,{'data':{'value':value}},token)
 assert api('homelab/data/'+name,token=token)['data']['data']['value']==value
api('auth/token/revoke-self',{},token)
# Retain only the recovery share, in root-only staging outside service data and agent mounts.
recovery.write_text(json.dumps({'keys_base64':data['keys_base64'],'threshold':data.get('secret_threshold',1)},indent=2)+'\n')
print('Vault initialized; four credentials enrolled and verified; bootstrap root token revoked.')
