"""Root-owned Unix service: run a Python file in one agent's isolated container."""
import json
import os
import pwd
import selectors
import socket
import socketserver
import struct
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path('/home/operator/KrishAdmin-LLM-Hub/agents')
AGENTS = ('jessica', 'harvey', 'louis', 'mike', 'rachel', 'donna', 'benjamin')
IMAGE = 'python@sha256:cb33f7f771ecec2ef1225cf39b159591a040391bd73e4c01f00fdfc4c47611d2'
UID = pwd.getpwnam('krishadmin').pw_uid

def command(body, name):
    if not isinstance(body, dict) or set(body) != {'agent', 'path'} or body['agent'] not in AGENTS:
        raise ValueError('Select one named agent and a workspace Python file')
    relative = body['path']
    if not isinstance(relative, str) or not relative.startswith('workspace/') or not relative.endswith('.py'):
        raise ValueError('Only workspace Python files can run')
    parts = relative.split('/')
    if len(parts) < 2 or any(not p or p.startswith('.') or '\\' in p or '\x00' in p for p in parts):
        raise ValueError('Unsafe path')
    home = ROOT / body['agent']; workspace = home / 'workspace'; file = home / relative
    if home.is_symlink() or workspace.is_symlink() or not file.is_file() or file.is_symlink() or not file.resolve().is_relative_to(workspace.resolve()):
        raise ValueError('Workspace links or missing files are refused')
    return ['/usr/bin/docker', 'run', '--rm', '--name', name, '--network', 'none', '--read-only',
            '--user', f'{UID}:{UID}', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--pids-limit', '64', '--memory', '512m', '--memory-swap', '512m', '--cpus', '1',
            '--ulimit', 'fsize=16777216:16777216', '--log-driver', 'none',
            '--tmpfs', '/tmp:rw,noexec,nosuid,size=64m',
            '--mount', f'type=bind,src={workspace},dst=/work',
            '--workdir', '/work', '--env', 'PYTHONDONTWRITEBYTECODE=1', IMAGE,
            'python3', '-I', '/work/' + '/'.join(parts[1:])]

def execute(body):
    name = 'hq-agent-sandbox-' + uuid.uuid4().hex
    args = command(body, name)
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    output = bytearray(); deadline = time.monotonic() + 60; reason = None
    selector = selectors.DefaultSelector(); selector.register(process.stdout, selectors.EVENT_READ)
    try:
        while True:
            if time.monotonic() > deadline:reason = '60-second limit'; break
            events = selector.select(.2)
            if events:
                data = os.read(process.stdout.fileno(), 4096)
                if not data:break
                output.extend(data)
                if len(output) > 12000:reason = 'output limit'; break
            elif process.poll() is not None:break
        if reason:
            subprocess.run(['/usr/bin/docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            process.kill()
        code = process.wait(timeout=10)
    finally:
        selector.close(); process.stdout.close()
        if process.poll() is None:process.kill(); process.wait()
        subprocess.run(['/usr/bin/docker', 'rm', '-f', name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    return {'agent': body['agent'], 'path': body['path'], 'exit_code': code,
            'status': 'limited' if reason else 'passed' if code == 0 else 'failed',
            'limit_reason': reason, 'output': output[:12000].decode(errors='replace'),
            'scope': 'Disposable Python container; only this agent workspace mounted; no network, credentials or other agent files. Workspace changes persist.'}

class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(90)
        try:
            _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if uid not in (0, UID):raise PermissionError('Caller refused')
            line = self.rfile.readline(2049)
            if len(line) > 2048 or not line.endswith(b'\n'):raise ValueError('Request too large')
            value = execute(json.loads(line))
        except Exception as error:value = {'error': type(error).__name__, 'status': 'failed'}
        self.wfile.write(json.dumps(value).encode() + b'\n')

if __name__ == '__main__':
    if int(os.environ.get('LISTEN_PID', '0')) != os.getpid() or os.environ.get('LISTEN_FDS') != '1':
        raise SystemExit('Start through systemd socket activation')
    with socketserver.UnixStreamServer('/run/hq-hub/sandbox.sock', Handler, bind_and_activate=False) as server:
        server.socket.close(); server.socket = socket.socket(fileno=3); server.serve_forever()
