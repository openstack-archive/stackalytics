#!/bin/bash 

.././tools/with_venv.sh python launchpad/map-email-to-lp-name.py \
       $(cat emails.txt) > launchpad-ids.txt
