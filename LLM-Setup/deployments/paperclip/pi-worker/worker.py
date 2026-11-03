"""Private authenticated, single-job worker. Never returns raw agent output."""
import hmac
import json
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEYS = ('PAPERCLIP_AGENT_ID', 'PAPERCLIP_COMPANY_ID', 'PAPERCLIP_RUN_ID', 'PAPERCLIP_API_KEY')
GATE = threading.Lock()

def kill_tree(pid):
    children = {}
    for item in Path('/proc').iterdir():
        if not item.name.isdigit():
            continue
        try:
            stat = (item / 'stat').read_text().rsplit(')', 1)[1].split()
            children.setdefault(int(stat[1]), []).append(int(item.name))
        except (OSError, ValueError, IndexError):
            continue
    def kill(current):
        for child in children.get(current, []):
            kill(child)
        try:
            os.kill(current, signal.SIGKILL)
        except ProcessLookupError:
            pass
    kill(pid)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def reply(self, code, value):
        payload = json.dumps(value).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        self.reply(200 if self.path == '/health' else 404, {'ok': self.path == '/health'})

    def do_POST(self):
        self.connection.settimeout(15)
        secret = Path('/run/secrets/pi-bridge-token').read_text().strip()
        if self.path != '/run' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + secret):
            self.reply(403, {'error': 'Forbidden'})
            return
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError()
            body = json.loads(self.rfile.read(length))
            if not isinstance(body, dict) or any(not isinstance(body.get(k), str) or not body[k] for k in KEYS):
                raise ValueError()
        except (ValueError, TypeError):
            self.reply(400, {'error': 'Invalid job'})
            return
        if not GATE.acquire(blocking=False):
            self.reply(409, {'error': 'Worker busy; retry after current job completes'})
            return
        try:
            env = dict(os.environ)
            env.update({k: body[k] for k in KEYS})
            env.update(PAPERCLIP_API_URL='http://server:3100', HQ_BACKEND='nvidia-gpu', HQ_MODE='specialist')
            proc = subprocess.Popen(['python3', '/opt/worker/pi_runtime.py'], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
            try:
                deadline = time.monotonic() + 420
                while True:
                    try:
                        raw, error_output = proc.communicate(timeout=2)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() > deadline:
                            raise
                        try:
                            req = urllib.request.Request('http://server:3100/api/heartbeat-runs/' + body['PAPERCLIP_RUN_ID'], headers={'Authorization': 'Bearer ' + body['PAPERCLIP_API_KEY']})
                            with urllib.request.urlopen(req, timeout=5) as response:
                                active = json.load(response).get('status') == 'running'
                        except Exception:
                            active = False
                        if not active:
                            kill_tree(proc.pid)
                            proc.communicate()
                            self.reply(200, {'ok': False, 'exit_code': 2, 'summaries': [{'event': 'pi_cancelled', 'reason': 'Origin run is not active or could not be verified'}]})
                            return
            except subprocess.TimeoutExpired:
                kill_tree(proc.pid)
                proc.communicate()
                raise
            summaries = []
            for line in (raw + error_output).decode('utf-8', errors='replace').splitlines():
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('event') == 'failed':
                    message = str(event.get('error', 'Runtime failed'))[:300]
                    for value in (body.get('PAPERCLIP_API_KEY'), secret):
                        if value:
                            message = message.replace(value, '[redacted]')
                    summaries.append({'event': 'pi_runtime_failed', 'error': message})
                if event.get('event') == 'pi_completed':
                    summaries.append({key: event.get(key) for key in ('event', 'tool_events', 'turns', 'input_tokens', 'output_tokens', 'seconds')})
            self.reply(200, {'ok': proc.returncode == 0, 'exit_code': proc.returncode, 'summaries': summaries})
        except subprocess.TimeoutExpired:
            self.reply(504, {'error': 'Worker runtime deadline exceeded; job tree stopped'})
        except Exception:
            self.reply(500, {'error': 'Worker runtime failure'})
        finally:
            GATE.release()

if __name__ == '__main__':
    ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
