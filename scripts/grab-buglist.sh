#!/bin/bash

grep -v '^#' grizzly-with-libs | \
  while read project; do \
    .././tools/with_venv.sh python ./launchpad/buglist.py $project grizzly; \
  done > buglist.txt
