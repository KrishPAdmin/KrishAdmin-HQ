"""Local TLS vault transport. Errors never include request/response secret material."""
import json,ssl,urllib.request,urllib.error,subprocess
from pathlib import Path
BASE='https://127.0.0.1:8200/v1/'
CA='/etc/openbao/tls.crt'
class VaultError(RuntimeError):
    def __init__(self,message,status=None):
        super().__init__(message);self.status=status
def api(path,body=None,token=None,method=None):
    headers={'Content-Type':'application/json'}
    if token:headers['X-Vault-Token']=token
    req=urllib.request.Request(BASE+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
    try:
        with urllib.request.urlopen(req,context=ssl.create_default_context(cafile=CA),timeout=10) as response:
            raw=response.read();return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:raise VaultError('Vault request rejected (HTTP '+str(e.code)+')',status=e.code) from None
    except (OSError,ValueError):raise VaultError('Vault unavailable or invalid response') from None
def login(role):
    if role not in {'connector','runtime','operator'}:raise VaultError('Unknown connector identity')
    try:
        raw=subprocess.check_output(['/usr/bin/systemd-creds','decrypt','--name='+role,'/etc/credstore.encrypted/hq-vault-'+role,'-'],stderr=subprocess.DEVNULL)
        auth=json.loads(raw)
    except (OSError,ValueError,subprocess.CalledProcessError):raise VaultError('Connector identity unavailable') from None
    return api('auth/approle/login',auth)['auth']['client_token']
def read_secret(name,token):
    return api('homelab/data/'+name,token=token)['data']['data']['value']
