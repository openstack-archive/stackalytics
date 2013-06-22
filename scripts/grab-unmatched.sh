#!/bin/bash

grep -v '^#' unmatched-names | \
  while read line; do \

    echo
    echo "LINE: $line"

    EMAIL=$(echo "$line" | awk -F" " '{print $1}')
    NAME=$(echo "$line" | cut -d ' ' -f2-)
#    echo $EMAIL
#    echo $NAME

    LAUNCHPAD=$(links -dump -codepage UTF-8 -http.extra-header "Cookie: PREF=ID=532e2937af64f34a:FF=0:NW=1:TM=1363615469:LM=1363615469:S=RQ32u6mIZ60kEpWC; NID=67=oaBHx3gZQzXJUBSwHhFGDPEnD9G_kGy-3MedWLoLiG-qPmMRIgDqehVG0epg-SzYAvqR4KMWNTzE2JLt-Cp03mdh1iAnHI5JMKp3mDYO32JySQMC_e5x1zLOxpE_YuEH" "http://google.com/search?ie=windows-1251&hl=ru&source=hp&q=$NAME+site%3Alaunchpad.net&btnG=%CF%EE%E8%F1%EA+%E2+Google&gbv=1" | grep launchpad.net/~ | \
    sed -r 's/.*launchpad.net\/~([a-z0-9\.-]+).*/\1/' | uniq | sort)

    echo "LAUNCHPAD: $LAUNCHPAD"

    if [ $LAUNCHPAD ]; then

      RES=$(links -dump https://launchpad.net/~$LAUNCHPAD | grep "$NAME")

      if [ -n "$RES" ]; then
        echo "$LAUNCHPAD $EMAIL $NAME ---- $RES"
      fi

    fi

    if [ -z $LAUNCHPAD ]; then
      echo "********** $EMAIL $NAME"
    fi

    sleep 1

  done
