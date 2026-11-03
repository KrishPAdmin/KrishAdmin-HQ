"""Idempotent homelab workflow configuration; uses existing local agents only."""
import json
from admin_api import Admin, ROOT

a = Admin().login()
state = json.loads((ROOT / 'instance.json').read_text()); cid = state['company_id']
agents = a.api('GET', f'/api/companies/{cid}/agents')
coordinator = next(x for x in agents if x['name'] == 'Local Coordinator')
targets = json.loads((ROOT / 'agents/targets.json').read_text())
department_path = ROOT / 'agents/department.json'
cfg = json.loads(department_path.read_text()) if department_path.exists() else {}
cfg['coordinator'] = coordinator['id']
cfg.setdefault('targets', {}).update(targets)
department_path.write_text(json.dumps(cfg, indent=2) + '\n')
settings = coordinator['adapterConfig']; settings.setdefault('env', {})['HQ_DEPARTMENT'] = '1'
a.api('PATCH', f'/api/agents/{coordinator["id"]}', {'adapterConfig': settings,
 'capabilities': 'Plans up to four local specialist steps, shares dependency evidence and synthesizes their results. Assign tasks here to coordinate AMD-GPU, NVIDIA-GPU and Pi. Final deliverables require human review.'})
a.api('PATCH', f'/api/companies/{cid}', {'requireBoardApprovalForNewAgents': True})
a.api('PATCH', '/api/instance/settings/experimental', {'enableCases': True, 'enableDecisions': True})
projects = a.api('GET', f'/api/companies/{cid}/projects'); project = next(x for x in projects if x['name'] == 'Cluster Operations')
routines = a.api('GET', f'/api/companies/{cid}/routines')
result = {}
for name, cron, description in [
 ('Daily GPU health report', '0 10 * * *', '[HQ routine: gpu-health]\nCollect current health with Pi: run python3 /opt/worker/cluster_health.py > cluster-health.json, then write report.md from that JSON. Publish both files. AMD-GPU then reviews the collected evidence and flags failures or missing coverage. Coordinator returns a final report for operator review. This checks only the two configured GPU APIs, not NAS/storage/Proxmox health. No remote changes.'),
 ('Daily team digest', '0 17 * * *', '[HQ routine: daily-standup]\nCollect an activity brief from each existing specialist using live Paperclip task records for the last 24 hours, then aggregate the briefs and current board blockers. This bounded local adaptation does not run a second Q&A round. Automatically finish this observational digest.')]:
 assignee = coordinator['id']
 if name == 'Daily GPU health report' and state.get('operations_agents', {}).get('health'):
  assignee = state['operations_agents']['health']
  description = 'Deterministic GPU API and host observations. Publish JSON and report. Missing or stale telemetry is unknown; no model generation or remote changes.'
 payload = {'title': name, 'description': description, 'assigneeAgentId': assignee, 'projectId': project['id'],
            'concurrencyPolicy': 'skip_if_active', 'catchUpPolicy': 'skip_missed', 'status': 'active'}
 routine = next((r for r in routines if r['title'] == name), None)
 routine = a.api('PATCH', f'/api/routines/{routine["id"]}', payload) if routine else a.api('POST', f'/api/companies/{cid}/routines', payload)
 detail = a.api('GET', f'/api/routines/{routine["id"]}')
 if not detail.get('triggers'):
  a.api('POST', f'/api/routines/{routine["id"]}/triggers', {'kind': 'schedule', 'cronExpression': cron, 'timezone': 'America/New_York'})
 result[name] = routine['id']
for agent in agents:
 if agent['status'] == 'error':
  a.api('POST', f'/api/agents/{agent["id"]}/clear-error', {})
(ROOT / 'validation/networkchuck-upgrade/routines.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
