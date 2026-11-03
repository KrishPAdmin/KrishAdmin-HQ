"""Runtime policy shared with the native Control Center. No model-editable inputs."""
import json,os
from pathlib import Path
ROOT=Path('/paperclip/hq-control')

def policy(company_id):
    try:
        data=json.loads((ROOT/(str(company_id)+'.json')).read_text())
        if data.get('companyId')!=company_id:raise ValueError('Company mismatch')
        return data
    except (OSError,ValueError,TypeError):
        return {'externalAI':'disabled','autoEscalate':False,'maxSteps':4,'agents':{}}

def agent_settings(company_id,agent_id):
    return policy(company_id).get('agents',{}).get(agent_id,{})
