"""Host-only credential transport for existing fixed diagnostic connectors."""
import json,os,socket,socketserver,struct,pwd,grp
from pathlib import Path
from vault_common import api,login,read_secret
SOCKET='/run/hq-vault/connector.sock'
ALLOWED={'pi-cluster','amd-gpu-ssh'}
UID=pwd.getpwnam('krishadmin').pw_uid
class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            _,uid,_=struct.unpack('3i',self.connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            if uid not in (0,UID):raise PermissionError()
            line=self.rfile.readline(257)
            if len(line)>256 or not line.endswith(b'\n'):raise ValueError()
            request=json.loads(line)
            if set(request)!={'name'} or request['name'] not in ALLOWED:raise PermissionError()
            token=login('connector')
            try:value=read_secret(request['name'],token)
            finally:api('auth/token/revoke-self',{},token)
            self.wfile.write(json.dumps({'value':value}).encode()+b'\n')
        except Exception:
            self.wfile.write(b'{"error":"Credential unavailable or access denied"}\n')
class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads=True
if __name__=='__main__':
    # The system manager creates the socket outside this service's mount namespace.
    # This preserves AppArmor access from hardened unprivileged host collectors.
    if int(os.environ.get('LISTEN_PID','0'))!=os.getpid() or os.environ.get('LISTEN_FDS')!='1':
        raise SystemExit('Start through hq-vault-connector.socket')
    with Server(SOCKET,Handler,bind_and_activate=False) as server:
        server.socket.close()
        server.socket=socket.socket(fileno=3)
        server.serve_forever()
