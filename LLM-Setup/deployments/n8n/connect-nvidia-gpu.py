#!/usr/bin/env python3
"""Consume the NVIDIA-GPU token/certificate transferred over SSH and connect n8n."""
from pathlib import Path
import json, os, ssl, subprocess, urllib.request, uuid
root=Path('/home/operator/n8n')
os.chdir(root)
secret=root/'incoming/nvidia-gpu-token'
certificate=root/'incoming/nvidia-gpu-server.crt'
if not secret.is_file() or not certificate.is_file():
 raise SystemExit('Waiting for incoming/nvidia-gpu-token and incoming/nvidia-gpu-server.crt transferred from the GPU VM over SSH.')
token=secret.read_text().strip()
if len(token)!=64 or any(c not in '0123456789abcdef' for c in token):
 raise SystemExit('Token does not match the generated installer token format.')
context=ssl.create_default_context(cafile=str(certificate))
request=urllib.request.Request('https://192.0.2.181:11434/api/tags',headers={'Authorization':'Bearer '+token})
models=json.load(urllib.request.urlopen(request,context=context,timeout=20)).get('models',[])
names=[m['name'] for m in models]
model=next((m for m in ['qwen3:8b','qwen3:4b'] if m in names),None)
if model is None: raise SystemExit('No configured Qwen3 starter model found; installed models: '+', '.join(names))
trust=root/'trust'
trust.mkdir(mode=0o755,exist_ok=True)
(trust/'nvidia-gpu-server.crt').write_bytes(certificate.read_bytes())
(trust/'nvidia-gpu-server.crt').chmod(0o644)
def compose(*args,**kwargs):
 return subprocess.run(['sudo','-n','docker','compose',*args],check=True,**kwargs)
credential=[{'id':'krishnvidia_gpuAuth01','name':'KrishAdmin-HQ | nvidia-gpu API','type':'httpHeaderAuth','data':{'name':'Authorization','value':'Bearer '+token}}]
compose('exec','-T','n8n','sh','-c','umask 077; cat > /tmp/krish-nvidia-gpu-credential.json',input=json.dumps(credential),text=True,stdout=subprocess.DEVNULL)
try:
 compose('exec','-T','n8n','n8n','import:credentials','--input=/tmp/krish-nvidia-gpu-credential.json','--projectId=0LG1O502f2lHh1mm')
finally:
 compose('exec','-T','n8n','node','-e',"require('fs').unlinkSync('/tmp/krish-nvidia-gpu-credential.json')")
p=root/'compose.yaml';s=p.read_text()
if 'NODE_EXTRA_CA_CERTS:' not in s:
 s=s.replace('      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}','      N8N_ENCRYPTION_KEY: ${N8N_ENCRYPTION_KEY}\n      NODE_EXTRA_CA_CERTS: /etc/krishadmin-hq/nvidia-gpu-server.crt')
 s=s.replace('    volumes: [n8n_data:/home/node/.n8n]','    volumes:\n      - n8n_data:/home/node/.n8n\n      - ./trust/nvidia-gpu-server.crt:/etc/krishadmin-hq/nvidia-gpu-server.crt:ro')
p.write_text(s)
p=root/'workflows/krishadmin-hq-ai-router.json';w=json.loads(p.read_text());w['versionId']=str(uuid.uuid4())
for node in w['nodes']:
 if node['name']=='nvidia-gpu | Fast':
  body=node['parameters']['jsonBody']
  for old in ['qwen3:4b','qwen3:8b']:body=body.replace("model: '"+old+"'","model: '"+model+"'")
  # Bound context for the small card to match its starter configuration.
  node['parameters']['jsonBody']=body.replace('num_ctx:8192','num_ctx:4096')
p.write_text(json.dumps(w,indent=2)+'\n')
compose('cp',str(p),'n8n:/tmp/krishadmin-hq-ai-router.json')
compose('exec','-T','n8n','n8n','import:workflow','--input=/tmp/krishadmin-hq-ai-router.json','--projectId=0LG1O502f2lHh1mm')
compose('config','--quiet')
compose('up','-d','--wait','--wait-timeout','120')
compose('restart','runners','proxy')
# Delete only the transferred plaintext token after it has been imported successfully.
secret.unlink()
(root/'nvidia-gpu-connection.json').write_text(json.dumps({'endpoint':'https://192.0.2.181:11434','model':model,'tlsVerified':True,'credentialId':'krishnvidia_gpuAuth01'},indent=2)+'\n')
print('NVIDIA-GPU connected with verified TLS. Model:',model)
print('Next: execute the router with tier=fast to verify inference through n8n.')
