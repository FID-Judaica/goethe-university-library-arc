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
import functools
import deromanize
from deromanize import trees, keygenerator, get_self_rep
try:
    from HspellPy import Hspell
    hspell = Hspell(linguistics=True)
except ImportError:
    hspell = None
import hebrew_numbers


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

    def decode(self, line, stripped=False):
        """Return a list of Word instances from a given line of input."""
        chunks = self.make_chunks(line)
        return self.get_heb(chunks, stripped=stripped)

    def get_heb(self, chunks, stripped=False):
        hebz = []
        for chunk in chunks:
            if isinstance(chunk, list):
                if len(chunk) > 1:
                    if stripped:
                        he = chunk[-1].stripped_heb
                    else:
                        he = chunk[-1].heb
                        for i in range(len(he)):
                            if he.key == str(he[i]) and he.key != '':
                                he.keyparts = ('-', he.key)
                                he.key = '-' + str(he.key)
                                he[i] = (
                                    deromanize.Replacement(0, '-', '')
                                    +
                                    deromanize.Replacement(
                                        he[i].weight,  str(he[i]), str(he[i]))
                                )
                elif stripped and chunk[0] == maqef:
                    continue
                hebz.append(deromanize.add_reps(
                    [i.stripped_heb if stripped else i.heb for i in chunk]))
                if self.sp == 'double':
                    double_check_spelling(hebz[-1], self.strip)
            else:
                hebz.append(get_self_rep(chunk))
        return hebz

    def get_rom(self, chunks):
        romed = []
        for chunk in chunks:
            if isinstance(chunk, list):
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
        remixed = []
        for chunk in raw_chunks:
            new_chunk = []
            if chunk == ['', '']:
                remixed.append('-')
                continue
            for i, inner in enumerate(chunk[:-1]):
                if self.checkprefix(i, inner, chunk):
                    new_chunk.append(Prefix(inner, self))
                else:
                    new_chunk.append(Word(inner, **self.w_kw))
                    remixed.extend([new_chunk, [maqef]])
                    new_chunk = []
            if new_chunk:
                new_chunk.append(Word(chunk[-1], **self.w_kw))
                remixed.append(new_chunk)
            else:
                remixed.append([Word(chunk[-1], **self.w_kw)])
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

    # # bracket shenanigans # #
    rebracket = False
    if line[0] == '[' and line[-1] == ']' and ']' not in line[:-1]:
        line = line[1:-1]
        rebracket = True
    if '[' in line:
        line = re.sub(r'\[.*?\]', '', line)
    if rebracket:
        line = '[' + line + ']'
    if '- ' in line:
        line = re.sub(r'(\w)- +([^@])', r'\1-\2', line)
    if ' -' in line:
        line = re.sub(r' -(\w)', r'-\1', line)
    if line.startswith('ha'):
        line = re.sub('^ha\w{0,2}- *@', 'h @', line)

    line = re.sub(r'\b([blw])([î]-|-[iî])', r'\1i-yĕ', line)

    return line


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
            checkable = str(i).replace('״', '"').replace('׳', "'")
            if not (hspell.check_word(checkable) and hspell.linginfo(
                    checkable)):
                i.weight += 200
    replist.prune()
    return replist


def fix_numerals(int_str):
    front, num, back = num_strip(int_str)
    length = len(num)
    if length > 3:
        if num[0] == '5':
            num = num[1:]
        else:
            return get_self_rep(int_str)

    heb = hebrew_numbers.int_to_gematria(num)
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
u = {'û', 'u'}
