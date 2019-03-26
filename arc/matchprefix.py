#!/usr/bin/env python3
"""Matching Hebrew prefixes is hard in records from America. That's bad.
"""
from functools import partial
from itertools import chain, product
from libaaron import pipe
from deromanize import trees

MAPJOIN = partial(map, "".join)


class Gem(str):
    """class that I can check for elsewhere"""


def getpart(trie, key, default=None):
    """trees.Trie.getpart, but with a default return value, like dict.get"""
    try:
        return trie.getpart(key)
    except KeyError:
        return default, key


def prefixgen(cons, vowels, extra):
    """pipeline for generating prefixes"""
    return pipe(product(cons, vowels), MAPJOIN, partial(chain, extra))


def prefixmatcherfactory(
    prefixvowels="iîeĕêa",
    consvavs="wṿv",
    vav_extra="uû",
    shes=("she", "še", "šē"),
    prefixconsonants="k ḵ kh b v l".split(),
    no_gem_extra=("mē", "me", "hā"),
    gem_extra=("mi", "ha", "he"),
):
    """factory that takes a bunch of data and does a lot of work and then
    returns a closure that maps prefixes. TODO: actually document parameters.
    """
    vav_prefixes = pipe(
        prefixgen(consvavs, prefixvowels, vav_extra),
        lambda i: {c: c for c in i},
        trees.Trie,
    )
    she = trees.Trie({c: Gem(c) for c in shes})
    joined_prepositions = pipe(
        prefixgen(prefixconsonants, prefixvowels, no_gem_extra),
        lambda i: {c: c for c in i},
    )
    pipe(
        prefixgen(prefixconsonants, "a", gem_extra),
        lambda i: {c: Gem(c) for c in i},
        joined_prepositions.update,
    )
    prepositions = trees.Trie(joined_prepositions)

    def matchprefix(string, nextstr, dedup=True):
        """determine whether the string is a prefix. returns components
        if yes
        """
        parts = []
        for trie in (vav_prefixes, she, prepositions):
            if not string:
                return parts
            if (
                dedup
                and parts
                and isinstance(parts[-1], Gem)
                and len(string) > 1
                and string[0] == string[1]
            ):
                string = string[1:]
            value, string = getpart(trie, string)
            if value:
                parts.append(value)
        if not parts:
            return None
        if isinstance(parts[-1], Gem) and nextstr.startswith(string):
            return parts
        return None

    return matchprefix


def main():
    """why does a main function need a docstring?"""
    matchprefix = prefixmatcherfactory()
    # print(matchprefix("ule"))
    # print(matchprefix("veshebbe"))
    # print(matchprefix("vesheba"))
    # print(matchprefix("vehan"))


if __name__ == "__main__":
    main()
