import collections
import json
import re
import deromanize.tools

try:
    import Levenshtein
except ImportError:
    Levenshtein = None
word_bound = re.compile(r"(?:\s|-(?!\d)|>>)+")


class QueryError(Exception):
    pass


class EmptyQuery(Exception):
    pass


class MultiMatchError(Exception):
    pass


class NoMatchError(Exception):
    pass


def get_ngrams(sequence, n):
    return (sequence[i : i + n] for i in range(len(sequence) - n + 1))


def get_all_ngrams(sequence):
    for i in range(len(sequence), 0, -1):
        yield from get_ngrams(sequence, i)


def compare(seq1, seq2):
    """compare sequences by their difference in length, Jaccard index, and the
    length of the longest matching ngrams.
    """
    if seq1 == seq2:
        return 1
    len_diff = len(seq1) / len(seq2)
    if len_diff > 1:
        len_diff = 1 / len_diff

    ngrams1 = {tuple(ng) for ng in get_all_ngrams(seq1)}
    ngrams2 = {tuple(ng) for ng in get_all_ngrams(seq2)}

    overall = len(ngrams1 & ngrams2) / len(ngrams1 | ngrams2)
    if overall == 1 or overall == 0:
        return overall

    try:
        max_match = len(max(ngrams1 & ngrams2, key=len)) / len(seq1)
    except ValueError:
        return 0

    return (len_diff + max_match + overall) / 3


def compare_str(seq1, seq2):
    """returns a fraction based on the Levenshtein distance of two strings"""
    if seq1 == seq2:
        return 1
    ld = Levenshtein.distance(seq1, seq2)
    longest = len(seq1 if len(seq1) > len(seq2) else seq2)
    return (longest - ld) / longest


def match_words_to_search(chunks, searchresult, compare_func, join=True):
    """returns a fraction expressing how well transliteration chunks can be
    mapped to a string.
    """
    wordlist = [hebstrip(w)[1] for w in word_bound.split(searchresult)]
    wordset = set(wordlist)
    genlist = [
        m
        for m in [
            match_one(rlist, wordset)
            for rlist in chunks.linked_heb
            if rlist.data
        ]
        if m
    ]
    ours = [i[0] for i in genlist]
    theirs = [i[1] for i in genlist]
    if join:
        return compare_func(" ".join(ours), " ".join(wordlist)), theirs
    else:
        return compare_func(ours, wordlist), theirs


def fuzzy_match(replist, wordset):
    """find the closest match in a replist to words in a wordset by Levenshtein
    distance.
    """
    matches = []
    for rep in replist:
        for word in wordset:
            matches.append((Levenshtein.distance(str(rep), word), word, rep))

    matches.sort(key=lambda x: (x[0], x[2].weight))
    try:
        return str(matches[0][2]), matches[0][1]
    except IndexError:
        return ("", "")


def match_one(replist, wordset):
    """find the closest match in a replist to words in a wordset. Looks for an
    exact match first, then falls back to fuzzy_match() (Levenshtein distance).
    """
    matches = []
    for rep in replist:
        rep = str(rep)
        if str(rep) in wordset:
            if matches:
                raise MultiMatchError
            else:
                matches.append(str(rep))

    if matches:
        return matches[0], matches[0]
    else:
        return fuzzy_match(replist, wordset)


def make_dicts(*dict_paths):
    """dict_paths: a list of paths with word frequency lists in json
    files. Returns a counter object from the composited list. Used for
    reording replists.
    """
    dicts = collections.Counter()
    for d in dict_paths:
        with open(str(d)) as fh:
            dicts.update(json.load(fh))
    return dicts


hebstrip = deromanize.tools.stripper_factory(
    "אבגדהוזחטיכךלמםנןסעפףצץקרשת1234567890"
)


def use_dict(rlist, dictionary, reweight=False):
    """takes a deromanize.ReplacementList as input, along with a word-
    frequency counter (output of nli_check.make_dicts()) and reorders it
    according to the values in the wordlist.

    WARNING: this function has no explicit return value. It only produces
    a side-effect on a replist.
    """
    if not dictionary:
        return rlist

    rlist = rlist.copy()
    notfound = []
    for i, rep in enumerate(rlist):
        w = str(rep).split("-")[-1]
        val = dictionary.get(w)
        if val is None:
            notfound.append(i)
        if reweight:
            rep.weight = val

    while notfound:
        del rlist[notfound.pop()]

    if len(rlist) == 0:
        pass

    if reweight:
        rlist.sort(reverse=True)

    return rlist


def getfirst(s):
    """get the first item out of a list if it's a list. Else, return
    the item. Kind of a stupid function.
    """
    return s[0] if isinstance(s, list) else s


def printable(title, subtitle=None, resp=None):
    """Turns a title, subtitle and responsibility statement into a
    human-friendly display formatted string.
    """
    title = getfirst(title)
    subtitle = getfirst(subtitle)
    resp = getfirst(resp)
    if subtitle:
        title += " : " + subtitle
    if resp:
        title += " / " + resp
    return title


def get_title_chunks(title, decoder, dicts=None):
    chunk_map = collections.OrderedDict()
    for n, f in (("title", "a"), ("subtitle", "d"), ("responsibility", "h")):
        try:
            chunks = decoder.make_chunks(title[f][0])
            chunk_map[n] = chunks
        except KeyError:
            pass

    if dicts:
        for chunks in chunk_map.values():
            for i, rlist in enumerate(chunks.linked_heb):
                chunks.linked_heb[i] = use_dict(rlist, dicts)

    return chunk_map


def match_title(docs, chunks_map):
    if "subtitle" in chunks_map:
        gen1 = chunks_map["title"] + chunks_map["subtitle"]
    else:
        gen1 = chunks_map["title"]
    gen2 = chunks_map["title"]

    results = []
    for doc in docs:
        search1 = printable(doc["title"][0], doc.get("subtitle")).replace(
            " : ", " "
        )
        search2 = doc["title"][0]

        try:
            match_level, genlist = match_words_to_search(
                gen1, search1, compare_str
            )
        except MultiMatchError:
            results.append((0.0001, doc, []))
            continue

        # results that don't both include a subtitle
        if not ("subtitle" in doc and "subtitle" in chunks_map):
            match_level2, genlist2 = match_words_to_search(
                gen2, search2, compare_str
            )
            if match_level2 > match_level:
                match_level, genlist = match_level2, genlist2
        try:
            resp_match, resp_genlist = match_words_to_search(
                chunks_map["responsibility"],
                doc["responsibility"][0],
                compare,
                join=False,
            )

            if resp_match:
                results.append((match_level, doc, genlist))
        except (KeyError, MultiMatchError):
            pass

    results.sort(key=lambda x: x[0], reverse=True)
    return results


def strict_match(doc, chunks_map, gen, sub, strict=True):
    try:
        resp_match, resp_genlist = match_words_to_search(
            chunks_map["responsibility"], doc["responsibility"][0], compare_str
        )

        if strict and resp_match < 0.9:
            return

    except (KeyError, MultiMatchError):
        return

    search1 = printable(doc["title"][0], doc.get("subtitle")).replace(
        " : ", " "
    )

    try:
        match_level, genlist = match_words_to_search(gen, search1, compare_str)
    except MultiMatchError:
        return 0.0001, doc, []

    # results that don't both include a subtitle
    if not sub and "subtitle" in doc:
        match_level2, genlist2 = match_words_to_search(
            gen, doc["title"][0], compare_str
        )
        if match_level2 > match_level:
            match_level, genlist = match_level2, genlist2
            del doc["subtitle"]

    return match_level, doc, genlist


def get_matches(docs, chunks_map, func=strict_match):
    results = list(iter_matches(docs, chunks_map, func))
    results.sort(key=lambda x: x[0], reverse=True)
    return results


def iter_matches(docs, chunks_map, func=strict_match):
    if "subtitle" in chunks_map:
        gen = chunks_map["title"] + chunks_map["subtitle"]
        sub = True
    else:
        gen = chunks_map["title"]
        sub = False

    for doc in docs:
        result = strict_match(doc, chunks_map, gen, sub, strict=True)
        if result is not None:
            yield result
            if result[0] == 1:
                break
