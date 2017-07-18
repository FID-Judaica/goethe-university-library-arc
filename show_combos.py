#!/usr/bin/env python3
import sys
from pathlib import Path
import deromanize
import yaml
CONFIG_FILE = Path(__file__).parent/'data'/'new.yml'
keys = deromanize.KeyGenerator(yaml.safe_load(CONFIG_FILE.open()))


def main():
    pairs = {pair
             for key in keys
             for replist in keys[key].values()
             for rep in replist
             for pair in rep.keyvalue}

    print(*pairs, sep='\n')
    print(len(pairs))


if __name__ == '__main__':
    main()
