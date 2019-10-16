#!/usr/bin/env bash

script_path="$PWD/${0#./}"
proj_dir="${script_path%/*/*}"
cd "$proj_dir"

proj=fid-judaica
repos=( "deromanize" "pica_parse.py" "filtermaker" )

for repo in "${repos[@]}"; do
  if [[ ! -e $repo ]]; then
    git clone "https://github.com/$proj/$repo"
  fi
  pip install -e $repo
done

pip install -U "git+https://github.com/OriHoch/python-hebrew-numbers"

pip install -e .
