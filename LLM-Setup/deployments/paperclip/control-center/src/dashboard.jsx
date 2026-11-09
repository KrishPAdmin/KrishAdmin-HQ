import React,{useState,useEffect} from 'react';
const count=n=>Number.isFinite(n)?n.toLocaleString():'Unavailable';
const gib=n=>Number.isFinite(n)?(n/2**30).toFixed(2):'—';

export function LiveGPUs({call,companyId}){
 const [data,setData]=useState(null),[error,setError]=useState(''),[paused,setPaused]=useState(false),[history,setHistory]=useState({}),[clock,setClock]=useState(Date.now());
 useEffect(()=>{setData(null);setHistory({});},[companyId]);
 useEffect(()=>{if(paused)return;let stopped=false,timer;
  const poll=async()=>{try{const result=await call('/gpu-telemetry');if(stopped)return;setData(result);setError('');setClock(Date.now());
    if(result.sampled_at&&result.status!=='stale')setHistory(old=>{const next={...old};for(const card of result.cards||[]){const prior=old[card.id]||[];if(prior.at(-1)?.at!==result.sampled_at)next[card.id]=[...prior,{at:result.sampled_at,value:card.utilization_percent??null}].slice(-60);}return next;});
   }catch(e){if(!stopped){setError(e.message);setClock(Date.now());}}
   finally{if(!stopped)timer=setTimeout(poll,5000);}};
  poll();return ()=>{stopped=true;clearTimeout(timer);};
 },[companyId,paused]);
 useEffect(()=>{const timer=setInterval(()=>setClock(Date.now()),1000);return ()=>clearInterval(timer);},[]);
 const age=data?.sampled_at?(clock-Date.parse(data.sampled_at))/1000:null;
 const stale=!!error||age===null||age>30||age<0||data?.status==='stale';
 return <section aria-label="Live GPU measurements"><div className="hq-row"><div><h2>Live GPU measurements</h2><p className="hq-muted">Utilization, VRAM and power from fixed driver probes. Refreshes every 5 seconds while running.</p></div><button onClick={()=>setPaused(x=>!x)}>{paused?'Resume live view':'Pause live view'}</button></div>
 <p role="status" className={stale?'hq-notice':'hq-muted'}>{paused?'Paused · ':''}{error?'Collection failed: '+error:data?.status==='collecting'?'Collecting the first sample…':stale?'Measurements are stale or unavailable.':paused?'Last measurements':'Live measurements'} {data?.sampled_at&&<> · Last sample {new Date(data.sampled_at).toLocaleTimeString()} ({Math.max(0,Math.round(age))}s ago)</>}</p>
 <div className="hq-grid">{(data?.cards||[]).map(card=>{const available=card.status!=='unavailable';return <article className="hq-card" key={card.id} data-gpu={card.id}><div className="hq-row"><h3>{card.system.toUpperCase()} · {card.card}</h3><span className="hq-badge">{stale?'stale':card.status}</span></div><p className="hq-muted">{card.name}</p>
  <div className="hq-metrics"><div><span>Compute utilization</span><strong>{available&&card.utilization_percent!=null?card.utilization_percent.toFixed(0)+'%':'Unavailable'}</strong></div><div><span>Power draw</span><strong>{available&&card.power_watts!=null?card.power_watts.toFixed(1)+' W':'Unavailable'}</strong></div></div>
  {card.utilization_percent!=null&&<progress aria-label={card.id+' compute utilization'} value={card.utilization_percent} max="100"/>}
  <p><strong>VRAM</strong> {gib(card.memory_used_bytes)} / {gib(card.memory_total_bytes)} GiB {card.memory_percent!=null?'('+card.memory_percent.toFixed(1)+'%)':''}</p>
  {card.memory_percent!=null&&<progress aria-label={card.id+' VRAM used'} value={card.memory_percent} max="100"/>}
  <p><strong>Temperature:</strong> {card.temperature_c!=null?card.temperature_c+' °C':'Unavailable'}{card.junction_temperature_c!=null?' · junction '+card.junction_temperature_c+' °C':''}{card.memory_temperature_c!=null?' · memory '+card.memory_temperature_c+' °C':''}</p>
  {card.power_limit_watts!=null&&<p className="hq-muted">Reported power cap: {card.power_limit_watts.toFixed(0)} W</p>}
  <Trend samples={history[card.id]||[]} label={card.id+' utilization history'}/>
  <p className="hq-muted">Recent utilization · 0–100% · up to 60 samples</p>
 </article>;})}</div><p className="hq-muted">Idle utilization can coexist with allocated VRAM. Power is the driver-reported GPU reading, not whole-system wall power. Missing metrics stay unavailable; opaque activity counters are not treated as percentages. These samples do not certify thermal health.</p></section>;
}

function Trend({samples,label}){
 const segments=[];let current=[];
 for(let i=0;i<samples.length;i++){const s=samples[i];if(s.value==null){if(current.length)segments.push(current);current=[];}else current.push([samples.length<2?0:i/(samples.length-1)*300,52-s.value/100*48]);}if(current.length)segments.push(current);
 return <svg viewBox="0 0 300 56" role="img" aria-label={label} style={{width:'100%',height:64,display:'block'}}><path d="M0 52H300 M0 4H300" fill="none" stroke="var(--border)"/>{segments.map((s,i)=><polyline key={i} points={s.map(p=>p.join(',')).join(' ')} fill="none" stroke="var(--primary)" strokeWidth="2"/> )}</svg>;
}

export function StackOverview({stack,link}){
 if(!stack||stack.status==='unavailable')return <p className="hq-notice">The stack inventory is unavailable. Live GPU readings are separate; refresh after the next scheduled collection.</p>;
 const contexts=stack.context?.agents||[];
 return <><div className="hq-row"><h2>Entire stack</h2><span className="hq-badge">{stack.agents?.length||0} Paperclip agents · {stack.services?.length||0} HQ runtime services</span></div>
 <p className={stack.status==='stale'?'hq-notice':'hq-muted'}>Inventory collected {new Date(stack.collected_at).toLocaleString()} · {stack.status}. Inventory refreshes every five minutes; this view checks every 30 seconds.</p>
 <div className="hq-grid">{(stack.integrations||[]).map(i=><section key={i.name} className="hq-card"><div className="hq-row"><h3>{i.name}</h3><span className="hq-badge">{i.status}</span></div><p className="hq-muted">{i.detail}</p></section>)}</div>
 <section className="hq-card"><h2>Context windows and model allocation</h2><p>Configured tokens are the per-request limit. Loaded tokens describe the currently resident model; agents on the same GPU can request different sizes. Neither value is conversation usage.</p>
 <div className="hq-table-wrap"><table><thead><tr><th>Runtime / target</th><th>GPU</th><th>Model</th><th>Configured tokens</th><th>Loaded tokens</th><th>Model maximum</th></tr></thead><tbody>{contexts.map(r=><tr key={r.target}><td><strong>{r.target}</strong>{r.experimental&&<span className="hq-badge">experimental</span>}</td><td>{r.backend.toUpperCase()}</td><td>{r.model}</td><td>{count(r.configured_tokens)}</td><td>{r.loaded_context_tokens==null?'Not loaded':count(r.loaded_context_tokens)}</td><td>{count(r.model_max_tokens)}</td></tr>)}</tbody></table></div>
 <p className="hq-muted">Discord compaction trigger: {count(stack.context?.compression?.threshold_tokens)} tokens, using Jessica. Model maximum does not establish available VRAM or acceptable latency.</p>
 <details><summary>Change or restore context settings on HQ</summary><p>Use the HQ command line. Set/reset commands preview by default; add <code>--apply</code> to save. Native model limits are checked, snapshots are retained, and affected profiles are synchronized. Coordinator/compaction changes restart the Discord gateway.</p><pre>{'cd /home/operator/krishadmin-hq/deployments/hermes\npython3 contextctl.py show\npython3 contextctl.py set louis 16384\npython3 contextctl.py set louis 16384 --apply\npython3 contextctl.py reset louis --apply\npython3 contextctl.py rollback SNAPSHOT_ID --apply'}</pre><p>Above 64K on NVIDIA-GPU requires <code>--experimental</code>. Verify a real run's GPU residency and reported allocation after changing a value.</p></details></section>
 <section className="hq-card"><h2>Every registered agent</h2><div className="hq-table-wrap"><table><thead><tr><th>Agent</th><th>State</th><th>Runtime</th><th>Model / context</th><th>Purpose</th></tr></thead><tbody>{(stack.agents||[]).map(a=><tr key={a.id}><td><a href={link('/agents/'+a.id)}>{a.name}</a></td><td>{a.status}</td><td>{a.backend?.toUpperCase()||a.runtime}</td><td>{a.model?<>{a.model}<br/>{count(a.context_tokens)} tokens</>:'Not a local model window'}</td><td>{a.title||a.runtime}</td></tr>)}</tbody></table></div><p className="hq-muted">Dispatcher and fixed diagnostic agents do not have a model context window. The external escalation agent uses its selected provider; its context is not changed by the local controls. Paperclip state is not GPU health.</p></section>
 <div className="hq-grid"><section className="hq-card"><h2>Runtime services</h2>{(stack.services||[]).map(s=><p key={s.Service}><strong>{s.Service}</strong> · {s.State} · {s.Health||'no healthcheck'}</p>)}</section>
 <section className="hq-card"><h2>Repositories and projects</h2>{(stack.repositories||[]).map(r=><div key={r.name}><a href={r.url} target="_blank" rel="noreferrer">{r.name}</a><p className="hq-muted">{r.status} · {r.default_branch||'branch unavailable'} · {r.open_issues_and_prs??'unknown'} open issues and PRs</p></div>)}<a className="hq-link" href={link('/projects')}>All Paperclip projects</a><a className="hq-link" href={link('/issues')}>All tasks</a></section>
 <section className="hq-card"><h2>Available HQ skills</h2><p>{(stack.skills||[]).map(s=>s.name).join(' · ')}</p><p className="hq-muted">Installed skills are guidance. Tool authorization and actual integration readiness still apply.</p></section></div>
 <section className="hq-card"><h2>Current findings and setup gaps</h2>{(stack.assessment?.alerts||[]).map((a,i)=><p key={i}><strong>{a.target||a.id}</strong>: {a.message}</p>)}{(stack.assessment?.setup_items||[]).map((a,i)=><p key={'setup'+i}>{a.message}</p>)}{!stack.assessment&&<p>Assessment unavailable.</p>}<details><summary>Backup observations</summary><pre>{JSON.stringify(stack.backup_status,null,2)}</pre></details></section>
 <section className="hq-card"><h2>Recent tasks and reports</h2>{(stack.tasks||[]).map(t=><p key={t.id}><a href={t.url}>{t.identifier} · {t.title}</a> <span className="hq-badge">{t.status}</span></p>)}{!stack.tasks?.length&&<p>No recent task data available.</p>}<p className="hq-muted">{stack.coverage}</p></section></>;
}
