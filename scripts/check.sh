#!/usr/bin/env bash

script_path="$PWD/${0#./}"
proj_dir="${script_path%/*/*}"
cd "$proj_dir"

repos=( "deromanize" "pica_parse.py" "filtermaker" )

for repo in "${repos[@]}"; do
  printf "$repo\n"
  pushd "$repo"
  git status -s
  printf "\n---------------\n\n"
  popd
done
