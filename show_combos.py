#!/usr/bin/env python3
from pathlib import Path
import deromanize
import yaml
import unicodedata
CONFIG_FILE = Path(__file__).parent/'data'/'old.yml'
VOWELS = set('ieaou')

keys = deromanize.KeyGenerator(yaml.safe_load(CONFIG_FILE.open()))


def flatten_vowels(letterpairs):
    for rom, heb in letterpairs:
        new = ''
        for c in rom:
            decomposed = unicodedata.normalize('NFD', c)
            if decomposed[0] in VOWELS:
                new += decomposed[0]
            else:
                new += c
        yield (new, heb)


def main():
    pairs = set(flatten_vowels(
        pair
        for key in keys
        for replist in keys[key].values()
        for rep in replist
        for pair in rep.keyvalue))

    print(*sorted(pairs, key=lambda x: (x[1], x[0])), sep='\n')
    print(len(pairs))


if __name__ == '__main__':
    main()
