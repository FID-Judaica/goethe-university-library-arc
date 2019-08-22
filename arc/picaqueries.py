from libaaron.libaaron import pipe, pmap, pfilter
import libaaron
from arc import decode
from . import filters
from . import dates as dt
import typing as t
import string

monograph = set("ac")
namefields = "028A 028@ 028P".split()

# dummy argument for a kwarg where None is a possible user-supplied value
noarg = object()


def getdates(record):
    try:
        dates = record["011@"]
    except KeyError:
        return
    for field in dates:
        yield from (val for _, val in field)


def getyears(record):
    dates = getdates(record)
    years = (n for date in dates for n in dt.date2years(date))
    return map(dt.yearnorm, years)


def getnameppns(record):
    output = []
    for fieldname in ("028A", "028C"):
        try:
            name = record[fieldname]
        except KeyError:
            continue

        for field in name:
            try:
                output.extend(field["9"])
            except KeyError:
                continue

    return output


def ismonograph(record):
    if record.getone("002@", "0")[1] in monograph:
        return True
    return False


def _hastranscription(text):
    line = filters.Line(text[0])
    if any(line.has(p) for p in ("foreign", "english_y")):
        return False
    if line.has("transliteration"):
        return True
    return False


def hastransciption(subs):
    for sn in "adP":
        content = subs.get(sn)
        if content and _hastranscription(content):
            return content
    return False


def islatinfield(subs):
    lang = subs.get("U")
    if lang is None or lang == "Latn":
        return True
    return False


def getnameparts(subs):
    nameparts = []
    last = subs.get("a")
    first = subs.get("d")
    if last:
        nameparts.append(last[0])
    if first:
        nameparts.append(first[0])
    if nameparts:
        if len(nameparts) == 1:
            nameparts.append("")
        return nameparts
    personal = subs.get("P")
    if personal:
        return (personal[0], "")


def getnames(record):
    for field in namefields:
        field = record.get(field)
        if field:
            yield from map(getnameparts, field)


def sortedfromfields(record, fieldnames):
    names = []
    nottrans = []
    for field in fieldnames:
        field = record.get(field)
        if field:
            for subs in field:
                if islatinfield(subs):
                    if hastransciption(subs):
                        names.append(subs)
                    else:
                        nottrans.append(subs)
    transnames = [getnameparts(n) for n in names]
    transnames = list(filter(None, transnames))
    othernames = [getnameparts(n) for n in nottrans]
    othernames = list(filter(None, othernames))
    return transnames, othernames


def getsortednames(record):
    return sortedfromfields(record, namefields)


class NoMainTitle(Exception):
    pass


class Title:
    __slots__ = "maintitle", "subtitle", "responsibility"
    maintitle: str
    subtitle: t.Union[str, None]
    responsibility: t.Union[str, None]

    def __init__(self, maintitle, subtitle, responsibility):
        """

        """
        if not isinstance(maintitle, str):
            raise NoMainTitle((maintitle, subtitle, responsibility))

        self.maintitle = maintitle
        self.subtitle = subtitle
        self.responsibility = responsibility

    def __repr__(self):
        return libaaron.getrepr(
            self, self.maintitle, self.subtitle, self.responsibility
        )

    def cleaned(self):
        for attr in (self.maintitle, self.subtitle, self.responsibility):
            if attr:
                stripped = (w.strip(string.punctuation) for w in attr.split())
                if not stripped:
                    yield None
                try:
                    yield decode.cleanline(" ".join(stripped))
                except IndexError:
                    yield None
            else:
                yield None

    @property
    def text(self):
        maintitle, subtitle, responsibility = self.cleaned()
        out = [maintitle]
        if subtitle:
            out.extend((":", subtitle))
        if responsibility:
            out.extend(("/", responsibility))
        return " ".join(out)

    @property
    def textonly(self):
        maintitle, subtitle, responsibility = self.cleaned()
        at = maintitle.find("@")
        if at != -1:
            if at < 3:
                maintitle = maintitle[: at - 1] + maintitle[at + 1 :]
            else:
                maintitle = maintitle.replace("@", "")
        out = [maintitle]
        if subtitle:
            out.append(subtitle)
        if responsibility:
            out.append(responsibility)
        return " ".join(out)


def gettitle(subs):
    return Title(*map(subs.getone, "adh"))


def fields2transtitle(fields):
    for field in fields:
        if islatinfield(field):
            try:
                return gettitle(field)
            except NoMainTitle:
                continue
    raise NoMainTitle(fields)


def gettranstitle(record, fieldname="021A"):
    fields = record[fieldname]
    return fields2transtitle(fields)


def gettitletext(titlefield):
    # can throw a MulipleFields exception.
    return " ".join(
        pipe((titlefield.getone(sf) for sf in "adh"), pfilter(None))
    )


BAD_PROPS = "foreign yiddish_ending english_y arabic_article".split()


def needs_conversion(record):
    if record is None:
        return False
    title = record.get("021A")
    if not title:
        return False
    lang = record.get("021A", "U")
    if lang and "Hebr" in lang:
        return False

    isforeign = pipe(
        map(gettitletext, title),
        pmap(filters.Line),
        pmap(lambda l: any(l.has(p) for p in BAD_PROPS)),
        list,
    )
    if all(isforeign):
        return False

    return True
