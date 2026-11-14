"""Add the verified owner's DM to native maintenance notice delivery/retry tracking."""
import copy,json
from pathlib import Path

def dm_config(platform,cfg):
    if getattr(platform,'value',platform)!='discord':return None
    try:
        policy=json.loads(Path('/profile/discord-enrollment.json').read_text())
        target=policy.get('maintenance_dm') or {}
        if target.get('owner_id')!=policy['owner_id'] or not str(target.get('channel_id','')).isdecimal():return None
        result=copy.deepcopy(cfg)
        result.home_channel.chat_id=target['channel_id']
        result.home_channel.thread_id=None
        result.home_channel.user_id=policy['owner_id']
        result.home_channel.scope_id=None
        return result
    except (OSError,ValueError,KeyError,AttributeError):return None

def install():
    from gateway.run import GatewayRunner
    original=GatewayRunner._home_channel_transports
    if getattr(original,'_hq_owner_notices',False):return
    def transports(self):
        for platform,cfg,home,transport in original(self):
            yield platform,cfg,home,transport
            dm=dm_config(platform,cfg)
            if dm:yield platform,dm,dm.home_channel,transport
    transports._hq_owner_notices=True
    GatewayRunner._home_channel_transports=transports
    configs=GatewayRunner._served_home_channel_configs
    def served(self):
        for profile,platform,cfg in configs(self):
            yield profile,platform,cfg
            if profile is None:
                dm=dm_config(platform,cfg)
                if dm:yield profile,platform,dm
    GatewayRunner._served_home_channel_configs=served
