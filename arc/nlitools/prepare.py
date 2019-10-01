import re
from functools import partial
import libaaron

DONT_COUNT = re.compile(r"^<<(.*?)>> *")
HEB = r"אבגדהוזחטיכךלמםנןסעפףצץקרשת"
MAQEF = re.compile(r"(?<=[" + HEB + r"])-(?=[" + HEB + "])")
GERSHAYIM = re.compile(r"(?<=[" + HEB + r'])"(?=[' + HEB + "])")
GERESH = re.compile(
    r"(?<=[" + HEB + r"])'(?=[" + HEB + r"])" r"|(?<=\b[" + HEB + r"])'(?=\s|$)"
)
QUOTED = re.compile(
    r'(?<=")((?:['
    + HEB
    + r"]{2}|["
    + HEB
    + r']"['
    + HEB
    + "]|[^"
    + HEB
    + r']).*?)(?="(?:[^'
    + HEB
    + "]|$))"
)
SING_QUOTED = re.compile(QUOTED.pattern.replace('"', "'"))
MAGIC_WORDS = {"סיפורים", "שירים", "רומן"}
NUM_RANGE = re.compile(r"\b(\d+)-(\d+)\b")


def num_swap(match):
    first = match.group(1)
    second = match.group(2)
    if int(first) > int(second):
        first, second = second, first

    return first + " - " + second


def make_distinguisher(quoted, punct_re, punct):
    def distinguisher(string):
        slist = quoted.split(string)
        new_string = ""
        for p in slist:
            new_string += punct_re.sub(punct, p)
        return new_string

    return distinguisher


add_gershayim = make_distinguisher(QUOTED, GERSHAYIM, "״")
add_geresh = make_distinguisher(
    re.compile(QUOTED.pattern.replace('"', "'")), GERESH, "׳"
)


def fix_nli_format(text):
    return libaaron.pipe(
        text,
        partial(DONT_COUNT.sub, r"\1 @"),
        add_gershayim,
        partial(NUM_RANGE.sub, num_swap),
        lambda s: s.replace("<", "(").replace(">", ")"),
    )
