#!/bin/bash

grep -v '^#' grizzly-with-libs | \
  while read project; do \
    cd ~/Work/metric-root/$project; \
    git log | awk -F '[<>]' '/^Author:/ {print $2}'; \
  done | sort | uniq | grep -v '\((none)\|\.local\)$' > tmp
sed 's/ /\n/' < aliases >> tmp
sed 's/ /\n/' < other-aliases >> tmp
(sort | uniq | grep -v '\((none)\|\.local\)$') < tmp > emails.txt
rm tmp
