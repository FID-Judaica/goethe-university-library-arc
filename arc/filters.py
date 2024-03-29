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
import string
import filtermaker

# # Data Definitions # #
# common words and chars in other languages which should not appear in Hebrew.

# matches normally quoted words or phrases
SING_QUOTE = r"(\W|^)'\w.*?[\w.]'(\W|$)"
DUB_QUOTE = r'(\W|^)"\w.*?[\w.]"(\W|$)'


OLD_CHARS = set("ʾʿăaāâbdĕeěēêfghḥiīîjkḵlmnŏoōôpqrsṣśštṯṭuūûvwyzʻ")
PI_CHARS = set("ʾʿaābdeēfghḥiījkḵlmnoōpqrsṣśštṯṭuūvwyz")
NEW_CHARS = set("ʾʿabdefghḥikḳlmnoprsśtṭuvṿyzʻ")
HEB_CHARS = set("אב‎ג‎ד‎ה‎ו‎ז‎ח‎ט‎י‎כ‎ך‎ל‎מ‎נ‎ס‎ע‎פ‎צ‎ק‎ר‎ש‎ת‎ם‎ן‎ף‎ץ‎")

# all characters possible in transliteration
ALL_CHARS = NEW_CHARS | OLD_CHARS

# all transliteration character which are not in ascii
ALL_SPECIAL = ALL_CHARS - set(string.ascii_lowercase)
SPECIAL_NO_CIRCUMFLEX = ALL_SPECIAL - set("âêîôû")
EXCLUSIVE_TO_OLD = OLD_CHARS - NEW_CHARS
EXCLUSIVE_TO_NEW = NEW_CHARS - OLD_CHARS

VOWEL_SET = set("ăaāâĕeēêiîŏoōôuû")
DIACRITIC_VOWELS = VOWEL_SET - set("aeiou")
CONSONANT_SET = ALL_CHARS - VOWEL_SET
CONSONANTS = "".join(CONSONANT_SET)

NEW_DIGRAPHS = {"kh", "sh", "ts"}
UNDIGRAPHS = {"k'h", "s'h", "t's", "tʹs", "kʹh", "sʹh"}

# ō should only appear at the ends of words or in personal names. It's not
# illegal, but it's very suspicious. short /u/ is also suspicious.
SHORT_U = "u"
UNMARKED_LONG_O = r"ō\w"

NON_HEB = r"""(?x)
    # search certain words
    \b
    (a|der|di|des|de|dos|das|dem|in|der|zi|von|
     zî|fun|fir|fûn|il|of|and|und|un|tsu|zu|ṣu)\b |
    # search letters/clusters which should not appear in hebrew transliteration

    \bth|au|ao|ae|aa|oe|pf|
    ou|eu|ue|oo|ee|uo|eo|io|oi|ui|iu|[üäëöïáéàèíßçcx]
    """
YIDDISH_ENDING = "[" + "".join(CONSONANT_SET - {"y"}) + r"]n(\s|$)"
ENGLISH_Y = "[" + CONSONANTS + r"]y(\s|$)"
ARABIC_ARTICLE = r"(\W|^)al-[^p]"
LONG_IN_CLOSED = "[îīûūôōêē][" + CONSONANTS + "]{2}"


# # The actual tests that are used on the line # #
fs = filtermaker.get_filterspace()

fs.haschars(ALL_SPECIAL, "transliteration")
fs.haschars(SPECIAL_NO_CIRCUMFLEX, "trans_no_circum")
fs.haschars(EXCLUSIVE_TO_OLD, "old")
fs.haschars(EXCLUSIVE_TO_NEW, "new")
fs.haschars(HEB_CHARS, "heb")
fs.haschars(SHORT_U, "short_u")
fs.haschars(DIACRITIC_VOWELS, "diacritic_vowels")
fs.haschars(string.ascii_letters, "ascii_letters")

fs.hascluster(NEW_DIGRAPHS, "new_digraphs")
fs.hascluster(UNDIGRAPHS, "undigraphs")

fs.onlycharset(OLD_CHARS, "only_old"),
fs.onlycharset(NEW_CHARS, "only_new")
fs.onlycharset(PI_CHARS, "only_pi")
fs.onlycharset(HEB_CHARS, "only_heb")

fs.hasregex(NON_HEB, "foreign")
fs.hasregex(YIDDISH_ENDING, "yiddish_ending")
fs.hasregex(ARABIC_ARTICLE, "arabic_article")
fs.hasregex(ENGLISH_Y, "english_y")


@fs.register
def inner_sing_quote(line):
    return "'" in line.data and not SING_QUOTE.search(line.data)


@fs.register
def inner_dub_quote(line):
    return '"' in line.data and not DUB_QUOTE.search(line.data)


@fs.register
def unmarked_long_o(line):
    proper = any(i in line for i in ("lōmō", "yaʿaqōv", "kōl", "mōš"))
    return not proper and UNMARKED_LONG_O.search(line.data)


@fs.register
def only_western(line):
    return all(ord(c) < 256 for c in line.data)


@fs.register
def longinclosed(line):
    for m in LONG_IN_CLOSED.findall(line.data):
        if m[-1] != m[-2]:
            return True


Line = fs.Filter

# new API
from filtermaker import chainable
import re


class TrascriptionText(chainable.PropertyText):
    __slots__ = ()
    transliteration = chainable.haschars(ALL_SPECIAL)
    trans_no_circum = chainable.haschars(SPECIAL_NO_CIRCUMFLEX)
    old = chainable.haschars(EXCLUSIVE_TO_OLD)
    new_chars = chainable.haschars(EXCLUSIVE_TO_NEW)
    heb = chainable.haschars(HEB_CHARS)
    short_u = chainable.haschars(SHORT_U)
    diacritic_vowels = chainable.haschars(DIACRITIC_VOWELS)
    ascii_letters = chainable.haschars(string.ascii_letters)

    new_digraphs = chainable.hascluster(NEW_DIGRAPHS)
    undigraphs = chainable.hascluster(UNDIGRAPHS)

    only_old = chainable.onlycharset(OLD_CHARS)
    only_new = chainable.onlycharset(NEW_CHARS)
    only_pi = chainable.onlycharset(PI_CHARS)
    only_heb = chainable.onlycharset(HEB_CHARS)

    foreign = chainable.hasregex(re.compile(NON_HEB))
    yiddish_ending = chainable.hasregex(re.compile(YIDDISH_ENDING))
    arabic_article = chainable.hasregex(re.compile(ARABIC_ARTICLE))
    english_y = chainable.hasregex(re.compile(ENGLISH_Y))

    @chainable.chainable
    def inner_sing_quote(text):
        return "'" in text and not SING_QUOTE.search(text)

    @chainable.chainable
    def inner_dub_quote(text):
        return '"' in text and not DUB_QUOTE.search(text)

    @chainable.chainable
    def unmarked_long_o(text):
        proper = any(i in text for i in ("lōmō", "yaʿaqōv", "kōl", "mōš"))
        return not proper and UNMARKED_LONG_O.search(text)

    @chainable.chainable
    def only_western(text):
        return all(ord(c) < 256 for c in text)

    @chainable.chainable
    def longinclosed(text):
        for m in LONG_IN_CLOSED.findall(text):
            if m[-1] != m[-2]:
                return True


###################################################################
# # Here ends the library part. The rest is for the CLI utility # #
###################################################################


DESCRIPTION = """\
Filter input lines by properties (character sets and combinations):

\t%s


* "bad" is a list of characters that frequently appear in the
transliteration but aren't part of the standard. "undigraphs" are some
character combinations that the new standard uses to keep from
representing digraphs\
""" % "\n\t".join(
    sorted(fs._tests)
)


class NameSpace(dict):
    "namespace that imports modules lazily."

    def __missing__(self, name):
        return __import__(name)


def tester_maker(expression=None, namespace=None):
    if expression:
        expr = compile(expression, "string", "eval")
        namespace = NameSpace()
        namespace.update(__builtins__)

    def with_expression(line, required, forbidden):
        namespace["line"] = line
        if required and not all(line.has(i) for i in required):
            return False

        if forbidden and any(line.has(i) for i in forbidden):
            return False

        if not eval(expr, namespace):
            return False

        return True

    def no_expression(line, required, forbidden):
        if required and not all(line.has(i) for i in required):
            return False

        if forbidden and any(line.has(i) for i in forbidden):
            return False

        return True

    return with_expression if expression else no_expression


def main():
    import pica_parse
    import sys
    import argparse

    ap = argparse.ArgumentParser(
        description=DESCRIPTION,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    add = ap.add_argument
    add(
        "-r",
        "--required",
        default="",
        help="comma-separated list of properties",
    )

    add(
        "-f",
        "--forbidden",
        default="",
        help="comma-separated list of properties to exclude",
    )

    add(
        "-e",
        "--expression",
        help="a python expression which must evaluate to True in a boolean "
        "context for the line to print. current line can be accessed with the "
        "name `line`",
    )

    args = ap.parse_args()
    required = set(args.required.split(",")) - {""}
    forbidden = set(args.forbidden.split(",")) - {""}
    props = required | forbidden

    test = tester_maker(args.expression)
    for rec in pica_parse.file2records(sys.stdin):
        fields_of_interest = []
        for field in rec:
            for key, text in field.items():
                if test(Line(text, *props), required, forbidden):
                    fields_of_interest.append("{}.{}: {}".format(field.id, key, text))
        if fields_of_interest:
            print(rec.ppn, *fields_of_interest, sep="\t")

    # if args.pica:
    #     for record in pica_parse.file2records(sys.stdin):
    #         d = {'ppn': record.ppn}
    #         heb = {}
    #         for field in record:
    #             if field.id in d:
    #                 if field.get('U') == 'Hebr':
    #                     del field.dict['U']
    #                     heb[field.id] = {k: v[0] for k, v
    #                                      in field.dict.items()}
    #                 else:
    #                     continue
    #             else:
    #                 for k, sub in field.items():
    #                     if test(Line(sub, *props), required, forbidden):
    #                         d.setdefault(field.id, {})[k] = sub

    #         if len(d) > 1:
    #             print(json.dumps(d, ensure_ascii=False))
    # else:
    #     for line in (Line(l.rstrip(), *props) for l in sys.stdin):
    #         if test(line, required, forbidden):
    #             print(line)
