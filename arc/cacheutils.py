# Copyright 2017, Goethe University
#
# This library is free software; you can redistribute it and/or
# modify it either under the terms of:
#
#   the EUPL, Version 1.1 or – as soon they will be approved by the
#   European Commission - subsequent versions of the EUPL (the
#   "Licence"). You may obtain a copy of the Licence at:
#   https://joinup.ec.europa.eu/software/page/eupl
#
# or
#
#   the terms of the Mozilla Public License, v. 2.0. If a copy of the
#   MPL was not distributed with this file, You can obtain one at
#   http://mozilla.org/MPL/2.0/.
#
# If you do not alter this notice, a recipient may use your version of
# this file under either the MPL or the EUPL.
import re
import unicodedata
from . import decode
import deromanize as dr
from deromanize import cacheutils
CacheObject, CacheDB = cacheutils.CacheObject, cacheutils.CacheDB
NOCHECK = {'־', 'h', 'ה', '-', '։', ';'}
try:
    from HspellPy import Hspell
    hspell = Hspell(linguistics=True)
except ImportError:
    hspell = None


class FieldError(Exception):
    pass


class NoMatch(Exception):
    def __init__(self, replist, heb):
        self.replist = replist
        self.heb = heb

    def __str__(self):
        return "{!r} couldn't be deromanized to match {!r}". \
            format(self.replist.key, self.heb)


def loc_converter_factory(simple_reps, set_reps):
    replace = cacheutils.replacer_maker(simple_reps, set_reps)

    def get_loc(rep):
        flat_vowels = cacheutils.strip_chars(rep.keyvalue)
        loc = ''.join((i[0] for i in replace(flat_vowels)))
        if len(loc) > 1:
            if loc[0] == 'ʾ':
                loc = loc[1:]
            if loc[-1] == 'ʾ':
                loc = loc[:-1]
            loc = loc.replace('-ʾ', '-')
        return loc

    return get_loc


def loc2phon(loc):
    vowels = 'ieaou'
    gstops = {'ʿ', 'ʾ'}
    phon = loc.replace('ḥ', 'ch').replace('kh', 'ch')
    if phon[-1] == 'h' and phon[-2:-1] in vowels:
        phon = phon[:-1]
    phon = ''.join(
        c for c in unicodedata.normalize('NFD', phon)
        if unicodedata.category(c)[0] == 'L' and c not in gstops
    )
    for v in vowels:
        phon = phon.replace(v+v, v+"'"+v)
    return phon


def remove_prefixes(pairs):
    new = []
    for heb, loc in pairs:
        _, heb, _ = decode.double_junker(heb)
        _, loc, _ = decode.double_junker(loc)
        romlist = loc.split('-')
        newheb = heb[len(romlist)-1:]
        # if len(romlist) > 1:
        #     print(romlist[-1], newheb)
        loc = romlist[-1]
        if len(loc) > 1:
            if loc[0] == 'ʾ':
                loc = loc[1:]
            if loc[-1] == 'ʾ':
                loc = loc[-1]
        new.append([newheb, loc])
    return new


def matcher_factory(simple_reps, set_reps):
    get_loc = loc_converter_factory(simple_reps, set_reps)

    def match_output(generated, submitted):
        breaks = re.compile(r'[\s־]+')
        submittedl = [i for i in breaks.split(submitted) if i not in NOCHECK]
        generatedl = [i for i in generated if i.key not in NOCHECK]
        if len(submittedl) != len(generatedl):
            raise FieldError("number of fields didn't match")
        else:
            matches = []
            for gen, sub in zip(generatedl, submittedl):
                for rep in gen:
                    if str(rep) == sub:
                        matches.append((sub, get_loc(rep)))
                        break
                else:
                    raise NoMatch(gen, sub)

            return matches

    return match_output


def form_builder_factory(simple_reps, set_reps):
    match_output = matcher_factory(simple_reps, set_reps)

    def form_builder(decoded, submitted):
        matches = match_output(decoded, submitted)
        matches = remove_prefixes(matches)
        for m in matches:
            m.append(loc2phon(m[1]))
        return matches

    return form_builder


# get stuff out of the caches
def collect_keys(rlist: dr.ReplacementList, decoder):
    """returns a dictionary where each key is the phonological value of
    replacements from a given replist. Each value is a dictionary. The keys of
    these inner dictionaries have hebrew forms as keys and the original
    Replacements as values.
    """
    loc_keys = {}
    phon_keys = {}
    for rep in rlist:
        heb = str(rep)
        loc = decoder.get_loc(rep)
        phon = loc2phon(loc)
        loc_keys.setdefault(loc, {})[heb] = rep
        phon_keys.setdefault(phon, {})[heb] = rep
    return loc_keys, phon_keys


def ignore_seen(ignore, *dicts):
    # side effects!!
    if ignore:
        for heb in ignore:
            for d in dicts:
                try:
                    del d[heb]
                except KeyError:
                    pass


def get_stats(rep_dict: dict, cached_vals: dict, key):
    total = 0
    cached_reps = []
    others = []
    for heb, count in cached_vals.items():
        total += count
        try:
            new = rep_dict.pop(heb)
            cached_reps.append((count, new))
        except KeyError:
            others.append((count, heb))

    matched = []
    for count, rep in cached_reps:
        rep.weight = (count / total) / 2 + rep.weight/2
        matched.append(rep)
    unmatched = [
        dr.StatRep.new(count/total, heb, key) for count, heb in others]
    uncached = list(rep_dict.values())
    return matched, unmatched, uncached


def get_newreps(keys, cache, ignore=None):
    matched = []
    unmatched = []
    uncached = []
    for k, rep_dict in keys.items():
        cached = cache[k]
        ignore_seen(ignore, rep_dict, cached)
        m, um, uc = get_stats(rep_dict, cached, k)
        matched += m
        unmatched += um
        uncached += uc
    return matched, unmatched, uncached


def match_cached(
        chunk,
        decoder,
        loc_cache,
        phon_cache,
        spelling_fallback=False
) -> dr.ReplacementList:
    if not isinstance(chunk, decode.Chunk):
        return chunk

    rlist = chunk.base.stripped_heb.makestat()
    if rlist.key in NOCHECK or len(rlist.key) <= 1:
        return chunk.heb
    for rep in rlist:
        try:
            int(str(rep))
            return chunk.heb
        except ValueError:
            pass

    loc_keys, phon_keys = collect_keys(rlist, decoder)
    matchedloc, unmatchedloc, _ = get_newreps(loc_keys, loc_cache)
    ignore = [str(r) for r in matchedloc]
    ignore += [str(r) for r in unmatchedloc]
    matchedphon, unmatchedphon, uncached = get_newreps(
        phon_keys, phon_cache, ignore)
    cached = []
    for reps in (matchedloc, unmatchedloc, matchedphon, unmatchedphon):
        reps.sort(key=lambda r: r.weight, reverse=True)
        cached.extend(reps)

    if spelling_fallback:
        for r in uncached:
            r.weight /= 2
            heb = str(r)
            try:
                if not (hspell.check_word(heb) and hspell.linginfo(heb)):
                    r.weight /= 100
            except UnicodeEncodeError:
                pass
    uncached.sort(key=lambda r: r.weight, reverse=True)
    new_rlist = dr.ReplacementList(rlist.keyparts, cached + uncached)
    return chunk.basemerge(new_rlist)
