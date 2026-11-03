"""Human-readable status from structured fields, without model-generated claims."""
def markdown(packet):
    lines=['# Homelab observation report','',f"Collected: {packet.get('collected_at','unknown')}",'',
           '## GPU APIs','','| System | API | Acceleration evidence |','|---|---|---|']
    for row in packet.get('gpu_api',[]):lines.append(f"| {row['system']} | {row['status']} | {row.get('acceleration','unknown')} |")
    lines+=['','## Basic host telemetry','',f"Snapshot: {packet.get('snapshot_status','unknown')}; age: {packet.get('snapshot_age_seconds','unknown')} seconds.",'',
            '| Host | Telemetry | Root disk used | RAM available |','|---|---|---|---|']
    for name,row in packet.get('host_telemetry',{}).items():
        host=packet.get('hosts',{}).get(name,{});disk=host.get('root_disk') or {};mem=host.get('memory') or {}
        ram=f"{mem.get('MemAvailable_bytes',0)/mem['MemTotal_bytes']*100:.1f}%" if mem.get('MemTotal_bytes') else 'unknown'
        used=str(disk['used_percent'])+'%' if 'used_percent' in disk else 'unknown'
        lines.append(f"| {name} | {row['status']} | {used} | {ram} |")
    lines+=['','## Backups','','| Source | File | Freshness at metadata check | Database restore | Application recovery |',
            '|---|---|---|---|---|']
    for row in packet.get('backups',{}).get('systems',[]):
        lines.append('| '+' | '.join(str(row.get(k,'unknown')) for k in ('system','status','freshness','database_restore','application_restore'))+' |')
    lines+=['',f"Backup metadata: {packet.get('backups',{}).get('metadata_status','unknown')}.",'','## Active observation alerts','']
    assessment=packet.get('assessment',{})
    for alert in assessment.get('alerts',[]):lines.append(f"- **{alert['severity']} / {alert['target']}**: {alert['message']} {alert['next_step']}")
    if not assessment.get('alerts'):lines.append('No active observation alerts within the configured checks.')
    lines+=['','## Setup and recovery gaps','']
    for item in assessment.get('setup_items',[]):lines.append('- '+item['message'])
    if not assessment.get('setup_items'):lines.append('No setup gaps reported by this observation source.')
    lines+=['','Basic observations do not certify complete hardware health. GPU residency does not prove active inference.',
            'Database restore validation does not prove full application recovery.','',f"Evidence SHA-256: `{packet.get('evidence_sha256','unknown')}`",'']
    return '\n'.join(lines)
