from . import filters
import typing as t

namefields = "028A 028@ 028P".split()


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


def getsortednames(record):
    names = []
    nottrans = []
    for field in namefields:
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


class Title(t.NamedTuple):
    maintitle: str
    subtitle: t.Union[str, None]
    responsibility: t.Union[str, None]


def gettitle(subs):
    return Title(*map(field.getone, "adh"))


def fields2transtitle(fields):
    for field in fields:
        if islatinfield(field):
            break
    return gettitle(fields)


def gettranstitle(record, fieldname="021A"):
    fields = record[fieldname]
    return fields2title(fields)
