import argparse
import collections
import json
import sys
from arc import config
from . import cacheutils as cu

CFG = config.Config()


def expand_kv(key, value):
    """add whitespace so columns look good"""
    lk, lv = len(key), len(value)
    if lk > lv:
        value = value + " " * (lk - lv)
    else:
        key = key + " " * (lv - lk)
    return key, value


def use_dict(rlist, dictionary):
    if not dictionary:
        return

    newlist = []
    for rep in rlist:
        val = dictionary.get(str(rep))
        if val is None:
            continue
        rep.weight = val
        newlist.append(rep)

    if newlist:
        rlist.data = newlist
        rlist.sort(reverse=True)


def main():
    ap = argparse.ArgumentParser(description="show some Hebrew things")
    add = ap.add_argument
    add(
        "--reverse-heb",
        "-r",
        action="store_true",
        help="reverse output for terminal",
    )
    add(
        "--show-new",
        "-n",
        action="store_true",
        help="Show the corrected from of the word with LoC transliteration",
    )
    add("--debug", "-d", action="store_true", help="show debugging info")
    add("--cache", "-C", action="store_true", help="use the cached forms")
    add("--dictionary", nargs="*", type=lambda x: json.load(open(x)))
    add("--numbers", "-N", action="store_true", help='show "secret" numbers')
    add("--crop", "-c", type=int, default=0)
    add("--spelling", "-s", action="store_true")
    add("--sep", default="│")
    add("--probabilites", "-p", action="store_true")
    add("--standard", default="old")
    add("--loc", "-l", action="store_true")
    args = ap.parse_args()

    if args.loc:
        args.standard = "new"

    decoder = CFG.from_schema(
        args.standard, fix_numerals=True, spellcheck=args.spelling
    )

    if args.dictionary:
        dictionary = collections.Counter()
        for d in args.dictionary:
            dictionary.update(d)
    else:
        dictionary = None

    if args.cache:
        loccache, phoncache = CFG.get_caches("LOC/ALA", "phonological")

    for t in map(str.rstrip, sys.stdin):
        print(t)
        print()
        for chunk in decoder.make_chunks(t):
            print(chunk.rom)
            print("-" * len(chunk.rom))
            if args.cache:
                word = cu.match_cached(chunk, decoder, loccache, phoncache)
            else:
                word = chunk.heb
            # use_dict(word, dictionary)
            if args.probabilites:
                word = word.makestat()
            for i, w in enumerate(word):
                if args.crop and args.crop == i:
                    break
                items = []
                items.append(str(w)[::-1] if args.reverse_heb else w)
                if args.show_new:
                    items.append(decoder.get_loc(w))
                if args.numbers:
                    items.append(
                        "%.2f" % w.weight
                        if isinstance(w.weight, float)
                        else w.weight
                    )
                print(*items, sep="\t")
                if args.debug:
                    atoms = [expand_kv(k, v) for k, v in w.keyvalue]
                    print("  " + args.sep.join(rom for rom, _ in atoms))
                    print("  " + args.sep.join(heb for _, heb in atoms) + "\n")
            print()


if __name__ == "__main__":
    main()
