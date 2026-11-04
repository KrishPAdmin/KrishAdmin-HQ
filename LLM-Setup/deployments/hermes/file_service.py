"""Restricted upload reader. No arbitrary paths, network fetching or file execution."""
import hashlib,hmac,json,os,re,resource,subprocess,sys,zipfile
from pathlib import Path
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer

ROOT=Path('/uploads');MAX_BYTES=5*1024*1024;MAX_TEXT=100000
TEXT={'.txt','.md','.csv','.tsv','.json','.yaml','.yml','.toml','.ini','.conf','.cfg','.xml','.html','.css','.py','.sh','.js','.ts','.jsx','.tsx','.sql','.log','.dockerfile'}
SUPPORTED=TEXT|{'.pdf','.docx','.xlsx'}

def upload(file_id):
    if not isinstance(file_id,str) or not re.fullmatch(r'doc_[a-f0-9]{12}_[^/\\\x00-\x1f]{1,180}',file_id):raise ValueError('Use an uploaded file_id returned by hq_files list; arbitrary paths are not allowed')
    path=ROOT/file_id
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Upload symlinks are not allowed')
    if not path.is_file():raise ValueError('Upload not found or its cache has expired')
    if path.stat().st_size>MAX_BYTES:raise ValueError('Upload exceeds 5 MiB')
    if path.suffix.lower() not in SUPPORTED:raise ValueError('Unsupported file type; use text/code/config, PDF, DOCX or XLSX')
    if re.search(r'(?:^|_)\.?env(?:\.|$)|id_(?:rsa|ed25519)|private.?key',file_id,re.I):raise ValueError('Credential files are not accepted for document review')
    return path

def extract(path):
    suffix=path.suffix.lower();truncated=False
    if suffix in TEXT:
        text=path.read_text(encoding='utf-8-sig')
        if '\x00' in text:raise ValueError('Binary content is not supported as text')
    elif suffix=='.pdf':
        from pypdf import PdfReader
        reader=PdfReader(path)
        if reader.is_encrypted:raise ValueError('Encrypted PDFs are not supported')
        parts=[];size=0;truncated=len(reader.pages)>100
        for page in reader.pages[:100]:
            part=page.extract_text() or '';parts.append(part);size+=len(part)
            if size>MAX_TEXT:truncated=True;break
        text='\n'.join(parts)
        if not text.strip():raise ValueError('No extractable text; scanned images need OCR, which is not enabled')
    else:
        with zipfile.ZipFile(path) as archive:
            entries=archive.infolist()
            if len(entries)>2000 or sum(e.file_size for e in entries)>20*1024*1024:raise ValueError('Document expands beyond extraction limits')
        if suffix=='.docx':
            from docx import Document
            doc=Document(path);parts=[p.text for p in doc.paragraphs]
            for table in doc.tables:
                parts.extend('\t'.join(c.text for c in row.cells) for row in table.rows)
            text='\n'.join(parts)
        else:
            from openpyxl import load_workbook
            book=load_workbook(path,read_only=True,data_only=False,keep_links=False)
            parts=[];size=0
            try:
                for sheet in book:
                    parts.append('Sheet: '+sheet.title)
                    for values in sheet.iter_rows(values_only=True):
                        line='\t'.join('' if v is None else str(v) for v in values);parts.append(line);size+=len(line)
                        if size>MAX_TEXT:truncated=True;break
                    if truncated:break
            finally:book.close()
            text='\n'.join(parts)
    return {'text':text[:MAX_TEXT],'extraction_truncated':truncated or len(text)>MAX_TEXT}

def validate_syntax(path):
    import ast,tomllib
    suffix=path.suffix.lower()
    if suffix not in ('.py','.json','.toml','.yaml','.yml'):
        return {'status':'not_supported','scope':'Syntax checks support Python, JSON, TOML and YAML only','executed':False}
    text=path.read_text(encoding='utf-8-sig')
    try:
        if suffix=='.py':ast.parse(text)
        elif suffix=='.json':json.loads(text)
        elif suffix=='.toml':tomllib.loads(text)
        elif suffix in ('.yaml','.yml'):
            import yaml
            list(yaml.safe_load_all(text))
        else:return {'status':'not_supported','scope':'Syntax checks support Python, JSON, TOML and YAML only','executed':False}
        return {'status':'passed','scope':'Syntax only; no code, formulas or workflows executed','executed':False}
    except (SyntaxError,ValueError) as error:
        return {'status':'failed','error_type':type(error).__name__,'line':getattr(error,'lineno',None),'executed':False}
    except Exception as error:return {'status':'failed','error_type':type(error).__name__,'executed':False}

def operation(body):
    action=body.get('action','list')
    if action=='list':
        rows=[]
        for path in sorted(ROOT.glob('doc_*'),key=lambda p:p.lstat().st_mtime,reverse=True)[:100]:
            try:path=upload(path.name)
            except ValueError:continue
            rows.append({'file_id':path.name,'name':path.name[17:],'bytes':path.stat().st_size,'type':path.suffix.lower()})
        return {'files':rows,'scope':'Authorized Discord upload cache only; cached files may expire.'}
    if action not in ('read','validate'):raise ValueError('Unsupported upload operation')
    path=upload(body.get('file_id'));offset=body.get('offset',0);limit=body.get('limit',3000)
    if action=='validate':
        result=subprocess.run([sys.executable,__file__,'--validate',str(path)],capture_output=True,text=True,timeout=20)
        if result.returncode:raise ValueError('Validation could not complete within limits')
        return {'file_id':path.name,'validation':json.loads(result.stdout)}
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=50000:raise ValueError('Use a nonnegative character offset and limit 1–50000')
    result=subprocess.run([sys.executable,__file__,'--extract',str(path)],capture_output=True,text=True,timeout=20)
    if result.returncode:raise ValueError('Document could not be extracted within limits; encrypted, malformed and image-only documents are not supported')
    data=json.loads(result.stdout);text=data['text'];chunk=text[offset:offset+limit]
    with path.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
    return {'file_id':path.name,'sha256':sha,'text':chunk,'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(text) else None,
            'extracted_characters':len(text),'extraction_truncated':data['extraction_truncated'],
            'scope':'This is an extracted slice, not necessarily the whole file. Formulas/macros/scripts are never executed.'}

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def send(self,status,data):
        raw=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
    def do_GET(self):self.send(200,{'status':'ok','service':'files'})
    def do_POST(self):
        if self.path!='/files':return self.send(404,{'error':'not found'})
        if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+Path('/run/access/worker').read_text().strip()):return self.send(403,{'error':'forbidden'})
        try:
            size=int(self.headers.get('Content-Length',0))
            if not 0<size<=4096:raise ValueError('Invalid request size')
            self.send(200,operation(json.loads(self.rfile.read(size))))
        except (ValueError,TypeError,KeyError) as error:self.send(400,{'error':str(error)[:250]})
        except Exception as error:self.send(502,{'error':type(error).__name__})

if __name__=='__main__':
    if len(sys.argv)==3 and sys.argv[1] in ('--extract','--validate'):
        resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024));resource.setrlimit(resource.RLIMIT_CPU,(15,15))
        print(json.dumps(extract(Path(sys.argv[2])) if sys.argv[1]=='--extract' else validate_syntax(Path(sys.argv[2]))))
    else:ThreadingHTTPServer(('0.0.0.0',8080),Handler).serve_forever()
