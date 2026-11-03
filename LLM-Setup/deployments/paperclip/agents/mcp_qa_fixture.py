#!/usr/bin/env python3
"""Local synthetic MCP transport fixture. No credentials, writes or networking."""
import json,sys
TOOLS=[{'name':'list_items','description':'List synthetic Control Center QA items.','inputSchema':{'type':'object','properties':{}},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True}},
 {'name':'get_value','description':'Read a synthetic QA value.','inputSchema':{'type':'object','properties':{'key':{'type':'string'}}},'annotations':{'readOnlyHint':True,'destructiveHint':False,'idempotentHint':True}}]
for line in sys.stdin:
 try:
  req=json.loads(line)
  if 'id' not in req:continue
  method=req.get('method');rid=req['id']
  if method=='initialize':result={'protocolVersion':'2025-03-26','capabilities':{'tools':{}},'serverInfo':{'name':'krishadmin-synthetic-qa','version':'1.0.0'}}
  elif method=='tools/list':result={'tools':TOOLS}
  elif method=='tools/call':
   name=(req.get('params') or {}).get('name')
   if name=='list_items':data={'items':[{'id':'qa-1','title':'Verify read-only transport'},{'id':'qa-2','title':'Verify private data stays local'}]}
   elif name=='get_value':data={'value':'synthetic-local-only'}
   else:raise ValueError('Only synthetic reads are available')
   result={'content':[{'type':'text','text':json.dumps(data)}],'isError':False}
  elif method=='ping':result={}
  else:raise ValueError('Unsupported MCP method')
  print(json.dumps({'jsonrpc':'2.0','id':rid,'result':result}),flush=True)
 except Exception:print(json.dumps({'jsonrpc':'2.0','id':req.get('id') if isinstance(req,dict) else None,'error':{'code':-32601,'message':'Unsupported synthetic fixture operation'}}),flush=True)
