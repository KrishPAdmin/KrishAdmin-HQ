import {test} from 'node:test';
import assert from 'node:assert/strict';
import {stackView} from './src/stack.js';
const now=Date.parse('2026-11-09T17:00:00Z');
test('Stack snapshot cannot cross company boundary or expose unknown top-level fields',()=>{
 const snapshot={schema_version:1,company_id:'lab',collected_at:'2026-11-09T16:59:00Z',agents:[{name:'Jessica'}],private_token:'do not expose'};
 assert.equal(stackView(snapshot,'other',now).status,'unavailable');
 const result=stackView(snapshot,'lab',now);assert.equal(result.status,'observed');assert.equal(result.age_seconds,60);assert.ok(!('private_token' in result));
});
test('Old, future and invalid timestamps are never labeled current',()=>{
 for(const collected_at of ['2026-11-09T16:00:00Z','2026-11-09T18:00:00Z','not a timestamp'])assert.equal(stackView({schema_version:1,company_id:'lab',collected_at},'lab',now).status,'stale');
 assert.equal(stackView(null,'lab',now).status,'unavailable');
});
