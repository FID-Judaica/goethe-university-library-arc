#!/bin/sh

repos=( "deromanize" "pica_parse.py" "filtermaker" )

printf "\e[31mStatus of Subrepos\e[0m\n"

for repo in "${repos[@]}"; do
  printf "\e[34m__________________\e[0m\n"
  printf "\e[33m$repo\e[0m\n"
  pushd "$repo" > /dev/null
  git status
  popd > /dev/null
done

printf "\e[31m__________________\e[0m\n\n"
