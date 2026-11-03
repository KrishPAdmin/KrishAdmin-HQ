from pathlib import Path
import json,uuid
base=Path('/home/operator/n8n/workflows')
health=json.loads((base/'current-health.json').read_text())[0]
health['name']='KrishAdmin-HQ | Service Health'
health['active']=False
health['versionId']=str(uuid.uuid4())
for k in ['activeVersionId','activeVersion','shared','homeProject','createdAt','updatedAt']:
 health.pop(k,None)
(base/'n8n-readiness-monitor.json').write_text(json.dumps(health,indent=2)+'\n')
def n(name,typ,params,pos,v=1,**kw):
 return dict(id=str(uuid.uuid4()),name=name,type='n8n-nodes-base.'+typ,typeVersion=v,parameters=params,position=pos,**kw)
def assign(values):
 return {'assignments':{'assignments':[{'id':str(uuid.uuid4()),'name':k,'value':v,'type':t} for k,v,t in values]},'options':{}}
def condition(expr):
 return {'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict','version':2},'conditions':[{'id':str(uuid.uuid4()),'leftValue':expr,'rightValue':True,'operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}}
http_options={'timeout':600000,'response':{'response':{'responseFormat':'json'}}}
def infer(name,url,model,cred,credname,pos,fast=False):
 body="={{ JSON.stringify({model: '"+model+"', messages: [{role: 'system', content: 'You are KrishAdmin-HQ, a local homelab assistant. Be accurate and concrete. Distinguish supplied evidence from assumptions. You only generate text; never claim to have inspected systems or executed actions.'}, {role:'user', content:$json.prompt}], stream:false, "+('think:false, ' if fast else '')+"options:{num_ctx:8192,num_predict:768,temperature:0.2} }) }}"
 return n(name,'httpRequest',{'method':'POST','url':url,'authentication':'genericCredentialType','genericAuthType':'httpHeaderAuth','sendBody':True,'specifyBody':'json','jsonBody':body,'options':http_options},pos,4.2,credentials={'httpHeaderAuth':{'id':cred,'name':credname}})
nodes=[n('Run manually','manualTrigger',{},[0,0]),n('Example request','set',assign([('tier','reasoning','string'),('prompt','In three sentences, explain what evidence I should collect before restarting a failed homelab service.','string')]),[220,0],3.4),n('Called by another workflow','executeWorkflowTrigger',{'inputSource':'passthrough'},[220,240],1.1),n('Validate request','if',condition("={{ typeof $json.prompt === 'string' && $json.prompt.trim().length > 0 && $json.prompt.length <= 12000 && ['fast','reasoning'].includes($json.tier) }}"),[460,100],2.2),n('Invalid request','stopAndError',{'errorMessage':'Provide prompt (1–12000 characters) and tier (fast or reasoning).'},[700,340]),n('Use NVIDIA-GPU fast model?','if',condition("={{ $json.tier === 'fast' }}"),[700,40],2.2),infer('nvidia-gpu | Fast','https://192.0.2.181:11434/api/chat','qwen3:4b','krishnvidia_gpuAuth01','KrishAdmin-HQ | nvidia-gpu API',[960,-80],True),infer('Dual AMD-GPU | Reasoning','http://198.51.100.202:11434/api/chat','qwen2.5:72b-instruct-q8_0','krishamd_gpuAuth01','KrishAdmin-HQ | AMD-GPU API',[960,160]),n('Return answer','set',assign([('answer',"={{ $json.message?.content ?? '' }}",'string'),('model','={{ $json.model }}','string'),('completed','={{ $json.done === true }}','boolean'),('generated_tokens','={{ $json.eval_count ?? 0 }}','number'),('total_seconds','={{ ($json.total_duration ?? 0) / 1000000000 }}','number'),('completed_at','={{ $now.toISO() }}','string')]),[1220,40],3.4),n('KrishAdmin-HQ guide','stickyNote',{'content':'# KrishAdmin-HQ — Local AI Router\n\n**Manual use:** edit `Example request`, choose tier `fast` or `reasoning`, then Execute Workflow.\n\n**Reusable:** call this workflow with `{ "tier": "fast", "prompt": "..." }`.\n\n**fast:** nvidia-gpu, local HTTPS; token and trusted certificate required. Model will be verified after connection.\n\n**reasoning:** dual AMD-GPU, ZeroTier VPN, Qwen 2.5 72B.\n\nFixed backend URLs; credentials are encrypted in n8n. TLS verification stays enabled. No shell commands or infrastructure changes. No automatic cross-backend retry. Inference runs only when requested.','height':430,'width':460},[0,-500])]
def edge(name):return {'node':name,'type':'main','index':0}
connections={}
for a,b in [('Run manually','Example request'),('Example request','Validate request'),('Called by another workflow','Validate request'),('nvidia-gpu | Fast','Return answer'),('Dual AMD-GPU | Reasoning','Return answer')]: connections[a]={'main':[[edge(b)]]}
connections['Validate request']={'main':[[edge('Use NVIDIA-GPU fast model?')],[edge('Invalid request')]]}
connections['Use NVIDIA-GPU fast model?']={'main':[[edge('nvidia-gpu | Fast')],[edge('Dual AMD-GPU | Reasoning')]]}
w={'id':'krishHqAiRouter01','name':'KrishAdmin-HQ | Local AI Router','active':False,'nodes':nodes,'connections':connections,'settings':{'executionOrder':'v1','timezone':'Etc/UTC','executionTimeout':660,'saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False},'versionId':str(uuid.uuid4()),'pinData':{},'tags':[]}
(base/'krishadmin-hq-ai-router.json').write_text(json.dumps(w,indent=2)+'\n')
print('Built branded health workflow and two-backend inference router.')
