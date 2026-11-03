// A deliberately small public view: never return adapter credentials or environment.
export function teamView(manifest,agents,companyId){
 if(!manifest||manifest.company_id!==companyId||!Array.isArray(manifest.agents))return {status:'unavailable',agents:[]};
 const byId=new Map(agents.map(a=>[a.id,a]));
 const rows=manifest.agents.flatMap(role=>{
  const agent=byId.get(role.id);if(!agent)return [];
  const config=agent.adapterConfig||{};
  const setting=key=>{const value=config.env?.[key];return typeof value==='string'?value:value?.type==='plain'?value.value:null;};
  const matches=agent.adapterType==='process'&&config.args?.includes('/opt/hq-agents/hermes_team_bridge.py')&&setting('HQ_TEAM_AGENT')===role.key&&setting('HQ_BACKEND')===role.backend;
  return [{id:agent.id,key:role.key,name:agent.name,title:agent.title,status:agent.status,
   reportsTo:agent.reportsTo||null,manager:byId.get(agent.reportsTo)?.name||'Human operator',
   backend:role.backend,model:role.model,parameters:role.parameters,maxOutputTokens:role.max_tokens,
   summary:role.summary,configurationMatches:matches&&((agent.reportsTo||null)===(role.reports_to_id||null))}];
 });
 return {status:rows.length===6&&rows.every(a=>a.configurationMatches)?'configured':'needs_attention',generatedAt:manifest.generated_at,agents:rows};
}
