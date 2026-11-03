#!/usr/bin/env python3
"""Replace a Discord bot token locally without repeating server enrollment."""
import json,os,subprocess
from enroll_discord import ROOT,EnrollmentError,validated_application

def main():
    os.umask(0o077)
    values=json.loads((ROOT/'profiles/concierge/discord-enrollment.json').read_text())
    print('In the Discord Developer Portal, open this application > Bot > Reset Token.')
    print('Paste the NEW token into this terminal only. Server/channel settings will be preserved.')
    token=validated_application(values['application_id'])
    path=ROOT/'access/discord-token'
    path.write_text(token+'\n');path.chmod(0o600)
    subprocess.run(['docker','compose','-f',str(ROOT/'compose.yaml'),'--profile','discord','up','-d','--force-recreate','concierge'],check=True)
    print('New token saved locally; gateway recreated. Ask the assistant to verify Discord reconnection.')

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:print('\nCancelled.')
    except EnrollmentError as e:print(str(e));raise SystemExit(1)
    except Exception as e:print('Rotation stopped: '+type(e).__name__+'. Credential omitted.');raise SystemExit(1)
