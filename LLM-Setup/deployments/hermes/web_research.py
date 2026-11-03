"""Public web search and source collection on HQ; never on a compute host."""
import datetime,hashlib,html,http.client,ipaddress,json,re,socket,ssl,xml.etree.ElementTree as ET
from urllib.parse import urlsplit,urlunsplit,urljoin,quote
from html.parser import HTMLParser

def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def fetch(url,limit=300000,redirects=3):
    for step in range(redirects+1):
        p=urlsplit(url)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.port not in (None,443):raise ValueError('Only public HTTPS pages without credentials are supported')
        addresses=socket.getaddrinfo(p.hostname,443,type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError('Private, loopback and link-local destinations are blocked')
        chosen=addresses[0];host=p.hostname
        class Pinned(http.client.HTTPSConnection):
            def connect(self):
                raw=socket.socket(chosen[0],chosen[1],chosen[2]);raw.settimeout(12)
                try:raw.connect(chosen[4]);self.sock=self._context.wrap_socket(raw,server_hostname=host)
                except BaseException:raw.close();raise
        conn=Pinned(host,timeout=12,context=ssl.create_default_context())
        try:
            conn.request('GET',urlunsplit(('','',p.path or '/',p.query,'')),headers={'User-Agent':'KrishAdmin-HQ-Research/1.0','Accept':'text/html,application/rss+xml,application/xml,text/plain','Accept-Encoding':'identity'})
            r=conn.getresponse()
            if r.status in (301,302,303,307,308):
                if step==redirects:raise ValueError('Too many redirects')
                location=r.getheader('Location')
                if not location:raise ValueError('Invalid redirect')
                url=urljoin(url,location);continue
            if r.status!=200:raise ValueError('HTTP '+str(r.status))
            content_type=r.getheader('Content-Type','')
            if not any(t in content_type for t in ('text/','application/rss+xml','application/xml','application/json')):raise ValueError('Unsupported document format')
            raw=r.read(limit+1)
            return {'url':url,'raw':raw[:limit],'download_truncated':len(raw)>limit,'fetched_at':now()}
        finally:conn.close()

def clean(raw):
    text=raw.decode('utf-8',errors='replace');text=re.sub(r'<(script|style)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
    main=re.search(r'<main\b[^>]*>(.*?)</main>',text,flags=re.S|re.I)
    if main:text=main.group(1)
    text=re.sub(r'<(nav|header|footer)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',text))).strip()

def focused_query(query):
    """Remove common task-writing instructions, preserving the research subject."""
    result=re.sub(r'^(?:please\s+)?(?:research|look up|search for|find information on)\s+(?:the\s+)?','',query.strip(),flags=re.I)
    result=re.split(r'\b(?:using|from|with)\s+(?:current\s+)?(?:official|primary|reliable)\s+sources\b',result,flags=re.I)[0]
    result=re.split(r'\b(?:cite|include)\s+(?:the\s+)?(?:technical\s+)?(?:specification\s+page|sources?|citations?)\b',result,flags=re.I)[0]
    result=result.strip(' .,:;')
    if 'official' in query.lower() and 'official' not in result.lower():result+=' official'
    return result or query

def collect(query,urls=None):
    if not isinstance(query,str) or not 1<=len(query)<=400:raise ValueError('Search query must be 1–400 characters')
    query=focused_query(query)
    if urls is not None and (not isinstance(urls,list) or not 1<=len(urls)<=3 or any(not isinstance(u,str) for u in urls)):raise ValueError('Supply 1–3 public HTTPS URLs')
    candidates=[];search={'provider':'Bing RSS','query':query,'status':'not_requested'}
    if not urls:
        try:
            page=fetch('https://www.bing.com/search?format=rss&q='+quote(query),limit=100000)
            root=ET.fromstring(page['raw'])
            for item in root.findall('./channel/item')[:6]:
                url=item.findtext('link','');title=html.unescape(item.findtext('title',''))
                if url.startswith('https://'):candidates.append({'url':url,'title':title[:180]})
            search.update(status='results_found' if candidates else 'no_results',fetched_at=page['fetched_at'],response_sha256=hashlib.sha256(page['raw']).hexdigest(),results=candidates)
        except Exception as e:search.update(status='failed',error_type=type(e).__name__)
        # Fetch up to three search results, at most two per origin. Never claim snippets are full sources.
        urls=[];counts={}
        for item in candidates:
            host=urlsplit(item['url']).hostname
            if counts.get(host,0)>=2:continue
            urls.append(item['url']);counts[host]=counts.get(host,0)+1
            if len(urls)==3:break
    class Links(HTMLParser):
        def __init__(self):super().__init__();self.links=[]
        def handle_starttag(self,tag,attrs):
            if tag=='a':
                href=dict(attrs).get('href')
                if href:self.links.append(href)
    terms=[t for t in re.findall(r'[a-z0-9]+',query.lower()) if len(t)>2 and t not in {'what','are','the','specifications','specs','research','please','find','current','official','and','for','with'}]
    def score(url):
        path=urlsplit(url).path.lower()
        return sum(10 for term in set(terms) if term in path)+(8 if 'specs' in path or 'technical' in path else 0)
    documents=[];failures=[];queue=[(u,0) for u in (urls or [])];seen=set();attempts=0
    while queue and attempts<6:
        url,depth=queue.pop(0)
        if url in seen:continue
        seen.add(url);attempts+=1
        try:
            page=fetch(url);text=clean(page['raw'])
            if len(text)<80:raise ValueError('Page has insufficient readable text')
            if terms and not any(re.search(r'\b'+re.escape(term)+r'\b',text,re.I) for term in terms):
                raise ValueError('Source does not mention the search subject')
            documents.append((score(page['url']),page,text))
            if depth<2 and terms:
                parser=Links();parser.feed(page['raw'].decode('utf-8',errors='replace'));origin=urlsplit(page['url']).hostname
                links=[]
                for href in parser.links:
                    linked=urljoin(page['url'],href);parts=urlsplit(linked)
                    if parts.hostname!=origin or parts.scheme!='https' or parts.query or parts.fragment:continue
                    if any(x in parts.path.lower() for x in ('/shop','/buy','/cart','/login','/checkout')):continue
                    if linked not in seen and score(linked)>score(page['url']):links.append(linked)
                if links:queue.insert(0,(max(set(links),key=lambda u:(score(u),-len(u))),depth+1))
        except Exception as e:failures.append({'url':url,'error_type':type(e).__name__})
    documents.sort(key=lambda x:x[0],reverse=True);sources=[]
    selected=documents[:2]
    for i,(_,page,text) in enumerate(selected):
        budget=2500 if i==0 else 350
        if i==0 and ('specs' in urlsplit(page['url']).path or 'technical' in urlsplit(page['url']).path):
            spans=[text[:1250]]
            for anchor,width in [('Chip ',300),('Camera ',300),('Power and Battery',350),('Cellular and Wireless',200)]:
                found=text.find(anchor)
                if found>=1250:spans.append(text[found:found+width])
            excerpt=' […] '.join(spans).encode()[:budget].decode('utf-8',errors='ignore')
        else:excerpt=text.encode()[:budget].decode('utf-8',errors='ignore')
        sources.append({'url':page['url'],'fetched_at':page['fetched_at'],'body_sha256':hashlib.sha256(page['raw']).hexdigest(),'excerpt':excerpt,'truncated':page['download_truncated'] or len(excerpt)<len(text)})
    packet={'collector':'HQ gateway; no requests issued by AMD-GPU','collected_at':now(),'search':search,'sources':sources,'fetch_failures':failures,
            'status':'sources_collected' if sources else 'no_source_evidence','limitations':'Search results can be irrelevant or incomplete. Excerpts are partial. Absence from results is not proof a product does not exist. Distinguish official announcements, rumors and uncertain names; cite fetched URLs.'}
    packet['evidence_sha256']=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    return packet
