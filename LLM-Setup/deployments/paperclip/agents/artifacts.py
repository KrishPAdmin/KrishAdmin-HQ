"""Bounded artifact publisher shared by observational runtimes."""
import json, mimetypes, urllib.request, uuid

def attachments(self, workspace):
    links = []
    secrets = self.private_values()
    for path in sorted(workspace.rglob('*'),key=lambda p:(p.name!='deliverables.zip',p.name!='test-results.txt',str(p))):
        self.require_active_run()
        relative = path.relative_to(workspace)
        if len(links) >= 5:
            break
        if path.is_symlink() or not path.is_file() or any(p.startswith('.') or p in ('__pycache__','node_modules') for p in relative.parts):
            continue
        if not path.resolve().is_relative_to(workspace.resolve()) or not 0 < path.stat().st_size <= 1048576:
            continue
        data = path.read_bytes()
        if any(secret.encode() in data for secret in secrets):
            raise RuntimeError('Artifact contained a credential; withheld from publication')
        boundary = 'paperclip-' + uuid.uuid4().hex
        filename = str(relative).replace('/', '_').replace('"', '_').replace('\r', '').replace('\n', '')
        mime = mimetypes.guess_type(filename)[0] or 'application/octet-stream'
        payload = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {mime}\r\n\r\n'.encode() + data + f'\r\n--{boundary}--\r\n'.encode())
        req = urllib.request.Request(self.api_base + f'/api/companies/{self.company_id}/issues/{self.issue["id"]}/attachments', data=payload,
            headers={**self.headers, 'Content-Type': f'multipart/form-data; boundary={boundary}'})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                attachment = json.load(response)
        except Exception:
            raise RuntimeError('Could not publish workspace artifact') from None
        content_path = attachment.get('contentPath') or '/api/attachments/' + attachment['id'] + '/content'
        links.append(f'[{filename}]({content_path})')
    return links
