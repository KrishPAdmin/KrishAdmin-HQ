"""Owner-authenticated Hub workflow used by Discord and the local CLI."""
import hashlib
import json
import socket
from hq_client import call

def execute(body):
    if not isinstance(body, dict) or set(body) - {'action','agent','path','offset','limit','content','question','kind','_service'}:
        raise ValueError('Unknown Hub fields')
    body = dict(body); body.pop('_service', None)
    action = body.get('action')
    if action in ('list', 'read', 'write'):
        return call('/hub-files', body)
    agent = body.get('agent'); path = body.get('path')
    if action == 'review':
        if agent == 'benjamin':raise ValueError('For Benjamin, submit a coding/server_ops task and name the file in his inbox')
        source = call('/hub-files', {'action': 'read', 'agent': agent, 'path': path, 'offset': body.get('offset', 0), 'limit': body.get('limit', 12000)})
        question = body.get('question') or 'Review the supplied file. State the reviewed span and concrete findings.'
        result = call('/team', {'action': 'delegate', 'agent': agent, 'kind': body.get('kind', 'code_review' if agent == 'louis' else 'summarize'),
                               'question': question, 'text': json.dumps(source)})
        return {**result, 'source': {k: v for k, v in source.items() if k != 'text'}}
    if action == 'sandbox':
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(95); client.connect('/run/hq-hub/sandbox.sock')
            client.sendall(json.dumps({'agent': agent, 'path': path}).encode() + b'\n')
            with client.makefile('rb') as stream:raw = stream.readline(400001)
        if len(raw) > 400000:raise ValueError('Sandbox response too large')
        result = json.loads(raw)
        if result.get('error'):raise RuntimeError('Sandbox request failed; no execution success claimed')
        # A unique receipt preserves actual output and exit status without overwriting files.
        import uuid
        result['receipt'] = call('/hub-files', {'action': 'write', 'agent': agent,
            'path': 'deliverables/sandbox-' + uuid.uuid4().hex + '.json', 'content': json.dumps(result, indent=2)})
        return result
    raise ValueError('Choose list, read, write, review or sandbox')
