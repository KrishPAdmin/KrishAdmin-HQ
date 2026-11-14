import {test} from 'node:test';
import assert from 'node:assert/strict';
import {teamView} from './src/team.js';
const role={id:'jessica-id',key:'jessica',backend:'amd-gpu',model:'mixtral',reports_to_id:null};
const manifest={company_id:'lab',agents:[role]};
const agent={id:'jessica-id',name:'Jessica Pearson',reportsTo:null,adapterType:'process',adapterConfig:{args:['/opt/hq-agents/hermes_team_bridge.py'],env:{HQ_TEAM_AGENT:'jessica',HQ_BACKEND:'amd-gpu',PRIVATE_KEY:'must-not-be-returned'}}};
test('Team view is company scoped and omits private adapter configuration',()=>{
 assert.deepEqual(teamView(manifest,[agent],'other').agents,[]);
 const result=teamView(manifest,[agent],'lab');assert.equal(result.agents[0].configurationMatches,true);
 assert.equal(result.agents[0].manager,'Human operator');assert.ok(!JSON.stringify(result).includes('must-not-be-returned'));
});
test('Changed task routing and changed hierarchy are shown as mismatches',()=>{
 for(const changed of [{...agent,adapterType:'codex_local'},{...agent,reportsTo:'old-coordinator'},{...agent,adapterConfig:{...agent.adapterConfig,env:{HQ_TEAM_AGENT:'jessica',HQ_BACKEND:'nvidia-gpu'}}}]){
  const result=teamView(manifest,[changed],'lab');assert.equal(result.status,'needs_attention');assert.equal(result.agents[0].configurationMatches,false);
 }
});
test('Deleted agents are not shown as configured specialists',()=>{
 assert.equal(teamView(manifest,[],'lab').status,'needs_attention');assert.deepEqual(teamView(manifest,[],'lab').agents,[]);
});
test('Native plain environment bindings are compared without exposing them',()=>{
 const bound={...agent,adapterConfig:{...agent.adapterConfig,env:{HQ_TEAM_AGENT:{type:'plain',value:'jessica'},HQ_BACKEND:{type:'plain',value:'amd-gpu'}}}};
 assert.equal(teamView(manifest,[bound],'lab').agents[0].configurationMatches,true);
});
test('Benjamin uses the existing execution adapter and Harvey reporting line',()=>{
 const benjamin={id:'existing-worker',key:'benjamin',backend:'nvidia-gpu',context_target:'pi',execution_mode:'workspace',reports_to_id:'harvey-id'};
 const worker={id:benjamin.id,name:'Benjamin',reportsTo:'harvey-id',adapterType:'process',adapterConfig:{args:['/opt/hq-agents/pi_bridge.py']}};
 const m={company_id:'lab',agents:[benjamin]};
 const result=teamView(m,[worker,{id:'harvey-id',name:'Harvey Specter'}],'lab').agents[0];
 assert.equal(result.configurationMatches,true);assert.equal(result.manager,'Harvey Specter');assert.equal(result.contextTarget,'pi');
 assert.equal(teamView(m,[{...worker,adapterConfig:agent.adapterConfig}],'lab').agents[0].configurationMatches,false);
 assert.equal(teamView(m,[{...worker,reportsTo:'old-coordinator'}],'lab').agents[0].configurationMatches,false);
});
test('All seven team members must be present and correctly routed',()=>{
 const keys=['jessica','harvey','mike','louis','rachel','donna','benjamin'];
 const roles=keys.map(key=>({id:key,key,backend:'nvidia-gpu',reports_to_id:null,...(key==='benjamin'?{execution_mode:'workspace'}:{})}));
 const agents=roles.map(r=>({id:r.id,adapterType:'process',reportsTo:null,adapterConfig:{args:[r.key==='benjamin'?'/opt/hq-agents/pi_bridge.py':'/opt/hq-agents/hermes_team_bridge.py'],env:{HQ_TEAM_AGENT:r.key,HQ_BACKEND:r.backend}}}));
 const m={company_id:'lab',agents:roles};
 assert.equal(teamView(m,agents,'lab').status,'configured');
 assert.equal(teamView(m,agents.slice(0,-1),'lab').status,'needs_attention');
});
