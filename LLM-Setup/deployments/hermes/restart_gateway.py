#!/usr/bin/env python3
"""Planned gateway restart with the native back-online notification marker."""
import json,os,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def main():
    os.umask(0o077)
    home=ROOT/'profiles/concierge'
    cfg=json.loads((home/'config.yaml').read_text())['platforms']['discord']
    enrolled=json.loads((home/'discord-enrollment.json').read_text())
    if cfg.get('home_channel',{}).get('chat_id')!=enrolled['channel_id'] or cfg.get('gateway_restart_notification') is not True:
        raise SystemExit('Configure restart notifications for the enrolled private channel first.')
    marker=home/'.restart_pending.json';temp=marker.with_suffix('.json.tmp')
    temp.write_text(json.dumps({'requested_at':time.time(),'via_service':True,'detached':False})+'\n');temp.replace(marker)
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'--profile','discord','restart','concierge'],check=True)
    print('Restart requested. Hermes will announce when its Discord connection is online; marker remains pending until delivered.')

if __name__=='__main__':main()
