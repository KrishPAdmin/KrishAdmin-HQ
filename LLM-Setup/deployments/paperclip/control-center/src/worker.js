import {definePlugin,runWorker} from '@paperclipai/plugin-sdk';
import fs from 'node:fs/promises';
import crypto from 'node:crypto';
import {teamView} from './team.js';
import {load,save,audit,validatePolicy,validateSystem,getCertificate,proxmoxRead,fail,UUID} from './core.js';
let ctx;let queue=Promise.resolve();
const serialized=fn=>{const result=queue.then(fn);queue=result.catch(()=>{});return result;};
async function snapshot(){try{return JSON.parse(await fs.readFile('/opt/hq-observations/host-health.json','utf8'));}catch{return null;}}
async function companySnapshot(d){const raw=await snapshot();if(!raw)return null;const allowed=new Set(d.systems.filter(s=>s.kind==='linux').map(s=>'managed_'+s.id.replaceAll('-','')));return {...(d.includeGatewayObservations?{...raw,remote_hosts:{}}:{checked_at_utc:raw.checked_at_utc}),remote_hosts:Object.fromEntries(Object.entries(raw.remote_hosts||{}).filter(([k])=>allowed.has(k)||(d.includeGatewayObservations&&!k.startsWith('managed_'))))};}
async function workerRequest(route,body){const token=(await fs.readFile('/run/secrets/codex-bridge-token','utf8')).trim();const response=await fetch('http://codex-worker:8081'+route,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json',Authorization:'Bearer '+token}:{},body:body?JSON.stringify(body):undefined,signal:AbortSignal.timeout(15000)});if(!response.ok)fail('Codex account controller is unavailable. Retry when the current task finishes.',response.status);return await response.json();}
async function inspect(d,system,actor,issueId){
 if(system.readAccess==='off')fail('Read access is switched off.',403);
 if(actor.actorType==='agent'){
  if(!system.allowedAgents.includes(actor.agentId))fail('This agent is not permitted to use this system.',403);
  if(system.readAccess==='ask'){
   const configHash=crypto.createHash('sha256').update(JSON.stringify({kind:system.kind,endpoint:system.endpoint,host:system.host,fingerprint:system.fingerprint,secretId:system.secretId,tokenId:system.tokenId,allowedAgents:system.allowedAgents,readAccess:system.readAccess})).digest('hex');
   const approval=d.pendingActions.find(x=>x.systemId===system.id&&x.agentId===actor.agentId&&x.issueId===issueId&&x.status==='approved'&&x.configHash===configHash&&Date.parse(x.expiresAt)>Date.now());
   if(!approval){let pending=d.pendingActions.find(x=>x.systemId===system.id&&x.agentId===actor.agentId&&x.issueId===issueId&&x.status==='pending'&&x.configHash===configHash&&Date.parse(x.expiresAt)>Date.now());if(!pending){pending={id:crypto.randomUUID(),systemId:system.id,systemName:system.name,agentId:actor.agentId,issueId,action:'Read system health',configHash,endpoint:system.endpoint||system.host,status:'pending',createdAt:new Date().toISOString(),expiresAt:new Date(Date.now()+3600000).toISOString()};d.pendingActions=d.pendingActions.slice(-99);d.pendingActions.push(pending);await save(d);}return {status:428,body:{error:'Operator approval is required in Control Center → Access reviews.',actionId:pending.id}};}
   approval.status='consumed';approval.consumedAt=new Date().toISOString();await save(d);
  }
 }
 let result;
 if(system.kind==='proxmox'){
  const token=await ctx.secrets.resolve({type:'secret_ref',secretId:system.secretId,version:'latest'},{companyId:d.companyId,configPath:'proxmoxToken'});
  if(typeof token!=='string'||!token||/[\r\n]/.test(token))fail('The stored API token is invalid.',422);
  const checks=await Promise.all(['/api2/json/cluster/status','/api2/json/cluster/resources','/api2/json/nodes'].map(async p=>{try{return {path:p,status:'observed',data:await proxmoxRead(system,token,p)};}catch(e){return {path:p,status:'unavailable',error:String(e.message).replaceAll(token,'[redacted]')};}}));
  result={checkedAt:new Date().toISOString(),systemId:system.id,name:system.name,kind:system.kind,status:checks.every(c=>c.status==='observed')?'observed':'partial',checks,limitations:'Read-only API observations. Guest logs, host logs, console access, backup integrity and configuration changes are not included.'};
 }else{
  const s=await snapshot();const observation=s?.remote_hosts?.['managed_'+system.id.replaceAll('-','')];result={checkedAt:s?.checked_at_utc||null,systemId:system.id,name:system.name,kind:system.kind,status:s&&(!Number.isFinite(Date.parse(s.checked_at_utc))||Date.now()-Date.parse(s.checked_at_utc)>600000||Date.parse(s.checked_at_utc)>Date.now())?'stale':observation?.status||'unavailable',observation:observation||{reason:'Waiting for observer enrollment and the next five-minute host refresh.'},limitations:'Fixed Linux probe only; no arbitrary SSH commands or remote changes.'};
 }
 system.lastCheck=result;system.checkedAt=result.checkedAt;audit(d,actor,'system.read',system.id);await save(d);
 await ctx.activity.log({companyId:d.companyId,entityType:'plugin',entityId:'krishadmin.control-center',message:'Read-only system inspection: '+system.name,metadata:{systemId:system.id,actorId:actor.actorId,status:result.status}});
 return {status:200,body:result};
}
const plugin=definePlugin({async setup(c){ctx=c;},async onHealth(){return {status:'ok',message:'Control Center ready'};},
 async onApiRequest(r){return serialized(async()=>{try{
  const d=await load(r.companyId),b=r.body||{},actor=r.actor;
  if(actor.actorType==='user'&&r.routeKey!=='overview'&&!(d.operatorUserIds||[]).includes(actor.userId||actor.actorId))fail('Only the configured lab operators can change controls or access local systems.',403);
  if(r.routeKey==='overview'){
   if(actor.actorType==='agent')return {status:200,body:{externalAI:d.externalAI,autoEscalate:d.autoEscalate,maxSteps:d.maxSteps,agent:d.agents[actor.agentId]||{},systems:d.systems.filter(s=>s.allowedAgents.includes(actor.agentId)).map(s=>({id:s.id,name:s.name,kind:s.kind,readAccess:s.readAccess}))}};
   const agents=await ctx.agents.list({companyId:r.companyId,limit:100,offset:0});
   let manifest=null;try{manifest=JSON.parse(await fs.readFile('/paperclip/hq-hermes/team.json','utf8'));}catch{}
   return {status:200,body:{...d,agentsList:agents.map(a=>({id:a.id,name:a.name,status:a.status,adapterType:a.adapterType,title:a.title,reportsTo:a.reportsTo})),team:teamView(manifest,agents,r.companyId),hostSnapshot:await companySnapshot(d)}};
  }
  const agents=await ctx.agents.list({companyId:r.companyId,limit:100,offset:0});const ids=new Set(agents.map(a=>a.id));
  if(r.routeKey==='codex-status')return {status:200,body:await workerRequest('/login/status',{})};
  if(r.routeKey==='codex-login'){audit(d,actor,'codex.login_started','account');await save(d);return {status:200,body:await workerRequest('/login/start',{})};}
  if(r.routeKey==='policy'){if(b.revision!==undefined&&b.revision!==(d.revision||0))fail('Controls changed since this page loaded. Refresh and review the latest settings before saving.',409);Object.assign(d,validatePolicy(b,ids));audit(d,actor,'policy.updated','company');await save(d);await ctx.activity.log({companyId:r.companyId,entityType:'plugin',entityId:'krishadmin.control-center',message:'Operator updated agent and privacy controls',metadata:{actorId:actor.actorId,externalAI:d.externalAI,autoEscalate:d.autoEscalate,maxSteps:d.maxSteps}});return {status:200,body:{ok:true}};}
  if(r.routeKey==='certificate')return {status:200,body:await getCertificate(b.endpoint)};
  if(r.routeKey==='save-system'){const system=validateSystem(b,ids);const old=d.systems.find(x=>x.id===system.id);if(old&&old.kind!==system.kind)fail('A system type cannot be changed.');if(old){Object.assign(old,system);delete old.lastCheck;delete old.checkedAt;for(const action of d.pendingActions)if(action.systemId===system.id&&['pending','approved'].includes(action.status))action.status='superseded';}else d.systems.push(system);audit(d,actor,'system.configured',system.id);await save(d);await ctx.activity.log({companyId:r.companyId,entityType:'plugin',entityId:'krishadmin.control-center',message:'Operator configured local system '+system.name,metadata:{systemId:system.id,kind:system.kind}});return {status:200,body:{ok:true,id:system.id}};}
  if(r.routeKey==='remove-system'){const old=d.systems.find(x=>x.id===r.params.systemId);if(!old)fail('System not found.',404);d.systems=d.systems.filter(x=>x.id!==old.id);audit(d,actor,'system.disconnected',old.id);await save(d);return {status:200,body:{ok:true}};}
  if(r.routeKey==='inspect'||r.routeKey==='agent-inspect'){const system=d.systems.find(x=>x.id===r.params.systemId);if(!system)fail('System not found.',404);return await inspect(d,system,actor,r.params.issueId||null);}
  if(r.routeKey==='resolve-action'){const action=d.pendingActions.find(x=>x.id===r.params.actionId);if(!action||action.status!=='pending'||Date.parse(action.expiresAt)<=Date.now())fail('This request is no longer pending.',409);if(!['approved','denied'].includes(b.status))fail('Choose approve or deny.');action.status=b.status;action.decidedBy=actor.actorId;action.decidedAt=new Date().toISOString();audit(d,actor,'access.'+b.status,action.id);await save(d);return {status:200,body:{ok:true,issueId:action.issueId}};}
  if(r.routeKey==='enrollment')return {status:200,body:{script:await fs.readFile('/opt/hq-control-plugin/seed/install-observer.sh','utf8')}};
  return {status:404,body:{error:'Unknown operation'}};
 }catch(e){return {status:e.status||400,body:{error:e.status?e.message:'Operation failed. Check access, endpoint and saved configuration.'}};}});}
});export default plugin;runWorker(plugin,import.meta.url);
