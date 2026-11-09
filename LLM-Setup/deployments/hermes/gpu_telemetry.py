"""Bounded GPU telemetry; never infer utilization from model residency or opaque counters."""
import csv,datetime,json,math,re,threading,time
from concurrent.futures import ThreadPoolExecutor

def number(value):
    match=re.fullmatch(r'\s*(-?\d+(?:\.\d+)?)\s*(?:%|W|MiB)?\s*',str(value))
    if not match:return None
    result=float(match[1]);return result if math.isfinite(result) and result>=0 else None

def percentage(value):
    value=number(value);return value if value is not None and value<=100 else None

def parse(target,result):
    rows=[];checks=result.get('checks',{})
    if target=='nvidia-gpu' and checks.get('nvidia',{}).get('status')=='observed':
        for values in csv.reader(checks['nvidia'].get('output','').splitlines()):
            if len(values)<9:continue
            used,total=number(values[6]),number(values[7])
            rows.append({'id':'nvidia-gpu:'+values[0].strip(),'system':target,'card':values[0].strip(),'name':values[1].strip(),
                         'temperature_c':number(values[4]),'utilization_percent':percentage(values[5]),
                         'memory_used_bytes':used*1048576 if used is not None else None,'memory_total_bytes':total*1048576 if total is not None else None,
                         'power_watts':number(values[8]),'power_source':'nvidia-smi power.draw','power_limit_watts':None})
    if target=='amd-gpu':
        try:cards=json.loads(checks.get('amd',{}).get('output','{}'))
        except (ValueError,TypeError):cards={}
        sensors={r['card']:r for r in checks.get('amd_sensors',{}).get('cards',[]) if re.fullmatch(r'card\d+',r.get('card',''))}
        by_bus={r.get('pci_bus_id','').lower():r for r in sensors.values() if r.get('pci_bus_id')}
        actual_cards={card:value for card,value in cards.items() if re.fullmatch(r'card\d+',card)}
        for card in sorted(actual_cards or sensors):
            if not re.fullmatch(r'card\d+',card):continue
            values=cards.get(card,{})
            # ROCm indices and DRM card numbers differ on multi-adapter hosts.
            # Join by the actual PCI bus identity; never guess from card numbering.
            sensor=by_bus.get(str(values.get('PCI Bus','')).lower(),{}) if actual_cards else sensors.get(card,{})
            utilization=percentage(values.get('GPU use (%)'))
            if utilization is None:utilization=percentage(sensor.get('utilization_percent'))
            rows.append({'id':'amd-gpu:'+card,'system':target,'card':card,'drm_card':sensor.get('card'),'pci_bus_id':sensor.get('pci_bus_id'),'name':values.get('Card Series','AMD GPU'),
                         'temperature_c':number(values.get('Temperature (Sensor edge) (C)')),
                         'junction_temperature_c':number(values.get('Temperature (Sensor junction) (C)')),
                         'memory_temperature_c':number(values.get('Temperature (Sensor memory) (C)')),
                         'utilization_percent':utilization,'memory_used_bytes':number(sensor.get('memory_used_bytes')),
                         'memory_total_bytes':number(sensor.get('memory_total_bytes')),'power_watts':number(sensor.get('power_watts')),
                         'power_limit_watts':number(sensor.get('power_limit_watts')),'power_source':sensor.get('power_source')})
    if not rows:
        rows=[{'id':target+':'+card,'system':target,'card':card,'name':target.upper()+' GPU','status':'unavailable'} for card in (['0'] if target=='nvidia-gpu' else ['card0','card1'])]
    for row in rows:
        used,total=row.get('memory_used_bytes'),row.get('memory_total_bytes')
        row['memory_percent']=round(100*used/total,2) if used is not None and total and 0<=used<=total else None
        metrics=('utilization_percent','memory_used_bytes','memory_total_bytes','power_watts','temperature_c')
        row['status']='observed' if all(row.get(k) is not None for k in metrics) else 'partial' if any(row.get(k) is not None for k in metrics) else 'unavailable'
        row['sensor_time']=result.get('checked_at_utc')
    return rows

class LiveGPU:
    def __init__(self,collector):
        self.collector=collector;self.lock=threading.Lock();self.running=False;self.updated=0;self.value=None
    def _collect(self):
        def sample(target):
            try:return parse(target,self.collector(target))
            except Exception:return parse(target,{})
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:rows=sum(pool.map(sample,('nvidia-gpu','amd-gpu')),[])
            stamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self.lock:
                self.value={'sampled_at':stamp,'cards':rows,'status':'observed' if all(r['status']=='observed' for r in rows) else 'partial',
                            'source':'Fixed read-only SSH probes; no model inference','poll_seconds':5,'stale_after_seconds':30}
                self.updated=time.monotonic()
        finally:
            with self.lock:self.running=False
    def get(self):
        with self.lock:
            age=time.monotonic()-self.updated
            if age>=5 and not self.running:
                self.running=True;threading.Thread(target=self._collect,daemon=True).start()
            result=dict(self.value or {'sampled_at':None,'cards':[],'status':'collecting','poll_seconds':5,'stale_after_seconds':30})
            result.update(age_seconds=round(age,1) if self.value else None,refreshing=self.running)
            if self.value and age>30:result['status']='stale'
            return result
