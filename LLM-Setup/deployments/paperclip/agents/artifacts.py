"""Bounded artifact publisher shared by observational runtimes."""
import json, mimetypes, urllib.request, uuid, os

def mirror(root, issue_id, run_id, filename, data):
    """Mirror only artifacts that already passed publication checks; no link following."""
    folder=str(uuid.UUID(issue_id))+'-'+str(uuid.UUID(run_id))
    base=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        try:os.mkdir(folder,mode=0o700,dir_fd=base)
        except FileExistsError:pass
        directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=base)
        try:
            name=uuid.uuid4().hex[:8]+'-'+filename.encode()[:180].decode(errors='ignore')
            fd=os.open(name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
            with os.fdopen(fd,'wb') as stream:stream.write(data)
        finally:os.close(directory)
    finally:os.close(base)

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
        if getattr(self,'hub_deliverables',None):
            mirror(self.hub_deliverables,self.issue['id'],self.run_id,filename,data)
    return links
