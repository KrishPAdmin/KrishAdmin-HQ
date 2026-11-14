"""Owner-only Discord DMs, independent of the shared channel allowlist."""
import json
from pathlib import Path

def owner():
    try:
        value=json.loads(Path('/profile/discord-enrollment.json').read_text())['owner_id']
        return value if isinstance(value,str) and value.isdecimal() else None
    except (OSError,ValueError,KeyError):return None

def dm_allowed(user_id):
    expected=owner()
    return expected is not None and str(user_id)==expected

def install():
    from gateway.run import GatewayRunner
    original=GatewayRunner._is_user_authorized
    if getattr(original,'_hq_owner_dm',False):return
    def authorized(self,source,**kwargs):
        platform=getattr(source.platform,'value',source.platform)
        if platform=='discord' and source.chat_type=='dm' and not dm_allowed(source.user_id):return False
        return original(self,source,**kwargs)
    authorized._hq_owner_dm=True
    GatewayRunner._is_user_authorized=authorized

def patch_adapter(cls):
    original=cls._discord_message_admission
    if getattr(original,'_hq_owner_dm',False):return
    def admission(self,message,**kwargs):
        if getattr(message,'guild',None) is None and not dm_allowed(getattr(message.author,'id',None)):return False,False
        return original(self,message,**kwargs)
    admission._hq_owner_dm=True
    cls._discord_message_admission=admission
    evaluate=cls._evaluate_slash_authorization
    def slash(self,interaction):
        if getattr(interaction,'guild',None) is None and not dm_allowed(getattr(getattr(interaction,'user',None),'id',None)):return False,'unauthorized'
        return evaluate(self,interaction)
    cls._evaluate_slash_authorization=slash
