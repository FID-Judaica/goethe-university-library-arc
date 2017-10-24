#!/usr/bin/env python3
from pathlib import Path
import deromanize
import yaml
from deromanize import cacheutils
CONFIG_FILE = Path(__file__).parent/'data'/'old.yml'
keys = deromanize.KeyGenerator(yaml.safe_load(CONFIG_FILE.open()))


def main():
    pairs = set()
    for key in keys:
        pairs.update(
                set(cacheutils.strip_chars(cacheutils.get_combos(keys[key]))))
    print(*sorted(pairs, key=lambda x: (x[1], x[0])), sep='\n')
    print(len(pairs))


if __name__ == '__main__':
    main()
