import sys
import argparse
import yaml
import arc
from pathlib import Path
from . import cacheutils
PROJ_PATH = Path(arc.__file__).parents[1]


def expand_kv(key, value):
    lk, lv = len(key), len(value)
    if lk > lv:
        value = value + ' ' * (lk-lv)
    else:
        key = key + ' ' * (lv-lk)
    return key, value


def main():
    ap = argparse.ArgumentParser(description='show some Hebrew things')
    add = ap.add_argument
    add('--reverse-heb', '-r', action='store_true',
        help='reverse output for terminal')
    add('--show-new', '-n', action='store_true',
        help='Show the corrected from of the word with LoC transliteration')
    add('--debug', '-d', action='store_true', help='show debugging info')
    add('--numbers', '-N', action='store_true', help='show "secret" numbers')
    add('--crop', '-c', type=int, default=0)
    add('--sep', '-s', default='│')
    add('--probabilites', '-p', action='store_true')
    add('--standard', default='old')
    add('--loc', '-l', action='store_true')
    args = ap.parse_args()

    if args.loc:
        args.standard = 'loc'

    if args.standard == 'old':
        config_file = PROJ_PATH/'data'/'old.yml'
    elif args.standard in ['loc', 'new']:
        config_file = PROJ_PATH/'data'/'new.yml'
    profile = yaml.safe_load(config_file.open())
    decoder = arc.Decoder(profile, fix_numerals=True)
    set_reps = decoder.profile['to_new']['sets']
    simple_reps = decoder.profile['to_new']['replacements']
    global replace
    get_loc = cacheutils.loc_converter_factory(simple_reps, set_reps)

    for t in map(str.rstrip, sys.stdin):
        print(t)
        for word in decoder.decode(t):
            word.prune()
            if args.probabilites:
                word.makestat()
            for i, w in enumerate(word):
                if args.crop and args.crop == i:
                    break
                items = []
                items.append(str(w)[::-1] if args.reverse_heb else w)
                if args.show_new:
                    items.append(get_loc(w))
                if args.numbers:
                    items.append(w.weight)
                print(*items, sep='\t')
                if args.debug:
                    atoms = [expand_kv(k, v) for k, v in w.keyvalue]
                    print('  ' + args.sep.join(rom for rom, _ in atoms))
                    print('  ' + args.sep.join(heb for _, heb in atoms) + '\n')
        print()


if __name__ == '__main__':
    main()
