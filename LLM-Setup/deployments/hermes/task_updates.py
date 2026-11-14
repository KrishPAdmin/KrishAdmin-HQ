"""Durable task subscriptions and deterministic, bounded Discord result messages."""
import hashlib,json,re,time

TERMINAL={'in_review','done','blocked','cancelled','canceled'}

def issue_url(identifier):
    if not re.fullmatch(r'KRI-\d+',identifier):raise ValueError('Invalid task identifier')
    return 'https://paperclip.example.invalid/KRI/issues/'+identifier

def reply_footer(messages,content):
    """Use successful, correlated task tool results from this turn only."""
    start=next((i for i in range(len(messages)-1,-1,-1) if messages[i].get('role')=='user'),len(messages))
    calls=set();tasks=[]
    for message in messages[start+1:]:
        if message.get('role')=='assistant':
            calls.update(c['id'] for c in message.get('tool_calls',[]) if c.get('id') and c.get('function',{}).get('name')=='hq_task')
        if message.get('role')!='tool' or message.get('tool_call_id') not in calls:continue
        try:
            result=json.loads(message['content'])
            if not isinstance(result,dict) or result.get('error'):continue
            task=result.get('task','');url=issue_url(task)
            if result.get('url')!=url:continue
        except (ValueError,TypeError,KeyError):continue
        if task not in tasks:tasks.append(task)
    if not tasks:return content
    footer='\n'.join('Paperclip report '+task+': '+issue_url(task) for task in tasks)
    return content.rstrip()+'\n\n'+footer

def clip_units(text,limit):
    """Conservative UTF-16 budget also handles astral emoji."""
    return text.encode('utf-16-le')[:max(0,limit)*2].decode('utf-16-le',errors='ignore')

def schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS task_watches (
        issue_id TEXT NOT NULL, channel_id TEXT NOT NULL, user_id TEXT NOT NULL,
        source_message_id TEXT, message_id TEXT, delivered_hash TEXT,
        pending TEXT, attempted_at REAL, next_poll REAL NOT NULL DEFAULT 0,
        failures INTEGER NOT NULL DEFAULT 0, last_error TEXT, closed INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY(issue_id,channel_id,user_id))''')

def origin_checked(origin,policy):
    if origin is None:return None
    if not isinstance(origin,dict):raise ValueError('Invalid notification origin')
    allowed={str(x) for x in policy.get('allowed_users',[])}|{str(policy['owner_id'])}
    if origin.get('platform')!='discord' or origin.get('user_id') not in allowed:
        raise PermissionError('Notification requester is not allowed')
    channel=policy['channel_id']
    dm=policy.get('maintenance_dm') or {}
    if (dm.get('owner_id')==policy['owner_id'] and origin.get('user_id')==policy['owner_id']
            and origin.get('chat_id')==dm.get('channel_id') and not origin.get('scope_id')):
        channel=dm['channel_id']
    if origin.get('chat_id')!=channel and origin.get('parent_chat_id')!=channel:
        raise PermissionError('Notification channel is not allowed')
    if origin.get('scope_id') and origin['scope_id']!=policy['guild_id']:
        raise PermissionError('Notification server is not allowed')
    message=origin.get('message_id') if origin.get('chat_id')==channel else None
    if message and not re.fullmatch(r'\d{15,22}',message):raise ValueError('Invalid source message')
    # Preserve the verified owner DM; shared-channel threads use the enrolled channel.
    return {'channel_id':channel,'user_id':origin['user_id'],'source_message_id':message}

def subscribe(db,issue_id,origin):
    if not origin:return False
    schema(db)
    db.execute('INSERT OR IGNORE INTO task_watches(issue_id,channel_id,user_id,source_message_id) VALUES (?,?,?,?)',
               (issue_id,origin['channel_id'],origin['user_id'],origin.get('source_message_id')))
    return True

def fingerprint(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()

def clean(text,secrets=()):
    text=str(text)
    for secret in secrets:
        if len(secret)>=8:text=text.replace(secret,'[redacted]')
    text=re.sub(r'(?i)\b(token|password|secret|authorization|api[_ -]?key)\s*[:=]\s*\S+',r'\1: [redacted]',text)
    text=re.sub(r'(?s)-----BEGIN .*?PRIVATE KEY-----.*?-----END .*?PRIVATE KEY-----','[redacted private key]',text)
    text=re.sub(r'[\x00-\x08\x0b-\x1f]','',text)
    return text.replace('@','＠').replace('```','').replace('/KRI/issue/','/KRI/issues/')

def render(result,user_id,marker,secrets=()):
    status=result['status']
    headings={'in_review':'Execution completed — awaiting review','done':'Task marked done',
              'blocked':'Could not complete — blocked','cancelled':'Task cancelled','canceled':'Task cancelled'}
    if status not in TERMINAL:raise ValueError('Not a reportable state')
    lines=[f'<@{user_id}> **{result["task"]}: {headings[status]}**']
    evidence=result.get('result_evidence') or {}
    analysis=evidence.get('analysis') or {};packet=evidence.get('evidence') or {}
    assessment=packet.get('assessment') or {}
    if status in ('blocked','cancelled','canceled'):
        lines.append('Outcome: no successful completion confirmed.')
    elif assessment.get('result')=='no_active_observation_alerts':
        lines.append('Observed checks: no active alerts. This is partial telemetry, not a complete health certification.')
    elif assessment.get('alerts'):
        lines.append('Observed checks: findings need attention.')
        lines.extend('- '+clean(a.get('message',a.get('id','Finding')),secrets)[:180] for a in assessment['alerts'][:3])
    else:
        lines.append('Outcome: review the agent’s findings; task status alone does not establish a pass.')
    if analysis.get('backend') and analysis.get('model'):
        lines.append('Execution receipt: **'+clean(analysis['backend'],secrets).upper()+'**, `'+clean(analysis['model'],secrets)+'`'+
                     (' — '+str(analysis['seconds'])+' seconds.' if isinstance(analysis.get('seconds'),(int,float)) else '.'))
        if packet.get('gpu_api'):
            lines.append('GPU snapshot was collected before this analysis; an idle snapshot does not mean the inference above was unused.')
    elif result.get('agent_comment'):
        lines.append('Agent report (excerpt):\n'+clean(result['agent_comment'],secrets)[:650])
    if packet.get('collected_at'):lines.append('Evidence collected: '+clean(packet['collected_at'],secrets))
    footer='-# Task update reference: '+marker+'\n\nPaperclip report: '+issue_url(result['task'])
    # Reserve the entire footer before trimming the preview, including recovery marker.
    budget=1950-len(footer.encode('utf-16-le'))//2-2
    content='\n\n'.join(lines)
    if len(content.encode('utf-16-le'))//2>budget:content=clip_units(content,budget-1)+'…'
    return {'content':content+'\n\n'+footer,'allowed_mentions':{'parse':[],'users':[user_id],'replied_user':False},'flags':4}
