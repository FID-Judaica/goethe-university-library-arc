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
        if unicodedata.category(char)[0] == 'L':
            remainder = word[i:]
            break
        junk.append(char)
        if junk[-1] == "'":
            del junk[-1]
            remainder = "'" + remainder

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
        return [deromanize.add_reps([i.heb for i in chunk])
                if isinstance(chunk, list) else get_self_rep(chunk)
                for chunk in chunks]

    def get_rom(self, chunks):
        romed = []
        for chunk in chunks:
            if isinstance(chunk, list):
                try:
                    romed.append('-'.join(i.word for i in chunk))
                except AttributeError:
                    print(chunks)
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
            return get_self_rep(self.word)
        except IndexError:
            return
        if front:
            word = get_self_rep(front) + word
        if back:
            word = word + get_self_rep(back)
        return word

    def __repr__(self):
        return f"Word({self.word!r})"


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
        return f"Prefix({self.word!r})"


def coredecode(keys, word):
    if word == '':
        return get_self_rep(word)
    replist = _coredecode(keys, word)
    for i in replist:
        if hspell.check_word(str(i)) and hspell.linginfo(str(i)):
            i.weight -= 1000
    replist.prune()
    return replist


def _coredecode(keys, word):
    # add aleph to words that begin with vowels.
    if word[0] in keys.profile['vowels']:
        word = 'ʾ' + word
    # remove doubled letters
    newword = ''
    for i, c in enumerate(word):
        if i == 0 or c != word[i-1]:
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


maqef = keygenerator.ReplacementList('-', ['־'])
maqef.heb = maqef
maqef.word = '-'
u = {'û', 'u'}
hspell = Hspell(linguistics=True)
