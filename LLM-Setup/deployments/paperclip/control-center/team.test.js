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
