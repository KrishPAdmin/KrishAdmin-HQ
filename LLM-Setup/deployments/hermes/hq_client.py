"""Local broker client; credentials stay in headers and are never printed."""
import json,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def call(route,body=None,timeout=550):
    token=(ROOT/'access/operator').read_text().strip()
    request=urllib.request.Request('http://127.0.0.1:18880'+route,data=json.dumps(body or {}).encode(),
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=timeout) as response:return json.load(response)
    except urllib.error.HTTPError as error:raise RuntimeError('HQ broker returned HTTP '+str(error.code)) from None
    except (urllib.error.URLError,TimeoutError):raise RuntimeError('HQ broker could not be reached before the deadline') from None
