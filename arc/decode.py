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
from functools import wraps
import deromanize
from deromanize import trees


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
        if unicodedata.category(char)[0] != 'L':
            remainder = word[i:]
            break
        junk.append(char)

    return (''.join(junk), remainder) if remainder else ('', ''.join(junk))


def double_junker(word):
    '''strip non-character symbols off the front and back of a word. return a
    tuple with (extra stuff from the front, word, extra stuff from the back)'''
    front_junk, remainder = junker(word)
    back_junk, stripped_word = [i[::-1] for i in junker(remainder[::-1])]
    return [front_junk, stripped_word, back_junk]


def junk_splitter(func):
    '''decorator to ignore punctuation before and after words'''
    @wraps(func)
    def split_func(word, *args, **kwargs):
        front_junk, stripped_word, back_junk = double_junker(word)
        if stripped_word:
            output = func(stripped_word, *args, **kwargs)
        else:
            output = ''

        return front_junk + output + back_junk

    return split_func

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
        cleanedline = self.cleanline(line)
        chunks = self.makechunks(cleanedline)

        return chunks

    def makechunks(self, line):
        rawchuncks = [i.split('-') for i in line.split()]
        remixed = []
        newchunk = []
        for chunk in rawchuncks:
            newchunk = []
            for i, inner in enumerate(chunk[:-1]):
                if self.checkprefix(i, inner, chunk):
                    newchunk.append(inner)
                else:
                    remixed.append(([inner, '-']))
            if newchunk:
                newchunk.append(chunk[-1])
                remixed.append(newchunk)
            else:
                remixed.append([chunk[-1]])
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

        return line
