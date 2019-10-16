import sys
import json
from .. import solrtools as st
import tornado
import typing as t
from libaaron import lxml_little_iter, pmap, pfilter, pipe
from ..decode import debracket
import listdict

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
    return [
        doc.get(getfield(x)) for x in ("title", "subtitle", "responsibility")
    ]


def mkfield(fieldname, query):
    return st.mkfield(getfield(fieldname), query)


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
    # core = solrtools.SolrCore("http://localhost:8983/solr/" + index)
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


def clean_nli_text(text):
    if not text:
        return text
    text = text[0]
    return pipe(
        text,
        debracket,
        lambda s: s.replace(">>", "").split(),
        pmap(lambda s: s.strip(st.punctuation)),
        pfilter(None),
        " ".join,
    )


def prepare_doctitle(doc):
    out = map(clean_nli_text, st.gettitle(doc))
    return " ".join(filter(None, out))
