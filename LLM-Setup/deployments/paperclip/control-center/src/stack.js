// Keep installation observations company-scoped and explicitly mark stale snapshots.
export function stackView(snapshot,companyId,now=Date.now()){
 if(!snapshot||snapshot.company_id!==companyId||snapshot.schema_version!==1)return {status:'unavailable',agents:[]};
 const age=(now-Date.parse(snapshot.collected_at))/1000;
 const allowed=['schema_version','company_id','collected_at','stale_after_seconds','context','agents','services','integrations','repositories','skills','tasks','assessment','hosts','backup_status','coverage'];
 return {...Object.fromEntries(allowed.filter(k=>k in snapshot).map(k=>[k,snapshot[k]])),status:Number.isFinite(age)&&age>=0&&age<=600?'observed':'stale',age_seconds:Number.isFinite(age)?Math.round(age):null};
}
