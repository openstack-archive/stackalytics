#!/bin/bash

grep -v '^#' grizzly-with-libs | \
  while read project; do cat ~/Work/metric-root/$project/.mailmap; done | \
  grep -v '^#' | sed 's/^[^<]*<\([^>]*\)>/\1/' | \
  grep '<.*>' | sed -e 's/[<>]/ /g' | \
  awk '{if ($3 != "") { print $3" "$1 } else {print $2" "$1}}' | \
  sort | uniq > aliases
