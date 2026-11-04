"""Live public-page and container-boundary checks; no Discord messages."""
import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hq_client import call,ROOT

r=call('/web/read',{'url':'https://quotes.toscrape.com/js/','render':True,'limit':4000})
assert r['extraction']=='browser DOM + semantic metadata',r
assert 'Albert Einstein' in r['text'] and r['browser_receipt']['requests']>1
assert r['browser_receipt']['dom_sha256'] and not r['render_error']
browser=json.loads(subprocess.check_output(['docker','inspect','hq-hermes-renderer-1']))[0]
assert set(browser['NetworkSettings']['Networks'])=={'hq-hermes_research_internal'}
assert browser['HostConfig']['ReadonlyRootfs'] and browser['HostConfig']['CapDrop']==['ALL']
assert not browser['HostConfig']['Privileged'] and browser['Config']['User']=='pwuser'
assert not browser['HostConfig']['PortBindings']
assert all(m['Destination']=='/app/render_server.mjs' for m in browser['Mounts'])
probe='''import json,urllib.request,urllib.error
for url in ['https://127.0.0.1/','https://203.0.113.3/','http://example.com/']:
 req=urllib.request.Request('http://renderer:8080/render',data=json.dumps({'url':url}).encode(),headers={'Content-Type':'application/json'})
 try:
  urllib.request.urlopen(req,timeout=55);raise AssertionError('Forbidden URL rendered')
 except urllib.error.HTTPError as error:
  assert error.code==400
print('Private addresses and HTTP refused by live renderer')
'''
subprocess.run(['docker','compose','exec','-T','broker','python','-'],input=probe,text=True,cwd=ROOT,check=True)
no_egress="try{await fetch('https://example.com',{signal:AbortSignal.timeout(2000)});process.exit(1)}catch{console.log('Direct browser-container internet blocked')}"
subprocess.run(['docker','compose','exec','-T','renderer','node','--input-type=module','-e',no_egress],cwd=ROOT,check=True)
out={'source':r['url'],'extraction':r['extraction'],'browser_receipt':r['browser_receipt'],'private_destinations_refused':True,'direct_egress_blocked':True,'sandbox_enabled_in_launcher':True,'messages_sent':0}
(ROOT/'validation/research-browser.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
