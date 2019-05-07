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
import collections
import re
import unicodedata
import deromanize as dr
import libaaron
from deromanize import trees, keygenerator as kg, get_self_rep
from . import cacheutils
from .matchprefix import prefixmatcherfactory
import hebrew_numbers

matchprefix = prefixmatcherfactory()

try:
    from HspellPy import Hspell

    hspell = Hspell(linguistics=True)
except ImportError:
    hspell = None


class DecoderMismatch(Exception):
    pass


class NoMatch(Exception):
    pass


class Decoder:
    """Decoder class for our catalogue standards."""

    def __init__(
        self,
        profile,
        strip_func=None,
        fix_numerals=False,
        spellcheck=False,
        fix_k=False,
    ):
        """Initialize with a deserialized profile from deromanize"""
        self.profile = profile
        self.joined_prefix = trees.Trie(
            {i: i for i in profile["joined_prefixes"]}
        )
        self.prefix_vowels = set(profile["prefix_vowels"]) | {""}
        self.gem_prefix = trees.Trie({i: i for i in profile["gem_prefixes"]})
        self.keys = dr.KeyGenerator(profile)
        self.num = fix_numerals
        self.sp = spellcheck
        self.w_kw = {
            "decoder": self,
            "fix_numerals": self.num,
            "spellcheck": self.sp,
        }
        if strip_func:
            self.strip = strip_func
        else:
            self.strip = dr.stripper_factory(
                profile["vowels"].items(),
                profile["consonants"].items(),
                "0123456789",
            )

        self.fix_k = mk_k_fixer(profile["vowels"]) if fix_k else None
        set_reps = profile["to_new"]["sets"]
        simple_reps = profile["to_new"]["replacements"]
        self.get_loc = cacheutils.loc_converter_factory(simple_reps, set_reps)

    def locandphon(self, rep):
        loc = self.get_loc(rep)
        return loc, cacheutils.loc2phon(loc)

    def __getitem__(self, key):
        return self.profile[key]

    def decode(self, line, strip=False, link=False):
        """Return a list of Word instances from a given line of input."""
        chunks = self.make_chunks(line)
        return chunks.get_heb(strip=strip, link=link)

    def get_rom(self, chunks):
        romed = []
        for chunk in chunks:
            if isinstance(chunk, Chunk):
                try:
                    romed.append("-".join(i.word for i in chunk))
                except AttributeError:
                    raise
            else:
                romed.append(str(chunk))
        return romed

    def make_chunks(self, line: str):
        line = line.lower()
        if self.fix_k:
            line = self.fix_k(line)
        cleaned_line = cleanline(line)
        raw_chunks = [i.split("-") for i in cleaned_line.split()]
        remixed = Chunks(self)
        for chunk in raw_chunks:
            if chunk == ["", ""]:
                remixed.append("-")
                continue
            new_chunk = Chunk()
            for i, inner in enumerate(chunk[:-1]):
                preparts = self.checkprefix(i, inner, chunk)
                if preparts:
                    new_chunk.extend(Prefix(p, self) for p in preparts)
                else:
                    new_chunk.append(Word(inner, **self.w_kw))
                    remixed.extend([new_chunk, maqef])
                    new_chunk = Chunk()
            if new_chunk:
                new_chunk.append(Word(chunk[-1], **self.w_kw))
                remixed.append(new_chunk)
            else:
                remixed.append(Chunk([Word(chunk[-1], **self.w_kw)]))
        return remixed

    def checkprefix(self, i, inner, chunk):
        front, part, back = self.strip(inner)
        _, nextp, _ = self.strip(chunk[i + 1])
        # new:
        parts = matchprefix(part, nextp, dedup=False)
        if not parts:
            return None
        return parts


def cleanline(line):

    if line[0] == "@":
        line = line[1:]

    line = debracket(line)

    if "- " in line:
        line = re.sub(r"(\w)- +([^@])", r"\1-\2", line)
    if " -" in line:
        line = re.sub(r" -(\w)", r"-\1", line)
    if line.startswith("ha"):
        line = re.sub(r"^ha\w{0,2}- *@", "h @", line)

    line = re.sub(r"\b([blw])([î]-|-[iî])", r"\1i-yĕ", line)
    line = line.replace("ʼ", "'")
    return line


def mk_k_fixer(vowels):
    vowels = "".join(vowels)
    exp = re.compile("(?<=[" + vowels + "])k(?![k-])")

    def fix_k(line):
        if "k" not in line:
            return line
        return exp.sub("ḵ", line)

    return fix_k


def debracket(line):
    # # bracket shenanigans # #
    rebracket = False
    if line[0] == "[" and line[-1] == "]" and "]" not in line[:-1]:
        line = line[1:-1]
        rebracket = True
    if "[" in line:
        line = re.sub(r"\[.*?\]", "", line)
    if rebracket:
        line = "[" + line + "]"
    line = remove_combining(line)
    return line


def remove_combining(line):
    new_line = []
    for c in line:
        if unicodedata.category(c) != "Mn":
            new_line.append(c)
    return "".join(new_line)


class Word:
    __slots__ = "word", "split", "keys", "num", "sp", "_stripped_heb", "_heb"

    def __init__(self, word, decoder, fix_numerals=False, spellcheck=False):
        self.word = word
        self.split = decoder.strip(word)
        self.keys = decoder.keys
        self.num = fix_numerals
        self.sp = spellcheck

    @property
    def stripped_heb(self):
        try:
            return self._stripped_heb
        except AttributeError:
            pass
        front, rom, back = self.split
        try:
            word = coredecode(self.keys, rom, self.sp)
        except KeyError:
            if self.num:
                try:
                    word = fix_numerals(rom)
                except ValueError:
                    word = get_self_rep(self.word)
            else:
                word = get_self_rep(self.word)

        except IndexError:
            return
        self._stripped_heb = word
        return word

    @property
    def heb(self):
        try:
            return self._heb
        except AttributeError:
            pass
        front, rom, back = self.split
        word = self.stripped_heb
        if word is None:
            return
        if front:
            word = get_self_rep(front) + word
        if back:
            word = word + get_self_rep(back)
        self._heb = word
        return word

    def __repr__(self):
        return "Word({!r})".format(self.word)


class Prefix(Word):
    __slots__ = "word", "split", "keys", "num", "sp", "_stripped_heb", "_heb"

    @libaaron.cached
    def stripped_heb(self):
        front, rom, back = self.split
        word, remainder = self.keys["front"].getpart(rom)
        # work on a copy because we're going to modify the object's state
        word = word.copy()
        rep = dr.Replacement
        key = word.key + remainder[0:1]
        w = word[0]
        word.data = [rep.new(w.weight, str(w), key) + rep.new(0, "", "-")]
        return word

    def __repr__(self):
        return "Prefix({!r})".format(self.word)


class LinkedReplist(collections.UserList):
    __slots__ = "data", "linked", "_head_dict"

    def __init__(self, *linked):
        self.data = linked[0]
        self.linked = linked

    def __repr__(self):
        return "LinkedReplist(" + ", ".join(repr(i) for i in self.linked) + ")"

    def __delitem__(self, index):
        for replist in self.linked:
            del replist[index]

    def sort(self, reverse=False):
        for row in self.groups():
            for cell in row[1:]:
                cell.weight = row[0].weight

        for replist in self.linked:
            replist.sort(reverse=reverse)

    def groups(self, index=None):
        if index is None:
            return list(zip(*self.linked))
        else:
            return tuple(rlist[index] for rlist in self.linked)

    @libaaron.cached
    def head_dict(self):
        hd = {}
        for i, reps in enumerate(self.groups()):
            hd.setdefault(str(reps[0]), []).append((i, reps))
        return hd

    def copy(self):
        return type(self)(*[l.copy() for l in self.linked])


class Chunk(collections.UserList):
    def __init__(self, parts=None):
        self.data = parts or []
        self.reorder = None

    @property
    def rom(self):
        return "-".join(p.word for p in self)

    def replist_gen(self, strip=False):
        prefix = self.prefix_gen(strip)
        if strip:
            he = self.base.stripped_heb
        else:
            he = self.base.heb

        if prefix:
            he = hyphenate(he)
        return prefix + he

    def prefix_gen(self, strip=False):
        return dr.add_rlists(
            [i.stripped_heb if strip else i.heb for i in self.data[:-1]]
        )

    def __repr__(self):
        return "Chunk({!r})".format(self.data)

    @property
    def base(self):
        return self.data[-1]

    def basemerge(
        self, rebase: dr.ReplacementList, with_prefix=False, gershayim=True
    ):
        if gershayim:
            rebase = dr.fix_gershayim_late(rebase)
        base = self.base
        maybe_hyphenate = True
        if with_prefix:
            prefix = dr.get_self_rep(self.data[0].split[0])
        else:
            prefix = self.prefix_gen()
            if base.split[0]:
                prefix = prefix + dr.get_self_rep(base.split[0])
                maybe_hyphenate = False
        if prefix and maybe_hyphenate:
            rebase = hyphenate(rebase)
        end = dr.get_self_rep(base.split[2])
        return dr.add_rlists((prefix, rebase, end))

    @libaaron.reify
    def stripped_heb(self):
        return self.replist_gen(strip=True)

    @libaaron.reify
    def heb(self):
        return self.replist_gen(strip=False)

    @libaaron.reify
    def linked_heb(self):
        return LinkedReplist(
            self.stripped_heb, self.heb, self[-1].stripped_heb
        )

    def groups(self):
        return self.linked_heb.groups()

    def get_selected_pair(self, selected):
        for i, rep in enumerate(self.stripped_heb):
            if str(rep) == selected:
                break
        full = self.heb[i]
        base = self.base.stripped_heb[i]
        return base, full

    def get_match(self, word):
        return self.linked_heb.head_dict[word]

    def __hash__(self):
        return hash(tuple(self.data))


def hyphenate(rlist):
    rlist = rlist.copy()
    if isinstance(rlist[0], dr.StatRep):
        weight = 1
    else:
        weight = 0
    for i in range(len(rlist)):
        rep = rlist[i]
        if rlist.key == str(rep) and rlist.key != "":
            rlist.keyparts = ("-",) + rlist.keyparts
            rlist[i] = rep.new(weight, "-", "") + type(rep)(
                rep.weight, rep.keyvalue
            )
    return rlist


class Chunks(collections.UserList):
    def __init__(self, decoder, chunks=None):
        self.data = chunks or []
        self.decoder = decoder

    def __repr__(self):
        return "<Chunks: {!r}>".format(self.data)

    def __add__(self, other):
        if self.decoder is not other.decoder:
            raise DecoderMismatch
        new = Chunks(self.decoder, self.data + other.data)
        new.stripped_heb = self.stripped_heb + other.stripped_heb
        new.heb = self.heb + other.heb
        return new

    def get_word_chunks(self):
        """Returns an iterable of what appear to be word chunks, mostly for
        attaching the corresponding Hebrew word from the match for caching
        later.
        """
        for chunk in self:
            if isinstance(chunk, Chunk):
                yield chunk

    def get_heb(self, strip=False, link=False):
        hebz = []
        dec = self.decoder
        for chunk in self:
            if isinstance(chunk, Chunk):
                if link:
                    hebz.append(chunk.linked_heb)
                elif strip:
                    hebz.append(chunk.stripped_heb)
                else:
                    hebz.append(chunk.heb)
                if dec.sp == "double":
                    double_check_spelling(hebz[-1], dec.strip)
            elif chunk is maqef:
                if not strip:
                    hebz.append(chunk)
            else:
                hebz.append(get_self_rep(chunk))
        return hebz

    @libaaron.reify
    def stripped_heb(self):
        return self.get_heb(strip=True)

    @libaaron.reify
    def heb(self):
        return self.get_heb(strip=False)

    @libaaron.reify
    def linked_heb(self):
        return self.get_heb(strip=True, link=True)

    def link_from_wordlist(self, wordlist):
        word_iter = iter(wordlist)
        word_counts = collections.Counter()
        reps = []
        cacheable = []
        for chunk in self:
            if isinstance(chunk, Chunk):
                curword = next(word_iter)
                if not curword:
                    raise NoMatch
                stripped, full, base = chunk.get_match(curword)[
                    word_counts[curword]
                ][1]
                word_counts[curword] += 1

                reps.append(full)
                cacheable.append(base)
            elif chunk is maqef:
                reps.append(chunk)
            else:
                reps.append(get_self_rep(chunk))

        return reps, cacheable, list(word_iter)


def coredecode(keys, word, spellcheck=False):
    if word == "":
        return get_self_rep(word)
    # add aleph to words that begin with vowels.
    vowels = keys.profile["vowels"]
    if word[0] in vowels:
        word = "ʾ" + word
    # remove doubled letters
    newword = word[0]
    for i, c in enumerate(word[1:]):
        i += 1
        if c != word[i - 1]:
            newword += c
    replist = dr.front_mid_end_decode(keys, newword)
    if spellcheck:
        check_spelling(replist)
    replist.prune()
    return replist


def fix_numerals(int_str, gershayim=False):
    front, num, back = num_strip(int_str)
    length = len(num)
    if length > 3:
        if num[0] == "5":
            num = num[1:]
        else:
            return get_self_rep(int_str)

    try:
        heb = hebrew_numbers.int_to_gematria(num)
    except KeyError:
        return get_self_rep(int_str)

    if not gershayim:
        heb = heb.replace("״", '"')
    if length >= 3:
        return kg.ReplacementList.new(int_str, [front + heb + back, int_str])
    else:
        return kg.ReplacementList.new(int_str, [int_str, front + heb + back])


def check_spelling(replist):
    # side effects
    for r in replist:
        heb = str(r)
        if not (hspell.check_word(heb) and hspell.linginfo(heb)):
            r.weight += 200


def double_check_spelling(replist, strip_func):
    for rep in replist:
        if rep.weight < 0:
            _, core, _ = strip_func(str(rep))
            try:
                if not hspell.check_word(core):
                    rep.weight += 1000
            except UnicodeEncodeError:
                pass
        else:
            break
    replist.sort()


num_strip = dr.stripper_factory(("0123456789",))


class FakeReplacementList(kg.ReplacementList):
    pass


# maqef = FakeReplacementList.new("-", ["־"])
maqef = FakeReplacementList.new("-", ["-"])
maqef.heb = maqef
maqef.rom = "-"
maqef.stripped_heb = get_self_rep("")
maqef.word = "-"
