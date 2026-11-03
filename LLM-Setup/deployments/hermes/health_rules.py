"""Deterministic findings from bounded observations; no network or model calls."""
import datetime,math

POLICY={'snapshot_max_age_seconds':600,'backup_metadata_max_age_seconds':600,
        'disk_warning_percent':80,'disk_critical_percent':90,
        'memory_warning_available_percent':10,'memory_critical_available_percent':5,
        'backup_max_age_hours':36}

def age_seconds(value,now):
    try:
        stamp=datetime.datetime.fromisoformat(value)
        if stamp.tzinfo is None:return None
        age=(now-stamp).total_seconds()
        return age if math.isfinite(age) else None
    except (ValueError,TypeError):return None

def assess(packet,now=None):
    now=now or datetime.datetime.now(datetime.timezone.utc)
    alerts=[];setup=[]
    def add(code,target,severity,message,action):
        alerts.append({'id':code+':'+target,'severity':severity,'target':target,'message':message,'next_step':action})
    for gpu in packet.get('gpu_api',[]):
        name=gpu['system']
        if gpu.get('status')!='reachable':add('gpu_api',name,'critical','Inference API is unavailable.','Check API service, credentials and the HQ-to-compute connection.')
        elif gpu.get('acceleration')=='cpu_only':add('gpu_cpu',name,'critical','A loaded model reports no GPU memory residency.','Inspect GPU/container initialization before requesting inference.')
    age=packet.get('snapshot_age_seconds')
    fresh=isinstance(age,(int,float)) and 0<=age<=POLICY['snapshot_max_age_seconds'] and packet.get('snapshot_status')=='fresh'
    if not fresh:add('host_snapshot','collector','warning','Host measurements are stale or unavailable.','Check paperclip-observations and hq-hermes-evidence services.')
    for name,row in packet.get('host_telemetry',{}).items():
        if row.get('status')!='observed':add('host_telemetry',name,'warning','Basic host telemetry is unavailable.','Check the enrolled observer login and trusted SSH host key. API reachability is separate.')
    if fresh:
        for name,host in packet.get('hosts',{}).items():
            disk=host.get('root_disk') or {};used=disk.get('used_percent')
            if isinstance(used,(int,float)) and 0<=used<=100 and used>=POLICY['disk_warning_percent']:
                severity='critical' if used>=POLICY['disk_critical_percent'] else 'warning'
                add('root_disk',name,severity,f'Root disk is {used:.1f}% used.','Inspect disk usage and backup growth; do not delete archives without a retention decision.')
            mem=host.get('memory') or {};total=mem.get('MemTotal_bytes');available=mem.get('MemAvailable_bytes')
            if isinstance(total,(int,float)) and total>0 and isinstance(available,(int,float)) and 0<=available<=total:
                percent=available/total*100
                if percent<POLICY['memory_warning_available_percent']:
                    severity='critical' if percent<POLICY['memory_critical_available_percent'] else 'warning'
                    add('memory',name,severity,f'Available RAM is {percent:.1f}%.','Inspect workload memory use; this sample alone does not establish a persistent shortage.')
    backups=packet.get('backups',{});age=age_seconds(backups.get('checked_at_utc'),now)
    if age is None or not 0<=age<=POLICY['backup_metadata_max_age_seconds']:
        add('backup_metadata','collector','warning','Backup metadata is stale or unavailable.','Check hq-backup-observations.service on HQ.')
    else:
        for row in backups.get('systems',[]):
            name=row['system']
            if row.get('status')!='file_present':
                add('backup_missing',name,'warning','No readable backup file was observed.','Inspect backup creation and metadata-export permissions.')
                continue
            backup_age=age_seconds(row.get('latest_modified_utc'),now)
            if backup_age is None or backup_age<0:
                add('backup_timestamp',name,'warning','Backup timestamp is missing or in the future.','Check clock synchronization and backup metadata.')
            elif backup_age>POLICY['backup_max_age_hours']*3600:
                add('backup_stale',name,'warning',f'Latest backup is {backup_age/3600:.1f} hours old.','Create a fresh backup in an approved maintenance window; check the schedule.')
            if row.get('database_restore')=='failed':add('backup_restore',name,'critical','Database restore validation failed.','Keep the backup and inspect its validation receipt; do not use it for production recovery yet.')
    if any(r.get('off_host_copy')=='not_configured' for r in backups.get('systems',[])):
        setup.append({'id':'off_host_backup','message':'Encrypted off-host backup destination is not configured.'})
    if any(r.get('application_restore')=='not_tested' for r in backups.get('systems',[])):
        setup.append({'id':'application_recovery','message':'A complete isolated application recovery drill remains untested.'})
    alerts.sort(key=lambda a:({'critical':0,'warning':1}[a['severity']],a['id']))
    return {'evaluated_at':now.isoformat(),'result':'attention_required' if alerts else 'no_active_observation_alerts',
            'alerts':alerts,'setup_items':setup,'policy':POLICY,
            'scope':'Basic telemetry and backup evidence only. No alerts does not certify complete hardware or application health.'}
