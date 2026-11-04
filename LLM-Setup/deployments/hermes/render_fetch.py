"""Public HTTPS-only fetch relay for the network-isolated research browser.

No credentials, cookies, POSTs to websites, arbitrary headers or private addresses.
"""
import base64,json,threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from web_research import fetch
LIMIT=threading.BoundedSemaphore(8)
class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,body):
        data=json.dumps(body).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_GET(self):self.send(200,{'service':'public-fetch','status':'ok'})
    def do_POST(self):
        if self.path!='/fetch':return self.send(404,{'error':'not found'})
        if not LIMIT.acquire(False):return self.send(429,{'error':'fetch capacity busy'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<8192:raise ValueError('Invalid request size')
            body=json.loads(self.rfile.read(size))
            if set(body)!={'url'} or not isinstance(body['url'],str):raise ValueError('Supply only a public HTTPS URL')
            # Every redirect is DNS-validated by fetch. Return the final URL so
            # the browser navigates there before interpreting relative URLs.
            page=fetch(body['url'],limit=2*1024*1024)
            if page['download_truncated']:raise ValueError('Browser resource exceeds 2 MiB')
            self.send(200,{'url':page['url'],'content_type':page['content_type'],'response_headers':page.get('response_headers',{}),'body':base64.b64encode(page['raw']).decode()})
        except Exception as error:self.send(400,{'error':str(error)[:180]})
        finally:LIMIT.release()
if __name__=='__main__':ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
