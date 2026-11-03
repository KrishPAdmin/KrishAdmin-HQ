"""CONNECT-only TLS tunnel to Discord; no LAN or arbitrary internet egress."""
import ipaddress,select,socket,socketserver
ALLOWED={'discord.com','gateway.discord.gg','cdn.discordapp.com','media.discordapp.net'}
class Handler(socketserver.StreamRequestHandler):
 def handle(self):
  self.connection.settimeout(15)
  try:
   line=self.rfile.readline(8192).decode('ascii').strip().split()
   if len(line)!=3 or line[0]!='CONNECT':raise ValueError()
   host,port=line[1].rsplit(':',1)
   if host not in ALLOWED or port!='443':raise ValueError()
   total=0
   while True:
    h=self.rfile.readline(8192);total+=len(h)
    if total>32768:raise ValueError()
    if h in (b'\r\n',b'\n',b''):break
   addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
   chosen=next(a for a in addresses if ipaddress.ip_address(a[4][0]).is_global)
   upstream=socket.socket(chosen[0],chosen[1],chosen[2]);upstream.settimeout(10);upstream.connect(chosen[4])
   self.wfile.write(b'HTTP/1.1 200 Connection Established\r\n\r\n');self.wfile.flush()
   self.connection.settimeout(None);upstream.settimeout(None)
   with upstream:
    while True:
     readable,_,_=select.select([self.connection,upstream],[],[],300)
     if not readable:return
     for src in readable:
      data=src.recv(65536)
      if not data:return
      (upstream if src is self.connection else self.connection).sendall(data)
  except Exception:
   try:self.wfile.write(b'HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n')
   except OSError:pass
class Server(socketserver.ThreadingTCPServer):allow_reuse_address=True;daemon_threads=True
if __name__=='__main__':Server(('0.0.0.0',8888),Handler).serve_forever()
