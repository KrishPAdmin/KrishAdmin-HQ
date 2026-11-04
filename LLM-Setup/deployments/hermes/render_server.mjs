// Read-only browser extraction. Chromium has no external network route: every
// HTTPS GET is fulfilled by the DNS-pinned public fetch relay on HQ.
import http from 'node:http';
import crypto from 'node:crypto';
import {chromium} from 'playwright-core';
let busy=false;
const send=(res,status,value)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value));};
function publicShape(value){
  const u=new URL(value);
  if(u.protocol!=='https:'||u.username||u.password||(u.port&&u.port!=='443'))throw Error('Only public HTTPS URLs without credentials');
  return u;
}
async function render(url){
  publicShape(url);
  const browser=await chromium.launch({headless:true,chromiumSandbox:true,args:['--disable-dev-shm-usage','--disable-background-networking','--disable-quic']});
  let requests=0,bytes=0,blocked=0;
  const deadline=setTimeout(()=>browser.close().catch(()=>{}),45000);
  try{
    const context=await browser.newContext({acceptDownloads:false,serviceWorkers:'block',javaScriptEnabled:true});
    await context.routeWebSocket('**/*',ws=>ws.close());
    await context.route('**/*',async route=>{
      const req=route.request();
      try{
        publicShape(req.url());
        if(req.method()!=='GET'||['image','media','font'].includes(req.resourceType())||++requests>64||bytes>16*1024*1024)throw Error('Request outside read-only browser budget');
        const response=await fetch('http://render-fetch:8080/fetch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:req.url()}),signal:AbortSignal.timeout(16000)});
        const data=await response.json();if(!response.ok)throw Error(data.error||'Resource fetch failed');
        if(data.url!==req.url()){
          await route.fulfill({status:302,headers:{location:data.url},body:''});return;
        }
        const body=Buffer.from(data.body,'base64');bytes+=body.length;
        if(bytes>16*1024*1024)throw Error('Page byte budget exceeded');
        await route.fulfill({status:200,contentType:data.content_type,headers:data.response_headers||{},body});
      }catch{
        blocked++;await route.abort('blockedbyclient').catch(()=>{});
      }
    });
    const page=await context.newPage();page.on('dialog',dialog=>dialog.dismiss().catch(()=>{}));
    const response=await page.goto(url,{waitUntil:'domcontentloaded',timeout:30000});
    if(!response||response.status()>=400)throw Error('Page navigation failed');
    await page.waitForLoadState('networkidle',{timeout:7000}).catch(()=>{});
    await page.waitForTimeout(1000);
    const title=await page.title();
    if(/just a moment|verify you are human|access denied/i.test(title))throw Error('Site challenge or access denial; no bypass attempted');
    const full=await page.locator('body').innerText({timeout:5000});
    const text=full.slice(0,80000);
    return {url:page.url(),title,text,dom_sha256:crypto.createHash('sha256').update(full).digest('hex'),truncated:full.length>text.length,requests,bytes,blocked_requests:blocked,collector:'HQ isolated browser',fetched_at:new Date().toISOString()};
  }finally{clearTimeout(deadline);await browser.close();}
}
http.createServer(async(req,res)=>{
  if(req.method==='GET'&&req.url==='/health')return send(res,200,{status:'ok',service:'renderer'});
  if(req.method!=='POST'||req.url!=='/render')return send(res,404,{error:'not found'});
  if(busy)return send(res,429,{error:'Browser busy; retry later'});
  busy=true;
  try{
    let raw='';for await(const chunk of req){raw+=chunk;if(raw.length>8192)throw Error('Request too large');}
    const body=JSON.parse(raw);if(Object.keys(body).some(k=>k!=='url')||typeof body.url!=='string')throw Error('Supply only a URL');
    send(res,200,await render(body.url));
  }catch(error){send(res,400,{error:String(error.message).slice(0,220)});}
  finally{busy=false;}
}).listen(8080,'0.0.0.0');
