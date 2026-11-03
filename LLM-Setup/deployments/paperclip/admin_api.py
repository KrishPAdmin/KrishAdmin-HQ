"""Local operator helper; credentials never go into agent mounts or output."""
import http.cookiejar
import json
import os
import pathlib
import secrets
import ssl
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
URL = "https://paperclip.example.invalid"


class Admin:
    def __init__(self):
        ctx = ssl.create_default_context()
        ctx.load_verify_locations(cafile=str(ROOT.parent / "n8n/tls/server.crt"))
        self.cookies = http.cookiejar.LWPCookieJar(str(ROOT / "session.cookies"))
        if (ROOT / "session.cookies").exists():
            self.cookies.load(ignore_discard=True)
        self.client = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=ctx),
            urllib.request.HTTPCookieProcessor(self.cookies),
        )

    def api(self, method, path, body=None):
        request = urllib.request.Request(
            URL + path, method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json", "Origin": URL},
        )
        try:
            with self.client.open(request, timeout=60) as response:
                raw = response.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as error:
            # API validation errors are useful; never include the request credentials.
            raise RuntimeError(f"{method} {path}: HTTP {error.code}: {error.read().decode()[:1500]}") from None

    def login(self, bootstrap=False):
        if not bootstrap and len(self.cookies):
            try:
                session = self.api("GET", "/api/auth/get-session")
            except RuntimeError as error:
                if "HTTP 401:" not in str(error):
                    raise
                session = None
            if session and session.get("user"):
                return self
        path = ROOT / "admin-credentials.json"
        if not path.exists():
            if not bootstrap:
                raise RuntimeError("Run bootstrap first")
            path.write_text(json.dumps({
                "email": "krishadmin@hq.internal",
                "password": secrets.token_urlsafe(24),
                "name": "KrishAdmin",
                "url": URL,
            }, indent=2) + "\n")
            path.chmod(0o600)
        credentials = json.loads(path.read_text())
        if bootstrap:
            self.api("POST", "/api/auth/sign-up/email", {
                k: credentials[k] for k in ("email", "password", "name")
            })
            self.api("POST", "/api/bootstrap/claim", {})
        else:
            self.api("POST", "/api/auth/sign-in/email", {
                k: credentials[k] for k in ("email", "password")
            })
        temporary = ROOT / (".session.cookies." + secrets.token_hex(4))
        temporary.touch(mode=0o600)
        self.cookies.save(str(temporary), ignore_discard=True)
        os.replace(temporary, ROOT / "session.cookies")
        return self


if __name__ == "__main__":
    import sys
    admin = Admin().login(bootstrap="--bootstrap" in sys.argv)
    print("Operator authentication successful")
    print(json.dumps(admin.api("GET", "/api/companies"), indent=2))
