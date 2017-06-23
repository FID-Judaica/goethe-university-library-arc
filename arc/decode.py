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
import functools
import deromanize
from deromanize import trees, keygenerator
from HspellPy import Hspell
import hebrew_numbers


class reify:
    """ Use as a class method decorator.  It operates almost exactly like the
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


# deromanizing in involves doing special stuff at the start and end of the
# word. The punctuation marks (obviously screw this up. Originally, these four
# functions where just going to be one decorator (junk_splitter), but I would
# have had to rewrite the whole program, so I made some other helper functions.
# I probably should rewrite the whole program, but, eh, works good.
#
# Also note: leading and trailing non-transliteration characters are referred
# to as "junk". Sorry.
def junker(word):
    '''remove non-character symbols from the front of a word. return a tuple
    containing the junk from the front, and the remainder of the word.'''
    junk = []
    remainder = ''
    for i, char in enumerate(word):
        if unicodedata.category(char)[0] == 'L' or char == "'":
            remainder = word[i:]
            break
        junk.append(char)
        # if junk[-1] == "'":
        #     del junk[-1]
        #     remainder = "'" + remainder

    return (''.join(junk), remainder) if remainder else ('', ''.join(junk))


def double_junker(word):
    '''strip non-character symbols off the front and back of a word. return a
    tuple with (extra stuff from the front, word, extra stuff from the back)'''
    front_junk, remainder = junker(word)
    back_junk, stripped_word = [i[::-1] for i in junker(remainder[::-1])]
    return front_junk, stripped_word, back_junk
###########################


class Decoder:
    """Decoder class for our catalogue standards."""
    def __init__(self, profile):
        """Initialize with a deserialized profile from deromanize"""
        self.profile = profile
        self.joinedpfx = trees.Trie(
            {i: i for i in profile['joined_prefixes']})
        self.pfxvowels = set(profile['prefix_vowels']) | {''}
        self.gempfx = trees.Trie(
            {i: i for i in profile['gem_prefixes']})
        self.keys = deromanize.KeyGenerator(profile)

    def __getitem__(self, key):
        return self.profile[key]

    def decode(self, line):
        """Return a list of Word instances from a given line of input."""
        chunks = self.makechunks(line)
        return self.get_heb(chunks)

    def get_heb(self, chunks):
        hebz = []
        for chunk in chunks:
            if isinstance(chunk, list):
                if len(chunk) > 1:
                    he = chunk[-1].heb
                    if he.key == str(he[0]) and he.key != '':
                        chunk[-1].heb = get_self_rep('-' + str(he[0]))
                hebz.append(deromanize.add_reps([i.heb for i in chunk]))
                # double_check_spelling(hebz[-1])
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

    def makechunks(self, line):
        cleanedline = self.cleanline(line)
        rawchuncks = [i.split('-') for i in cleanedline.split()]
        remixed = []
        newchunk = []
        for chunk in rawchuncks:
            newchunk = []
            if chunk == ['', '']:
                remixed.append('-')
                continue
            for i, inner in enumerate(chunk[:-1]):
                if self.checkprefix(i, inner, chunk):
                    newchunk.append(Prefix(inner, self.keys))
                else:
                    newchunk.append(Word(inner, self.keys))
                    remixed.extend([newchunk, [maqef]])
                    newchunk = []
            if newchunk:
                newchunk.append(Word(chunk[-1], self.keys))
                remixed.append(newchunk)
            else:
                remixed.append([Word(chunk[-1], self.keys)])
        return remixed

    def checkprefix(self, i, inner, chunk):
        front, part, back = double_junker(inner)
        try:
            beginning, end = self.joinedpfx.getpart(part)
            if end in self.pfxvowels:
                return True
            beginning, end = self.gempfx.getpart(part)
            _, nextp, _ = double_junker(chunk[i+1])
            if nextp.startswith(end):
                return True
            else:
                return False
        except KeyError:
            return False

    def cleanline(self, line):
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
        return line


class Word:
    def __init__(self, word, keys):
        self.word = word
        self.junked = double_junker(word)
        self.keys = keys

    @reify
    def heb(self):
        front, rom, back = self.junked
        try:
            word = coredecode(self.keys, rom)
        except KeyError:
            try:
                word = fix_numerals(rom)
            except ValueError:
                word = get_self_rep(self.word)
        except IndexError:
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
    def heb(self):
        front, rom, back = self.junked
        if rom in u:
            word = keygenerator.ReplacementList(rom, ['ו'])
        else:
            word = self.keys['front'][rom[0]]

        if front:
            word = get_self_rep(front) + word
        if back:
            word += get_self_rep(back)
        return word

    def __repr__(self):
        return "Prefix({!r})".format(self.word)


def coredecode(keys, word):
    if word == '':
        return get_self_rep(word)
    replist = _coredecode(keys, word)
    for i in replist:
        _, core, _ = double_junker(str(i))
        if hspell.check_word(core) and hspell.linginfo(core):
            i.weight -= 1000
    replist.prune()
    return replist


def _coredecode(keys, word):
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
    word = newword
    # get ending clusters, then beginning clusters, then whatever's left in the
    # middle.
    end, remainder = keys['end'].getpart(word)
    if remainder:
        try:
            front, remainder = keys['front'].getpart(remainder)
        except KeyError:
            return no_end(keys, word)
    else:
        return no_end(keys, word)

    if remainder:
        middle = keys['mid'].getallparts(remainder).add()
        return (front + middle + end)
    else:
        return (front + end)


def no_end(keys, word):
    # this is where words go when getting the ending first produces strange
    # results.
    front, remainder = keys['front'].getpart(word)
    if remainder:
        end, remainder = keys['end'].getpart(remainder)
        if remainder:
            middle = keys['mid'].getallparts(remainder).add()
            return (front + middle + end)
        else:
            return (front + end)
    else:
        return (front)


def get_self_rep(string):
    return keygenerator.ReplacementList(string, [string])


def fix_numerals(int_str):
    length = len(int_str)
    if length > 3:
        return get_self_rep(int_str)
    else:
        heb = hebrew_numbers.int_to_gematria(int_str)
        if length == 3:
            return keygenerator.ReplacementList(int_str, [heb, int_str])
        else:
            return keygenerator.ReplacementList(int_str, [int_str, heb])


def double_check_spelling(replist):
    for rep in replist:
        if rep.weight < 0:
            _, core, _ = double_junker(str(rep))
            try:
                if not hspell.check_word(core):
                    rep.weight += 1000
            except UnicodeEncodeError:
                pass
        else:
            break
    replist.sort()


maqef = keygenerator.ReplacementList('-', ['־'])
maqef.heb = maqef
maqef.word = '-'
u = {'û', 'u'}
hspell = Hspell(linguistics=True)
