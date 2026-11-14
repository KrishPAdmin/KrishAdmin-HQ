"""Explicit file delivery from the upload/draft cache, bound to the current reply."""
import hashlib,json,re
from pathlib import Path

ROOT=Path('/profile/cache/documents')
MAX_BYTES=5*1024*1024

def resolve(file_id):
    if not isinstance(file_id,str) or not re.fullmatch(r'[a-zA-Z0-9_. -]{1,200}',file_id):raise ValueError('Use a file_id or draft name, not a path')
    if re.fullmatch(r'doc_[a-f0-9]{12}_[^/\\]{1,180}',file_id):
        if re.search(r'(?:^|_)\.?env(?:\.|$)|id_(?:rsa|ed25519)|private.?key',file_id,re.I):raise ValueError('Credential files cannot be delivered')
        path=ROOT/file_id
    elif re.fullmatch(r'[a-zA-Z0-9_-]+-[a-f0-9]{12}\.(md|txt|py|sh|json|yaml|yml|js|ts|sql|csv)',file_id):path=ROOT/'drafts'/file_id
    else:raise ValueError('Use an uploaded file_id or a name returned by hq_draft')
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()) or not path.is_file():raise ValueError('File is missing or is not an authorized cache file')
    if path.stat().st_size>MAX_BYTES:raise ValueError('File exceeds 5 MiB')
    return path

def send_file(args,**kwargs):
    try:
        from gateway.session_context import get_session_env
        if get_session_env('HERMES_SESSION_PLATFORM')!='discord':raise ValueError('File delivery requires a Discord conversation')
        path=resolve(args.get('file_id'));data=path.read_bytes()
        return json.dumps({'delivery_requested':True,'file_id':path.name,'delivery_path':str(path),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'status':'queued_for_current_reply'})
    except (OSError,ValueError) as error:return json.dumps({'error':str(error)})

def install():
    import gateway.run as run
    original=run._collect_auto_append_media_tags
    if getattr(original,'_hq_files',False):return
    def collect(messages,history_offset=0,history_media_paths=None):
        tags,voice=original(messages,history_offset,history_media_paths)
        if history_offset>len(messages):return tags,voice
        current=messages[history_offset:];calls=run._tool_name_by_call_id(current)
        for message in current:
            if message.get('role') not in ('tool','function'):continue
            if calls.get(str(message.get('tool_call_id') or message.get('call_id') or ''))!='hq_send_file':continue
            try:
                value=json.loads(message.get('content') or '{}')
                if value.get('delivery_requested') is not True or value.get('error'):continue
                path=resolve(value.get('file_id'))
                if str(path)!=value.get('delivery_path'):continue
                if hashlib.sha256(path.read_bytes()).hexdigest()!=value.get('sha256'):continue
                tag='MEDIA:'+str(path)
                if str(path) not in (history_media_paths or set()) and tag not in tags:tags.append(tag)
            except (OSError,ValueError,TypeError,AttributeError):continue
        return tags,voice
    collect._hq_files=True
    run._collect_auto_append_media_tags=collect
