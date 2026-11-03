#!/usr/bin/env bash
set -euo pipefail
ssh -i /home/operator/.ssh/id_ed25519 -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes krishadmin@192.0.2.181 'umask 077; mkdir -p ~/.ssh; touch ~/.ssh/authorized_keys; chmod 700 ~/.ssh; chmod 600 ~/.ssh/authorized_keys; grep -qxF '"'"'from="192.0.2.180",restrict ssh-ed25519 REPLACE_WITH_YOUR_OBSERVER_PUBLIC_KEY KrishAdmin-HQ to nvidia-gpu'"'"' ~/.ssh/authorized_keys || printf "%s\n" '"'"'from="192.0.2.180",restrict ssh-ed25519 REPLACE_WITH_YOUR_OBSERVER_PUBLIC_KEY KrishAdmin-HQ to nvidia-gpu'"'"' >> ~/.ssh/authorized_keys'
ssh -i /home/operator/.ssh/krishadmin-hq-nvidia-gpu -o IdentitiesOnly=yes -o BatchMode=yes krishadmin@192.0.2.181 hostname
