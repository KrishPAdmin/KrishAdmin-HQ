"""Public web search and source collection on HQ; never on a compute host."""
import os,datetime,hashlib,html,http.client,ipaddress,json,re,socket,ssl,time,xml.etree.ElementTree as ET
from urllib.parse import urlsplit,urlunsplit,urljoin,quote,parse_qs
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
            conn.request('GET',urlunsplit(('','',p.path or '/',p.query,'')),headers={'User-Agent':'KrishAdmin-HQ-Research/1.0','Accept':'text/html,application/rss+xml,application/xml,application/json,text/plain,*/*;q=0.5','Accept-Encoding':'identity'})
            r=conn.getresponse()
            if r.status in (301,302,303,307,308):
                if step==redirects:raise ValueError('Too many redirects')
                location=r.getheader('Location')
                if not location:raise ValueError('Invalid redirect')
                url=urljoin(url,location);continue
            if r.status!=200:raise ValueError('HTTP '+str(r.status))
            content_type=r.getheader('Content-Type','')
            if not any(t in content_type for t in ('text/','application/rss+xml','application/xml','application/json','application/javascript','application/x-javascript')):raise ValueError('Unsupported document format')
            raw=r.read(limit+1)
            return {'url':url,'raw':raw[:limit],'content_type':content_type,'response_headers':{k:r.getheader(k) for k in ('access-control-allow-origin','content-language') if r.getheader(k)},'download_truncated':len(raw)>limit,'fetched_at':now()}
        finally:conn.close()

def clean(raw):
    text=raw.decode('utf-8',errors='replace');text=re.sub(r'<(script|style)\b[^>]*>.*?(?:</\1>|$)',' ',text,flags=re.S|re.I)
    main=re.search(r'<main\b[^>]*>(.*?)</main>',text,flags=re.S|re.I)
    if main:text=main.group(1)
    text=re.sub(r'<(nav|header|footer)\b[^>]*>.*?</\1>',' ',text,flags=re.S|re.I)
    return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]*>',' ',text))).strip()

def structured_text(raw,url):
    """Read semantic page data without executing scripts or mixing related entities."""
    text=raw.decode('utf-8',errors='replace');host=(urlsplit(url).hostname or '').lower();parts=[]
    if host in ('youtube.com','www.youtube.com','m.youtube.com') and re.match(r'^/(?:@[^/]+|channel/[^/]+)(?:/|$)',urlsplit(url).path):
        for match in re.finditer(r'(?:var\s+)?ytInitialData\s*=\s*',text):
            try:data,_=json.JSONDecoder().raw_decode(text[match.end():])
            except ValueError:continue
            meta=data.get('metadata',{}).get('channelMetadataRenderer',{})
            # Only this page's header. Recommended/featured channels have different counts.
            header=data.get('header',{});strings=[]
            def walk(value,depth=0):
                if depth>18:return
                if isinstance(value,dict):
                    for k,v in value.items():
                        if k in ('content','simpleText','accessibilityLabel') and isinstance(v,str) and len(v)<200:strings.append(v)
                        elif isinstance(v,(dict,list)):walk(v,depth+1)
                elif isinstance(value,list):
                    for v in value[:100]:walk(v,depth+1)
            walk(header)
            counts=list(dict.fromkeys(s for s in strings if re.search(r'\d.*subscribers?\b',s,re.I)))
            title=meta.get('title');channel_id=meta.get('externalId')
            if title:
                parts.append('YouTube PRIMARY CHANNEL HEADER: '+json.dumps({'channel_name':title,'channel_id':channel_id,'subscriber_count_display':counts,'header_text':list(dict.fromkeys(s for s in strings if s.startswith('@') or re.search(r'\d.*videos?\b',s,re.I)))},ensure_ascii=False))
                parts.append('Public YouTube subscriber counts are rounded/abbreviated. Report the displayed number as approximate, with the fetch timestamp; do not invent an exact private count.')
            break
    class Semantic(HTMLParser):
        def __init__(self):super().__init__();self.ld=False;self.data=[];self.blocks=[];self.meta=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='script' and a.get('type','').lower()=='application/ld+json':self.ld=True;self.data=[]
            if tag=='meta' and (a.get('property') or a.get('name')) in ('og:title','og:description','description','article:published_time','article:modified_time'):self.meta.append((a.get('property') or a.get('name'))+': '+a.get('content','')[:1200])
        def handle_data(self,data):
            if self.ld:self.data.append(data)
        def handle_endtag(self,tag):
            if tag=='script' and self.ld:self.blocks.append(''.join(self.data));self.ld=False
    parser=Semantic();parser.feed(text);parts.extend(parser.meta[:8])
    allowed={'@type','name','headline','description','datePublished','dateModified','price','priceCurrency','availability','ratingValue','ratingCount','reviewCount','userInteractionCount','interactionType','subscriberCount','numberOfItems','value','unitText','author','publisher','url'}
    def semantic(value,depth=0):
        if depth>10:return []
        result=[]
        if isinstance(value,dict):
            for k,v in value.items():
                if k in allowed and isinstance(v,(str,int,float,bool)):result.append(k+': '+str(v)[:1500])
                elif isinstance(v,(dict,list)):result.extend(semantic(v,depth+1))
        elif isinstance(value,list):
            for v in value[:30]:result.extend(semantic(v,depth+1))
        return result[:100]
    for block in parser.blocks[:8]:
        try:parts.append('Structured page metadata (may describe multiple entities): '+'; '.join(semantic(json.loads(block))))
        except (ValueError,RecursionError):pass
    return '\n'.join(parts)[:18000]

def document(url,render=False):
    host=(urlsplit(url).hostname or '').lower()
    limit=8*1024*1024 if host in ('youtube.com','www.youtube.com','m.youtube.com') else 2*1024*1024
    page=fetch(url,limit=limit);semantic=structured_text(page['raw'],page['url'])
    text=semantic+'\n'+clean(page['raw']) if semantic else clean(page['raw'])
    page['extraction']='HTML + semantic metadata'
    if render and not os.environ.get('HQ_RENDER_URL'):page['render_error']='Browser renderer is not configured'
    if (render or len(text.strip())<120 or len(text.strip())<500 and b'<script' in page['raw'].lower()) and os.environ.get('HQ_RENDER_URL'):
        try:
            import urllib.request
            req=urllib.request.Request(os.environ['HQ_RENDER_URL'],data=json.dumps({'url':page['url']}).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=55) as response:rendered=json.load(response)
            if rendered.get('text'):
                text=semantic+'\n'+rendered['text'];page['extraction']='browser DOM + semantic metadata';page['render']=rendered
        except Exception as error:page['render_error']=type(error).__name__
    page['text']=text;return page

def focused_query(query):
    """Remove common task-writing instructions, preserving the research subject."""
    result=re.sub(r'^(?:please\s+)?(?:research|look up|search for|find information on)\s+(?:the\s+)?','',query.strip(),flags=re.I)
    result=re.split(r'\b(?:using|from|with)\s+(?:current\s+)?(?:official|primary|reliable)\s+sources\b',result,flags=re.I)[0]
    result=re.split(r'\b(?:cite|include)\s+(?:the\s+)?(?:technical\s+)?(?:specification\s+page|sources?|citations?)\b',result,flags=re.I)[0]
    result=result.strip(' .,:;')
    if 'official' in query.lower() and 'official' not in result.lower():result+=' official'
    return result or query

def search_web(query):
    """Search on HQ with independent providers; snippets are discovery, not evidence."""
    if not isinstance(query,str) or not 1<=len(query)<=400:raise ValueError('Search query must be 1–400 characters')
    query=focused_query(query);results=[];attempts=[]
    class SearchLinks(HTMLParser):
        def __init__(self):super().__init__();self.url=None;self.title=[];self.rows=[]
        def handle_starttag(self,tag,attrs):
            a=dict(attrs)
            if tag=='a' and 'result__a' in a.get('class',''):
                u=urljoin('https://html.duckduckgo.com',a.get('href',''))
                self.url=parse_qs(urlsplit(u).query).get('uddg',[u])[0];self.title=[]
        def handle_data(self,data):
            if self.url:self.title.append(data)
        def handle_endtag(self,tag):
            if tag=='a' and self.url:
                self.rows.append({'url':self.url,'title':''.join(self.title)[:180]});self.url=None
    # Query both providers: a successful but irrelevant RSS response is not a useful fallback.
    for provider,url in [('DuckDuckGo','https://html.duckduckgo.com/html/?q='+quote(query)),('Bing RSS','https://www.bing.com/search?format=rss&q='+quote(query))]:
        try:
            page=fetch(url,limit=150000)
            if provider=='Bing RSS':
                root=ET.fromstring(page['raw']);rows=[{'url':x.findtext('link',''),'title':html.unescape(x.findtext('title',''))[:180]} for x in root.findall('./channel/item')[:8]]
            else:
                parser=SearchLinks();parser.feed(page['raw'].decode('utf-8',errors='replace'));rows=parser.rows[:8]
            rows=[r for r in rows if r['url'].startswith('https://')]
            attempts.append({'provider':provider,'status':'results_found' if rows else 'no_results','fetched_at':page['fetched_at']})
            for row in rows:
                if row['url'] not in {r['url'] for r in results}:results.append({**row,'provider':provider})
        except Exception as error:attempts.append({'provider':provider,'status':'failed','error_type':type(error).__name__})
    terms=set(re.findall(r'[a-z0-9]{3,}',query.lower()))-{'the','and','for','official','current','research','documentation','specifications','specs','using','latest','what','are','how'}
    def relevance(row):return sum(t in (row['title']+' '+row['url']).lower() for t in terms)
    if terms and (not results or max(map(relevance,results))<max(1,len(terms)*.65)):
        # RSS sometimes overweights the first word. Put a distinctive subject first,
        # preserving the full original question in metadata and later analysis.
        words=query.split()
        refined=' '.join(words[1:]+words[:1]) if len(words)>1 else query
        try:
            page=fetch('https://www.bing.com/search?format=rss&q='+quote(refined),limit=150000)
            root=ET.fromstring(page['raw']);rows=[{'url':x.findtext('link',''),'title':html.unescape(x.findtext('title',''))[:180],'provider':'Bing RSS refined'} for x in root.findall('./channel/item')[:8]]
            rows=[r for r in rows if r['url'].startswith('https://')]
            attempts.append({'provider':'Bing RSS refined','query':refined,'status':'results_found' if rows else 'no_results','fetched_at':page['fetched_at']})
            for row in rows:
                if row['url'] not in {r['url'] for r in results}:results.append(row)
        except Exception as error:attempts.append({'provider':'Bing RSS refined','status':'failed','error_type':type(error).__name__})
    results.sort(key=relevance,reverse=True)
    return {'query':query,'provider':'DuckDuckGo + Bing RSS','status':'results_found' if results else 'failed' if all(a['status']=='failed' for a in attempts) else 'no_results',
            'relevance_warning':bool(terms and results and max(map(relevance,results))<max(1,len(terms)*.65)),
            'attempts':attempts,'results':results[:10],'collector':'HQ','limitations':'Search listings are untrusted discovery links. Read sources before making factual claims.'}

def read_page(url,offset=0,limit=4000,find=None,render=False):
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=8000:raise ValueError('Use offset >= 0 and limit 1–8000')
    page=document(url,render=render);text=page['text']
    if find is not None:
        if not isinstance(find,str) or not 1<=len(find)<=120:raise ValueError('find must be 1–120 characters')
        position=text.lower().find(find.lower(),offset)
        if position<0:return {'url':page['url'],'status':'text_not_found','download_truncated':page['download_truncated'],'collector':'HQ'}
        offset=position
    chunk=text[offset:offset+limit]
    if not text:raise ValueError('No readable text after available extraction; authenticated, challenged or image pages may be unavailable')
    return {'url':page['url'],'fetched_at':page['fetched_at'],'body_sha256':hashlib.sha256(page['raw']).hexdigest(),
            'text':chunk,'offset':offset,'next_offset':offset+len(chunk) if offset+len(chunk)<len(text) else None,
            'download_truncated':page['download_truncated'],'extraction':page['extraction'],'render_error':page.get('render_error'),
            'browser_receipt':{k:v for k,v in page.get('render',{}).items() if k!='text'},'collector':'HQ','untrusted_source':True}

def weather(location,country_code=None):
    """Current modeled conditions and three-day forecast, collected only on HQ."""
    if not isinstance(location,str) or not 1<=len(location)<=100:raise ValueError('Supply a city name up to 100 characters')
    if country_code is not None and (not isinstance(country_code,str) or not re.fullmatch('[A-Za-z]{2}',country_code)):raise ValueError('country_code must be a two-letter country code')
    geo_url='https://geocoding-api.open-meteo.com/v1/search?name='+quote(location)+'&count=5&language=en&format=json'
    if country_code:geo_url+='&countryCode='+country_code.upper()
    page=fetch(geo_url,limit=60000);places=json.loads(page['raw']).get('results',[])
    if not places:return {'status':'location_not_found','location_query':location,'collector':'HQ'}
    place=places[0]
    url='https://api.open-meteo.com/v1/forecast?latitude='+str(float(place['latitude']))+'&longitude='+str(float(place['longitude']))+'&current=temperature_2m,apparent_temperature,relative_humidity_2m,precipitation,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max&forecast_days=3&timezone=auto'
    page=fetch(url,limit=60000);data=json.loads(page['raw'])
    return {'status':'collected','collector':'HQ','fetched_at':page['fetched_at'],'location':{k:place.get(k) for k in ('name','admin1','country','latitude','longitude')},
            'alternatives':[{k:p.get(k) for k in ('name','admin1','country')} for p in places[1:]],
            **{k:data.get(k) for k in ('timezone','current','current_units','daily','daily_units')},'source_url':url,'attribution':'Weather data by Open-Meteo; modeled current conditions, not a guaranteed local station observation.',
            'body_sha256':hashlib.sha256(page['raw']).hexdigest()}

def collect(query,urls=None):
    if not isinstance(query,str) or not 1<=len(query)<=400:raise ValueError('Search query must be 1–400 characters')
    query=focused_query(query)
    if urls is not None and (not isinstance(urls,list) or not 1<=len(urls)<=3 or any(not isinstance(u,str) for u in urls)):raise ValueError('Supply 1–3 public HTTPS URLs')
    candidates=[];search={'provider':'Bing RSS','query':query,'status':'not_requested'}
    if not urls:
        search=search_web(query);candidates=search['results']
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
        parts=urlsplit(url);path=parts.path.lower();host=(parts.hostname or '').lower()
        primary=host.startswith('docs.') or host.endswith(('.gov','.edu','.gov.uk','.gc.ca')) or any(host==h or host.endswith('.'+h) for h in ('apple.com','python.org','nvidia.com','amd.com','microsoft.com','kernel.org','ollama.com','nousresearch.com','modelcontextprotocol.io','open-meteo.com'))
        return (100 if primary else 0)+sum(10 for term in set(terms) if term in path)+(8 if 'specs' in path or 'technical' in path else 0)
    documents=[];failures=[];queue=[(u,0) for u in (urls or [])];seen=set();attempts=0
    deadline=time.monotonic()+60
    while queue and attempts<10 and time.monotonic()<deadline:
        url,depth=queue.pop(0)
        if url in seen:continue
        seen.add(url);attempts+=1
        try:
            page=document(url);text=page['text']
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
        except Exception as e:failures.append({'url':url,'error_type':type(e).__name__,'reason':str(e)[:160]})
    documents.sort(key=lambda x:x[0],reverse=True);sources=[]
    # Explicitly retain useful semantic channel statistics ahead of navigation pages.
    documents.sort(key=lambda x:('YouTube PRIMARY CHANNEL HEADER:' in x[2] and 'subscriber_count_display": ["' in x[2],x[0]),reverse=True)
    selected=documents[:3]
    for i,(_,page,text) in enumerate(selected):
        budget=6500 if i==0 else 1500
        if 'YouTube PRIMARY CHANNEL HEADER:' in text:
            excerpt=text[:budget]
        elif i==0 and ('specs' in urlsplit(page['url']).path or 'technical' in urlsplit(page['url']).path):
            spans=[text[:1250]]
            for anchor,width in [('Chip ',300),('Camera ',300),('Power and Battery',350),('Cellular and Wireless',200)]:
                found=text.find(anchor)
                if found>=1250:spans.append(text[found:found+width])
            excerpt=' […] '.join(spans).encode()[:budget].decode('utf-8',errors='ignore')
        else:
            # Include relevant passages from deeper in a page, rather than only navigation/intro.
            candidates=[]
            stems={t[:4] if len(t)>5 else t for t in terms}
            for start in range(0,len(text),700):
                window=text[start:start+2100].lower()
                matched=sum(1 for term in stems if re.search(r'\b'+re.escape(term),window))+sum(2 for term in set(terms) if re.search(r'\b'+re.escape(term)+r'\b',window))
                candidates.append((matched,start))
            anchors=[]
            for matched,start in sorted(candidates,key=lambda x:(-x[0],x[1])):
                if matched and all(abs(start-p)>=2100 for p in anchors):anchors.append(start)
                if len(anchors)==3:break
            excerpt=(text[:200]+' […] '+' […] '.join(text[p:p+2100] for p in sorted(anchors))) if anchors else text
            excerpt=excerpt.encode()[:budget].decode('utf-8',errors='ignore')
        excerpt=excerpt.encode()[:budget].decode('utf-8',errors='ignore')
        sources.append({'url':page['url'],'fetched_at':page['fetched_at'],'body_sha256':hashlib.sha256(page['raw']).hexdigest(),'excerpt':excerpt,'extraction':page.get('extraction'),
                        'browser_receipt':{k:v for k,v in page.get('render',{}).items() if k!='text'},'render_error':page.get('render_error'),
                        'truncated':page['download_truncated'] or len(excerpt)<len(text) or page.get('render',{}).get('truncated',False)})
    packet={'collector':'HQ gateway; no requests issued by AMD-GPU','collected_at':now(),'search':search,'sources':sources,'fetch_failures':failures,
            'status':'sources_collected' if sources else 'no_source_evidence','limitations':'Search results can be irrelevant or incomplete. Excerpts are partial. Absence from results is not proof a product does not exist. Distinguish official announcements, rumors and uncertain names; cite fetched URLs.'}
    packet['evidence_sha256']=hashlib.sha256(json.dumps(packet,sort_keys=True).encode()).hexdigest()
    return packet
