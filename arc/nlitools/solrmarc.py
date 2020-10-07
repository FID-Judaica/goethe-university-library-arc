from __future__ import annotations
import sys
import json
from arc import solrtools as st
from arc import picaqueries
import tornado
import typing as t
from libaaron import lxml_little_iter, pmap, pfilter, pipe
from arc.decode import debracket
from statistics import mean
import listdict
from arc import dates as dt
import Levenshtein
import deromanize
import string
from itertools import chain

from typing import Sequence, NamedTuple, Optional, Collection


ALT_NAMES = [
    ("020_a", "ISBN"),
    ("100_a", "name"),
    ("130_a", "uniformTitle"),
    ("245_a", "title"),
    ("245_b", "subtitle"),
    ("245_c", "responsibility"),
    ("246_a", "altTitle"),
    ("246_b", "altSubtitle"),
    ("260_a", "place"),
    ("260_b", "publisher"),
    ("260_c", "date"),
    ("400_a", "seriesPerson"),
    ("440_v", "oldVolume"),
    ("490_a", "series"),
    ("490_v", "volume"),
    ("700_a", "addedPerson"),
    ("751_a", "addedPlace"),
    ("830_a", "addedSeries"),
    # ('830_d', 'treatySigned'),
    ("830_v", "addedVolume"),
]
HEBFIELDS = [n[0] + "_txt" for n in ALT_NAMES]
NAMEDICT = {name: field for field, name in ALT_NAMES}


def getfield(name):
    return NAMEDICT.get(name, name) + "_txt"


TITLEFILEDS = [
    getfield(n)
    for n in (
        "uniformTitle",
        "title",
        "subtitle",
        "responsibility",
        "altTitle",
        "altSubtitle",
        "series",
        "addedSeries",
        "volume",
        "date",
        "oldVolume",
        "addedVolume",
    )
]
NAMEFIELDS = list(
    map(getfield, ["name", "responsibility", "seriesPerson", "addedPerson"])
)
NAMESPACE = "http://www.loc.gov/MARC21/slim"
NS_MAP = {"marc": NAMESPACE}
DATAFIELD = "{%s}datafield" % NAMESPACE
SUBFIELD = "{%s}subfield" % NAMESPACE
CONTROLFIELD = "{%s}controlfield" % NAMESPACE


def gettitle(doc):
    title = doc["245"][0]
    parts = (title.get(sf) for sf in ("a", "b", "c"))
    return [h[0] if h else h for h in parts]


def remove_ending(string):
    if not string:
        return string
    if string[-1] in ("/", ":"):
        return string[:-2]
    return string


def get_titles(doc):
    titles = doc.get("245", [])
    output = []
    for title in titles:
        parts = (title.get(sf) for sf in ("a", "b", "c"))

        output.append(
            picaqueries.Title(
                *(remove_ending(h[0]) if h else h for h in parts)
            )
        )
    return output


def get_names(doc):
    return doc.get("allnames", [])


def get_date(doc):
    out = []
    for field in doc.get("260", []):
        for sb in field.get("c", []):
            out.append(sb)
    return out


class NoIdentifier(Exception):
    pass


def get_id(doc):
    try:
        return doc["controlfields"]["001"]
    except KeyError:
        raise NoIdentifier(doc["controlfields"])


def mk_api_doc(doc):
    return {
        "title": get_titles(doc),
        "creator": get_names(doc),
        "date": get_date(doc),
        "identifier": get_id(doc),
    }


def mkfield(fieldname, query):
    return st.mkfield(getfield(fieldname), query)


def distance_ratio(a: str, b: str):
    # return 1 - Levenshtein.jaro_winkler(a, b)
    distance = Levenshtein.distance(a, b)
    if distance == 0:
        return 0, 0.0
    return distance, (distance / len(a)) if len(a) else 1.0


def mkfieldquery(
    fieldname, terms, escape=True, fuzzy=False, exact=False, and_=False
):
    join = st.and_ if and_ else st.join
    searchterms = join(terms, escape, fuzzy, exact)
    return mkfield(fieldname, searchterms)


class NliCore(st.SolrCore):
    def fieldsearch(
        self,
        fieldname,
        terms,
        escape=True,
        fuzzy=False,
        exact=False,
        and_=False,
    ):
        query = mkfieldquery(fieldname, terms, escape, fuzzy, exact, and_)
        return self.run_query(query)

    def getfullnames(self, names):
        names = map(", ".join, filter(None, names))
        docs = self.run_query(
            st.mkfield("allnames", st.join(names, True, False, True))
        )["docs"]

        out = {}
        for doc in docs:
            found = []
            for field in NAMEFIELDS:
                found += doc.get(field, [])
            out[doc["001_txt"].pop()] = found

        return out


class NliAsyncCore:
    _rsess = None

    @property
    def rsess(self):
        s = getattr(self, "_rsess", None)
        if not s:
            s = self._rsess = tornado.httpclient.AsyncHTTPClient()
        return s

    def __init__(self, url):
        """object for querying Solr that contains the core URL and a
        requests.Session for http.
        """
        self.url = url.rstrip("/")
        self.session = self.rsess

    # note that run_query_async returns an awaitable object.
    def run_query(self, query: str, fl=None, **kwargs) -> t.Awaitable[dict]:
        return st.run_query_async(
            self.url, self.session, query, fl=fl, **kwargs
        )

    # therefore, fieldsearch will also return an awaitable object.
    fieldsearch = NliCore.fieldsearch


def iter_record(record: dict) -> t.Iterator[t.Tuple[str, str, str]]:
    return listdict.iter(record, depth=1)


def rename_field(obj, old_name, new_name):
    try:
        obj[new_name] = obj.pop(old_name)
    except KeyError:
        pass


def marcfieldsplit(f):
    return f.attrib["tag"], f.findall(SUBFIELD)


def marcsubsplit(subf):
    return subf.attrib["code"], subf.text or ""


def record2dict(record):
    _, record = record
    datafields = record.findall(DATAFIELD)
    dct = listdict.mk(datafields, marcfieldsplit, marcsubsplit)
    dct["controlfields"] = controlfields = {}
    for elem in record.findall(CONTROLFIELD):
        controlfields[elem.attrib["tag"]] = elem.text
    return dct


def marcxml2dicts(xmlpath: str) -> t.Iterator[dict]:
    """take path to MARC21 XML file and yield a their content as a
    dictionaries of lists of dictionaries of lists.
    """
    tag = "{%s}record" % NAMESPACE
    records = lxml_little_iter(xmlpath, tag=tag)
    return map(record2dict, records)


def marcdict2doc(record: dict) -> dict:
    """turn MARC dictionaries generated by marcxml2dicts into solr
    documents.
    """
    new = {k + "_txt": v for k, v in record.pop("controlfields").items()}
    for fname, fields in record.items():
        subfieldset = set()
        for field in fields:
            subfieldset.update(field)
        for subname in sorted(subfieldset):
            subfieldlist = []
            for field in fields:
                subfieldlist.extend(field.get(subname, [""]))

            subfields = map(st.strip_gross_chars, filter(None, subfieldlist))
            try:
                listdict.extend(
                    new, "{}_{}_txt".format(fname, subname), subfields
                )
            except AttributeError:
                print(fname, fields, file=sys.stderr)
                raise
    return new


def marcxml2solr(xmlpath):
    return map(marcdict2doc, marcxml2dicts(xmlpath))


def solrdocgen():
    encode = json.JSONEncoder(ensure_ascii=False).encode
    (xml,) = sys.argv[1:]
    docs = marcxml2solr(xml)
    for doc in docs:
        print(encode(doc))


def getqueryparts(rlist):
    top3 = [s.replace("-", "") for s in map(str, rlist[:5])]
    return st.or_(filter(None, top3), fuzzy=True)


def map_n_filter_queryparts(rlists):
    for rlist in rlists:
        try:
            yield getqueryparts(rlist)
        except st.QueryError:
            pass


def getdocs(query, nlibooks):
    try:
        return nlibooks.run_query("alltitles:" + query)["docs"]
    except st.QueryError as e:
        print(e.args[0])
        raise Exception()


def getdocyears(datestrings):
    for datestring in datestrings:
        for year in dt.date2years(datestring):
            yield from dt.yearnorm(year)


def split_no_punctuation(string_):
    return pipe(
        string_.replace("-", " "),
        str.split,
        pmap(lambda s: s.strip(string.punctuation)),
        pfilter(None),
    )


def clean_nli_text(text):
    if not text:
        return text
    return pipe(
        text,
        debracket,
        lambda s: split_no_punctuation(s.replace(">>", "")),
        " ".join,
    )


def prepare_doctitle(doc):
    out = map(clean_nli_text, gettitle(doc))
    return " ".join(filter(None, out))


def prepare_api_doctitle(doc):
    title = doc["title"][0]
    out = map(
        clean_nli_text, (title.maintitle, title.subtitle, title.responsibility)
    )
    return " ".join(filter(None, out))


def gettopguess(nliwords, rlists):
    top_generated = []
    for rlist in rlists:
        for replacement in rlist:
            heb = str(replacement).strip(string.punctuation)
            if heb and heb in nliwords:
                top_generated.append(heb)
                break
        else:
            top_generated.append(str(rlist[0]).strip(string.punctuation))
    return [h for h in top_generated if h]


num_strip = deromanize.stripper_factory(string.digits)
TitleField = Optional[Sequence[Sequence[str]]]


class RepTitle(NamedTuple):
    main: TitleField
    sub: TitleField
    resp: TitleField


def rank_results(names, years, replists, results):
    names = set(names)
    years = set(years)
    matches = []
    for doc in results[:5]:
        excellent_match = False
        nli_stripped = prepare_doctitle(doc)
        nliwords = set(nli_stripped.split())
        topguess = " ".join(gettopguess(nliwords, replists))
        diff = distance_ratio(topguess, nli_stripped)
        if diff > 0.27:
            continue
        if diff < 0.02:
            excellent_match = True
        docnames = doc.get("allnames", [])
        shared_names = names.intersection(docnames)
        if not shared_names and not excellent_match:
            continue
        docdate = doc.get(getfield("date"), [])
        docdates = [num_strip(d)[1] for d in docdate]
        shared_dates = years.intersection(docdates)
        if not shared_dates and not excellent_match:
            continue
        matches.append(
            {
                "doc": doc,
                "diff": diff,
                "dates": list(shared_dates),
                "names": list(shared_names),
            }
        )

    matches.sort(key=lambda m: m["diff"], reverse=True)
    return matches


def get_distances(nlitext, title: RepTitle):
    nli_words = nlitext.split()
    nli_set = set(nli_words)

    main = gettopguess(nli_set, title.main)
    len_main = len(main)
    main_of_nli = " ".join(nli_words[:len_main])
    main_title = " ".join(main)
    main_distance, main_ratio = distance_ratio(main_title, main_of_nli)

    nli_remaining_set = set(nli_words[len_main:])
    remaining = gettopguess(
        nli_remaining_set, (title.sub or []) + (title.resp or [])
    )
    remaining_of_nli = " ".join(nli_words[len_main:])
    remaining_title = " ".join(remaining)
    remaining_ratio = 1 - Levenshtein.jaro(remaining_title, remaining_of_nli)

    return (
        main_title,
        main_distance,
        main_ratio,
        remaining_title,
        remaining_ratio,
    )


Reps = Sequence[str]


def strip_strings_and_update_set(s: set, strings):
    s.update(s.strip(string.punctuation) for s in strings)


def make_name_set(names, name_reps):
    name_parts = set()
    for name in names:
        name_parts.update(split_no_punctuation(name))
    for name in name_reps:
        if name:
            strip_strings_and_update_set(name_parts, chain(*name))
    return set(names), name_parts


def match_names(names, name_parts, match_names):
    shared_names = names.intersection(match_names)
    if shared_names:
        return shared_names, None
    _, match_parts = make_name_set(match_names, [])
    overlap = name_parts.intersection(match_parts)
    return shared_names, overlap


def rank_results2(
    names,
    people_reps: Collection[Sequence[Reps]],
    publisher,
    publisher_reps: Collection[Sequence[Reps]],
    years,
    title: RepTitle,
    results,
):
    names, name_parts = make_name_set(names, people_reps)
    for ben in ("בן", "בין", "ben", "Ben"):
        name_parts.discard(ben)
    years_ = set()
    for ys in map(dt.yearnorm, years):
        years_.update(ys)
    years = years_
    matches = []
    for doc in results[:5]:
        excellent_match = False

        # title matching
        nli_stripped = prepare_api_doctitle(doc)
        (
            main_title,
            main_distance,
            main_ratio,
            remaining_title,
            remaining_ratio,
        ) = get_distances(nli_stripped, title)
        if main_distance > 1:
            continue

        diff = mean([main_ratio, remaining_ratio / 2])
        if diff < 0.03:
            excellent_match = True

        # name matching
        docnames = doc["creator"]
        if docnames and names:
            shared_names, partial_names = match_names(
                names, name_parts, docnames
            )
            if not shared_names and not partial_names and not excellent_match:
                continue
        else:
            shared_names = []
            partial_names = []

        # date matching
        docdate = doc["date"] if years else None
        if docdate:
            docdates = list(getdocyears(docdate))
            shared_dates = years.intersection(docdates)
            if not shared_dates and not excellent_match:
                continue
        else:
            shared_dates = []

        # composite matching
        append = False
        ret_title = doc["title"][0].joined
        has_names = shared_names or partial_names
        if excellent_match:
            append = True
        elif main_title and main_distance == 0 and not remaining_title:
            ret_title = main_title
            append = True
        elif diff < 0.3:
            if shared_dates and not (names and docnames):
                append = True
            elif has_names and not (years or docdate):
                append = True
            elif has_names and shared_dates:
                append = True

        if append:
            matches.append(
                {
                    "title": ret_title,
                    "doc": doc,
                    "diff": diff,
                    "dates": list(shared_dates),
                    "names": list(shared_names),
                }
            )

    matches.sort(key=lambda m: m["diff"], reverse=True)
    return matches
