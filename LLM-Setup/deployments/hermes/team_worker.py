"""Individual named specialist runtime on HQ, with fixed local GPU identity."""
import hmac,json,os,threading,time,urllib.request,uuid
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from team import TEAM
from capabilities import prompt_for
NAME=os.environ['HQ_PROFILE'];ROLE=TEAM[NAME];LOCK=threading.Lock()

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.send(200,{'status':'ok','agent':NAME,'backend':ROLE['backend'],'model':ROLE['model'],'tools':[]})
    def do_POST(self):
        if self.path!='/run':return self.send(404,{'error':'not found'})
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+Path('/run/access/worker').read_text().strip()):return self.send(403,{'error':'forbidden'})
        if not LOCK.acquire(False):return self.send(429,{'error':'specialist busy'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=60000:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(size));kind=body.get('task_kind','plan')
            system,prompt=prompt_for(kind,body['question'],body['evidence'])
            system=ROLE['persona']+' '+system
            if len((system+prompt).encode())>6500:raise ValueError('Named-specialist prompt exceeds conservative context budget; use a smaller excerpt')
            request=urllib.request.Request('http://broker:8080/v1/chat/completions',
                data=json.dumps({'model':ROLE['model'],'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
                                 'max_tokens':ROLE['max_tokens']}).encode(),
                headers={'Content-Type':'application/json','Authorization':'Bearer '+Path('/run/access/identity').read_text().strip()})
            start=time.monotonic()
            with urllib.request.urlopen(request,timeout=500) as response:result=json.load(response)
            value={'agent':NAME,'name':ROLE['name'],'backend':ROLE['backend'],'model':ROLE['model'],'text':result['choices'][0]['message']['content'],
                   'run_id':result['id'],'seconds':round(time.monotonic()-start,3),'tools':[],'agent_host':'HQ gateway','task_kind':kind,'usage':result['usage']}
            folder=Path('/profile/runs');folder.mkdir(exist_ok=True)
            path=folder/(str(uuid.uuid4())+'.json');path.write_text(json.dumps({k:v for k,v in value.items() if k!='text'},indent=2)+'\n');path.chmod(0o600)
            self.send(200,value)
        except ValueError as error:self.send(400,{'error':str(error)[:250]})
        except Exception as error:self.send(502,{'error':type(error).__name__})
        finally:LOCK.release()

if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
