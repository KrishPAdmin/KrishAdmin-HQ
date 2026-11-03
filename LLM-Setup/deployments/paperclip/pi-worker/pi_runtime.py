"""Paperclip lifecycle outside Pi; model tools run only inside the worker."""
import datetime
import fcntl
import json
import mimetypes
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid

sys.path.insert(0, '/opt/hq-agents')
import local_agent

class PiAgent(local_agent.Agent):
    def require_active_run(self):
        try:
            active = self.api('GET', f'/heartbeat-runs/{self.run_id}').get('status') == 'running'
        except Exception:
            active = False
        if not active:
            # SystemExit bypasses generic failure handling: never mutate a cancelled task.
            raise SystemExit(2)

    def review(self, content):
        self.require_active_run()
        return super().review(content)

    def private_values(self):
        values = [os.environ.get('PAPERCLIP_API_KEY', '')]
        for name in ('nvidia-gpu-token', 'amd-gpu-token', 'pi-bridge-token'):
            path = Path('/run/secrets') / name
            if path.exists():
                values.append(path.read_text().strip())
        return [v for v in values if len(v) > 6]

    def attachments(self, workspace):
        from artifacts import attachments
        return attachments(self, workspace)

    def infer(self, messages, schema=None):
        if schema is not None:
            raise RuntimeError('Pi worker supports specialist tasks only')
        workspace = Path('/workspace') / str(uuid.UUID(self.issue['id']))
        workspace.mkdir(parents=True, exist_ok=True)
        if self.internal_handoff() and self.issue.get('parentId'):
            parent = self.api('GET', f"/issues/{self.issue['parentId']}")
            if '[HQ routine: gpu-health]' in (parent.get('description') or ''):
                from operations import gpu_health, now, report
                data = {'checked_at_utc': now().isoformat(), 'gpu': gpu_health()}
                (workspace / 'cluster-health.json').write_text(json.dumps(data['gpu'], indent=2) + '\n')
                (workspace / 'report.md').write_text(report(data))
                self.require_active_run()
                links = self.attachments(workspace)
                self.execution_evidence = {'kind':'Deterministic Python tool / CPU','model_inference':False,'location':'HQ 192.0.2.180 / Pi worker container','model':None,'run_id':self.run_id}
                print(json.dumps({'event': 'pi_completed', 'collector': 'deterministic', 'artifacts': links}), flush=True)
                return report(data) + '\nDeliverables: ' + ', '.join(links), 'deterministic-gpu-api-collector', 0
        system = ('You are an internal workspace assistant with actual file and shell tools in an isolated container. '
                  'Complete the supplied task. Use tools when files or verification are requested. '
                  'Work only in the current workspace. Do not inspect /proc, credentials, secrets or other workspaces. '
                  'For requested live cluster checks, use only python3 /opt/worker/cluster_health.py; it is an approved read-only collector. Do not change remote systems. Never claim tool work without executing it. '
                  'Save deliverables as ordinary files in this workspace; final response must explain results and verification. '
                  'Do not manage Paperclip tasks yourself; the surrounding runtime handles checkout, artifacts and human review. '
                  'For exact file content, run an executable assertion of the actual bytes (including required newline), not a visual readback. Only report tests that actually passed. '
                  'After required files and checks succeed, stop using tools and give a final response below 120 words. Keep work to at most 12 tool calls.')
        system += f' The exact current workspace is {workspace}. Save every deliverable under this directory, never directly under /workspace.'
        prompt = messages[-1]['content']
        # Explicit allowlist excludes Paperclip JWT and bridge credentials from Pi environment.
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'NODE_EXTRA_CA_CERTS') if k in os.environ}
        env.update(HOME='/home/node', PI_CODING_AGENT_DIR='/home/node/.pi/agent', PI_OFFLINE='1', PI_TELEMETRY='0')
        command = ['pi', '--mode', 'json', '-p', '--provider', 'hq-nvidia-gpu', '--model', 'paperclip-qwen3.5:9b', '--thinking', 'off',
                   '--tools', 'read,bash,edit,write,grep,find,ls', '--no-session', '--no-skills', '--no-extensions',
                   '--no-context-files', '--append-system-prompt', system, prompt]
        start = time.monotonic()
        lockdir = Path('/paperclip/hq-locks'); lockdir.mkdir(exist_ok=True)
        with (lockdir / 'nvidia-gpu.lock').open('w') as lock:
            while True:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() - start > 180:
                        raise RuntimeError('GPU queue wait exceeded 180 seconds')
                    time.sleep(1)
            with tempfile.TemporaryFile() as output:
                proc = subprocess.Popen(command, cwd=workspace, env=env, stdout=output, stderr=subprocess.DEVNULL, start_new_session=True)
                deadline = time.monotonic() + 180
                # Monitor the output without returning prompts, tool bodies or credentials.
                while proc.poll() is None:
                    output_size = os.fstat(output.fileno()).st_size
                    if time.monotonic() > deadline or output_size > 8388608:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                        raise RuntimeError('Pi exceeded the tool-run deadline or output limit')
                    observed = os.pread(output.fileno(), output_size, 0)
                    starts = 0
                    for event_line in observed.splitlines():
                        try:
                            if json.loads(event_line).get('type') == 'tool_execution_start':
                                starts += 1
                        except (ValueError, AttributeError):
                            continue
                    if starts > 12:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                        raise RuntimeError('Pi exceeded the 12 tool-call pilot limit')
                    time.sleep(0.25)
                code = proc.returncode
                if code:
                    raise RuntimeError(f'Pi process exited with status {code}; inspect worker setup')
                if output.tell() > 8388608:
                    raise RuntimeError('Pi output exceeded the pilot limit')
                output.seek(0)
                raw = output.read().decode('utf-8', errors='replace')
        final = ''; inputs = outputs = turns = 0; tool_events = []
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get('type') == 'tool_execution_end':
                tool_events.append({'name': event.get('toolName'), 'is_error': bool(event.get('isError'))})
            if event.get('type') not in ('turn_end', 'message_end'):
                continue
            message = event.get('message') or {}
            if message.get('role') != 'assistant':
                continue
            if message.get('stopReason') in ('error', 'aborted', 'length'):
                reason = message.get('stopReason')
                detail = str(message.get('errorMessage', ''))[:160]
                for value in self.private_values():
                    detail = detail.replace(value, '[redacted]')
                raise RuntimeError(f'Pi model stopped: {reason}. {detail}')
            if event['type'] == 'turn_end':
                usage = message.get('usage') or {}; inputs += usage.get('input', 0); outputs += usage.get('output', 0); turns += 1
            content = message.get('content', [])
            text = content if isinstance(content, str) else ''.join(c.get('text', '') for c in content if c.get('type') == 'text')
            if text.strip():
                final = text.strip()
        if not final:
            raise RuntimeError('Pi returned no final response')
        if any(secret in final for secret in self.private_values()):
            raise RuntimeError('Pi response contained a credential; withheld from publication')
        elapsed = round(time.monotonic() - start, 2)
        self.api('POST', f'/companies/{self.company_id}/cost-events', {
            'agentId': self.agent_id, 'issueId': self.issue['id'], 'heartbeatRunId': self.run_id,
            'provider': 'ollama-local', 'model': 'paperclip-qwen3.5:9b', 'costCents': 0,
            'inputTokens': inputs, 'outputTokens': outputs,
            'occurredAt': datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')})
        self.require_active_run()
        links = self.attachments(workspace)
        if not links and any(word in prompt.lower() for word in ('.json', '.md', '.txt', 'artifact', 'create a file')):
            raise RuntimeError('No publishable file was produced in this task workspace; claimed file completion was rejected')
        final += '\n\nPi tool execution: ' + str(len(tool_events)) + ' tool events across ' + str(turns) + ' model turns.'
        if links:
            final += '\n\nDeliverables: ' + ', '.join(links)
        self.execution_evidence = {'kind':'Local model with CPU workspace tools','model_inference':True,'location':'HQ Pi worker for tools; NVIDIA-GPU endpoint 192.0.2.181 for model inference','model':'paperclip-qwen3.5:9b','seconds':elapsed,'input_tokens':inputs,'output_tokens':outputs,'run_id':self.run_id}
        summary = {'event': 'pi_completed', 'tool_events': tool_events, 'turns': turns, 'input_tokens': inputs, 'output_tokens': outputs, 'seconds': elapsed, 'artifacts': links}
        (workspace / '.pi-validation.json').write_text(json.dumps(summary, indent=2) + '\n')
        print(json.dumps(summary), flush=True)
        return final, 'paperclip-qwen3.5:9b (Pi 0.74.0)', elapsed

if __name__ == '__main__':
    local_agent.Agent = PiAgent
    sys.exit(local_agent.main())
