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

    @property
    def joined(self):
        out = [decode.debracket(self.maintitle, rebracket=False)]
        if self.subtitle:
            out.extend((":", decode.debracket(self.subtitle, rebracket=False)))
        if self.responsibility:
            out.extend(
                ("/", decode.debracket(self.responsibility, rebracket=False))
            )
        return " ".join(out)

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
        out = []
        if maintitle:
            out.append(maintitle)
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


def has_hebrew(record):
    lang = record.get("021A", "U")
    return lang and "Hebr" in lang


def needs_conversion(record):
    if record is None:
        return False
    title = record.get("021A")
    if not title or has_hebrew(record):
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


def getpossiblenames(record, namedb):
    nameppns = getnameppns(record)

    def iternames():
        for ppn in nameppns:
            namesdict = namedb.get(ppn)
            if namesdict:
                for names in namesdict.values():
                    yield from names

    return set(n.lower() for n in iternames())


def getdocyears(datestrings):
    for datestring in datestrings:
        for year in dt.date2years(datestring):
            yield from dt.yearnorm(year)


namestarts = "028 055".split()


def getnamesfromwork(record):
    namefields = []
    for key in record.dict:
        if key[:3] in namestarts:
            namefields.append(key)

    return sortedfromfields(record, namefields)


def getnames(record, picanames):
    ppns = set(getnameppns(record))
    if not ppns:
        return [getnamesfromwork(record)]

    names = []
    for ppn in ppns:
        try:
            authrecord = picanames[ppn]
        except KeyError:
            continue

        transnames, othernames = getsortednames(authrecord)
        if not transnames and not othernames:
            continue
        names.append((transnames, othernames))
    if names:
        return names
    return [getnamesfromwork(record)]


def prerank(chunks, session):
    return session.usecache(chunks, dictionary=session.termdict)


def isconverted(record):
    for sf in record.get("047A", "r", []):
        if sf == "Originalschrift durch autom. Retrokonversion":
            return True
    return False


def getnamecomponents(record, session):
    allnames = getnames(record)
    output = set()
    for transnames, nontrans in allnames:
        for ln, fn in [*transnames, *nontrans]:
            output.update(ln.split())
            if fn:
                output.update(fn.split())
        for pair in transnames:
            for name in pair:
                if name:
                    chunks = session.getchunks(name)
                    rlists = prerank(chunks)
                    output.update(str(rep) for rl in rlists for rep in rl)
    output.discard("-")
    output.discard("בן")
    return output
