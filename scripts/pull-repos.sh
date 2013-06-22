#!/bin/bash

if [[ -z $STACKALYTICS_HOME ]]; then
    CONF='../etc/analytics.conf.local'
else
    CONF="$STACKALYTICS_HOME/conf/analytics.conf"
fi

TOP_DIR=$(cd $(dirname "$0") && pwd)

cd `cat $CONF | grep sources_root | awk -F"=" '{print $2}'`

for a in `dir`; do
    echo "Pulling $a"
    cd $a
    git pull
    cd ../
done
