#!/usr/bin/env bash

script_path="$PWD/${0#./}"
proj_dir="${script_path%/*/*}"
cd "$proj_dir"

proj=fid-judaica
repos=( "deromanize" "pica_parse.py" "filtermaker" )

for repo in "${repos[@]}"; do
  git clone "https://github.com/$proj/$repo"
  pip install -e $repo
done

git clone --recurse-submodules "https://github.com/OriHoch/python-hebrew-numbers"
pip install -U ./python-hebrew-numbers
rm -rf python-hebrew-numbers

pip install -e .
