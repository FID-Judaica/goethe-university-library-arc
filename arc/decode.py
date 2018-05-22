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
import functools
import re
import unicodedata
import deromanize
from deromanize import trees, keygenerator, get_self_rep
from collections import abc
try:
    from HspellPy import Hspell
    hspell = Hspell(linguistics=True)
except ImportError:
    hspell = None
import hebrew_numbers


class DecoderMismatch(Exception):
    pass


class NoMatch(Exception):
    pass


class OopsIter(abc.Iterator):
    def __init__(self, iterable):
        self.iter = iter(iterable)
        self.stack = collections.deque()

    def __next__(self):
        if self.stack:
            return self.stack.popleft()
        else:
            return next(self.iter)

    def oops(self, item):
        self.stack.append(item)


class reify:
    """Use as a class method decorator.  It operates almost exactly like the
    Python ``@property`` decorator, but it puts the result of the method it
    decorates into the instance dict after the first call, effectively
    replacing the function it decorates with an instance variable.  It is, in
    Python parlance, a non-data descriptor.

    Stolen from pyramid.
    http://docs.pylonsproject.org/projects/pyramid/en/latest/api/decorator.html#pyramid.decorator.reify
    """
    def __init__(self, wrapped):
        self.wrapped = wrapped
        functools.update_wrapper(self, wrapped)

    def __get__(self, inst, objtype=None):
        if inst is None:
            return self
        val = self.wrapped(inst)
        setattr(inst, self.wrapped.__name__, val)
        return val


class Decoder:
    """Decoder class for our catalogue standards."""
    def __init__(self, profile, strip_func=None, fix_numerals=False,
                 spellcheck=False):
        """Initialize with a deserialized profile from deromanize"""
        self.profile = profile
        self.joined_prefix = trees.Trie(
            {i: i for i in profile['joined_prefixes']})
        self.prefix_vowels = set(profile['prefix_vowels']) | {''}
        self.gem_prefix = trees.Trie(
            {i: i for i in profile['gem_prefixes']})
        self.keys = deromanize.KeyGenerator(profile)
        self.num = fix_numerals
        self.sp = spellcheck
        self.w_kw = {'decoder': self, 'fix_numerals': self.num,
                     'spellcheck': self.sp}
        if strip_func:
            self.strip = strip_func
        else:
            self.strip = deromanize.stripper_factory(
                profile['vowels'].items(), profile['consonants'].items())

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
                    romed.append('-'.join(i.word for i in chunk))
                except AttributeError:
                    raise
            else:
                romed.append(str(chunk))
        return romed

    def make_chunks(self, line: str):
        cleaned_line = cleanline(line)
        raw_chunks = [i.split('-') for i in cleaned_line.split()]
        remixed = Chunks(self)
        for chunk in raw_chunks:
            if chunk == ['', '']:
                remixed.append('-')
                continue
            new_chunk = Chunk()
            for i, inner in enumerate(chunk[:-1]):
                if self.checkprefix(i, inner, chunk):
                    new_chunk.append(Prefix(inner, self))
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
        try:
            beginning, end = self.joined_prefix.getpart(part)
            if end in self.prefix_vowels:
                return True
            beginning, end = self.gem_prefix.getpart(part)
            _, nextp, _ = self.strip(chunk[i+1])
            if nextp.startswith(end):
                return True
            else:
                return False
        except KeyError:
            return False


def cleanline(line):
    line = line.lower()

    if line[0] == '@':
        line = line[1:]

    line = debracket(line)

    if '- ' in line:
        line = re.sub(r'(\w)- +([^@])', r'\1-\2', line)
    if ' -' in line:
        line = re.sub(r' -(\w)', r'-\1', line)
    if line.startswith('ha'):
        line = re.sub('^ha\w{0,2}- *@', 'h @', line)

    line = re.sub(r'\b([blw])([î]-|-[iî])', r'\1i-yĕ', line)

    return line


def debracket(line):
    # # bracket shenanigans # #
    rebracket = False
    if line[0] == '[' and line[-1] == ']' and ']' not in line[:-1]:
        line = line[1:-1]
        rebracket = True
    if '[' in line:
        line = re.sub(r'\[.*?\]', '', line)
    if rebracket:
        line = '[' + line + ']'
    line = remove_combining(line)
    return line


def remove_combining(line):
    new_line = []
    for c in line:
        if unicodedata.category(c) != 'Mn':
            new_line.append(c)
    return ''.join(new_line)


class Word:
    def __init__(self, word, decoder, fix_numerals=False, spellcheck=False):
        self.word = word
        self.split = decoder.strip(word)
        self.keys = decoder.keys
        self.num = fix_numerals
        self.sp = spellcheck

    @reify
    def stripped_heb(self):
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
        return word

    @reify
    def heb(self):
        front, rom, back = self.split
        word = self.stripped_heb
        if word is None:
            return
        if front:
            word = get_self_rep(front) + word
        if back:
            word = word + get_self_rep(back)
        return word

    def __repr__(self):
        return "Word({!r})".format(self.word)


class Prefix(Word):

    @reify
    def stripped_heb(self):
        front, rom, back = self.split
        word, remainder = self.keys['front'].getpart(rom)
        # work on a copy because we're going to modify the object's state
        word = word.copy()
        rep = deromanize.Replacement
        key = word.key + remainder[0:1]
        w = word[0]
        word.data = [rep(w.weight, str(w), key) + rep(0, '', '-')]
        return word

    def __repr__(self):
        return "Prefix({!r})".format(self.word)


class LinkedReplist(collections.UserList):
    def __init__(self, *linked):
        self.data = linked[0]
        self.linked = linked

    def __repr__(self):
        return ('LinkedReplist(' +
                ', '.join(repr(i) for i in self.linked) +
                ')')

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
            tuple(rlist[index] for rlist in self.linked)

    @reify
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

    def replist_gen(self, strip=False):
        prefix = self.prefix_gen(strip)
        if strip:
            he = self.data[-1].stripped_heb
        else:
            he = self.data[-1].heb

        if prefix:
            he = hyphenate(he)
        return prefix + he

    def prefix_gen(self, strip=False):
        return deromanize.add_reps(
            [i.stripped_heb if strip else i.heb
             for i in self.data[:-1]])

    def __repr__(self):
        return 'Chunk({!r})'.format(self.data)

    @reify
    @functools.lru_cache(2**10)
    def stripped_heb(self):
        return self.replist_gen(strip=True)

    @reify
    @functools.lru_cache(2**10)
    def heb(self):
        return self.replist_gen(strip=False)

    @reify
    @functools.lru_cache(2**10)
    def linked_heb(self):
        return LinkedReplist(
            self.stripped_heb, self.heb, self[-1].stripped_heb)

    def groups(self):
        return self.linked_heb.groups()

    def get_selected_pair(self, selected):
        for i, rep in enumerate(self.stripped_heb):
            if str(rep) == selected:
                break
        full = self.heb[i]
        base = self.data[-1].stripped_heb[i]
        return base, full

    def get_match(self, word):
        return self.linked_heb.head_dict[word]

    def __hash__(self):
        return hash(tuple(self.data))


def hyphenate(rep):
    rep = rep.copy()
    for i in range(len(rep)):
        if rep.key == str(rep[i]) and rep.key != '':
            rep.keyparts = ('-', rep.key)
            rep.key = '-' + str(rep.key)
            rep[i] = (
                deromanize.Replacement(0, '-', '')
                +
                deromanize.Replacement(
                    rep[i].weight,  str(rep[i]), str(rep[i]))
            )
    return rep


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
                if dec.sp == 'double':
                    double_check_spelling(hebz[-1], dec.strip)
            elif chunk is maqef:
                if not strip:
                    hebz.append(chunk)
            else:
                hebz.append(get_self_rep(chunk))
        return hebz

    @reify
    def stripped_heb(self):
        return self.get_heb(strip=True)

    @reify
    def heb(self):
        return self.get_heb(strip=False)

    @reify
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
                stripped, full, base = chunk.get_match(
                    curword)[word_counts[curword]][1]
                word_counts[curword] += 1

                reps.append(full)
                cacheable.append(base)
            elif chunk is maqef:
                reps.append(chunk)
            else:
                reps.append(get_self_rep(chunk))

        return reps, cacheable, list(word_iter)


def coredecode(keys, word, spellcheck=False):
    if word == '':
        return get_self_rep(word)
    # add aleph to words that begin with vowels.
    vowels = keys.profile['vowels']
    if word[0] in vowels:
        word = 'ʾ' + word
    # remove doubled letters
    newword = word[0]
    for i, c in enumerate(word[1:]):
        i += 1
        if c in vowels and word[i-1] in vowels:
            newword += "'" + c
        elif c != word[i-1]:
            newword += c
    replist = deromanize.front_mid_end_decode(keys, newword)
    if spellcheck:
        for i in replist:
            if not (hspell.check_word(str(i)) and hspell.linginfo(str(i))):
                i.weight += 200
    replist.prune()
    return replist


def fix_numerals(int_str, gershayim=False):
    front, num, back = num_strip(int_str)
    length = len(num)
    if length > 3:
        if num[0] == '5':
            num = num[1:]
        else:
            return get_self_rep(int_str)

    try:
        heb = hebrew_numbers.int_to_gematria(num)
    except KeyError:
        return get_self_rep(int_str)

    if not gershayim:
        heb = heb.replace('״', '"')
    if length >= 3:
        return keygenerator.ReplacementList(
            int_str, [front+heb+back, int_str])
    else:
        return keygenerator.ReplacementList(
            int_str, [int_str, front+heb+back])


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


num_strip = deromanize.stripper_factory(('0123456789',))
maqef = keygenerator.ReplacementList('-', ['־'])
maqef.heb = maqef
maqef.stripped_heb = get_self_rep('')
maqef.word = '-'
