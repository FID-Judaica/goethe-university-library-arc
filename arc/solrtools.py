# Copyright 2018, Goethe University
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
import tornado.httpclient
import libaaron
import re
import requests
import typing as t
import json

decode = json.JSONDecoder().decode
encode = json.JSONEncoder().encode

# schema API
hebrew_text = {
    "add-field-type": {
        "name": "hebrew_text",
        "class": "solr.TextField",
        "analyzer": {"tokenizer": {"class": "solr.ICUTokenizerFactory"}},
    }
}
heb_text_template = {
    "add-field": {
        "type": "hebrew_text",
        "multiValued": True,
        "stored": True,
        "tokenized": True,
        "indexed": True,
    }
}

# text cleaning stuff.
_sp = r'\ + - && || ! ( ) { } [ ] ^ " ~ * ? :'.split()
_sp.append(" ")
SPECIAL_CHARS = re.compile("(" + "|".join(re.escape(c) for c in _sp) + ")")


def lucene_escape(word):
    """takes a string as input and properly escapes it for use in a
    Lucene query.
    """
    return SPECIAL_CHARS.sub(r"\\\1", word)


def strip_gross_chars(field):
    """some fields end with characters that I don't like"""
    if field is None:
        return None
    if field.endswith(" /") or field.endswith(" :"):
        return field[:-2]
    if field.endswith(".") or field.endswith(","):
        return field[:-1]
    return field


class QueryError(Exception):
    pass


class EmptyQuery(QueryError):
    pass


def join(terms, escape=True, fuzzy=False, exact=False, joiner=None):
    if exact:
        terms = ('"{}"'.format(t.replace('"', r"\"")) for t in terms)
    elif escape:
        terms = map(lucene_escape, terms)

    fz = ""
    if fuzzy:
        fz += "~"
    if not isinstance(fuzzy, bool):
        fz += str(fuzzy)

    if joiner:
        joiner = " {} ".format(joiner)
    else:
        joiner = " "

    parts = [p for term in terms for p in (term, fz, joiner)]
    try:
        del parts[-1]
    except IndexError:
        raise EmptyQuery("No search terms")
    return "({})".format("".join(parts))


def and_(terms, escape=True, fuzzy=False, exact=False):
    return join(terms, escape, fuzzy, joiner="AND")


def or_(terms, escape=True, fuzzy=False, exact=False):
    return join(terms, escape, fuzzy, joiner="OR")


def mkfield(fieldname, query):
    return "{}:{}".format(fieldname, query)


class SolrCore:
    _rsess = None

    @property
    def rsess(self):
        s = getattr(self, "_rsess", None)
        if not s:
            s = self._rsess = requests.Session()
        return s

    def __init__(self, url):
        """object for querying Solr that contains the core URL and a
        requests.Session for http.
        """
        self.url = url.rstrip("/")
        self.session = self.rsess
        self.add_docs = libaaron.chunkprocess(self.add_doc)

    @property
    def schema_url(self):
        return self.url + "/schema"

    def build_hebrew_shema(self, fields: t.Iterable[str]):
        """adds schema directives to solr for Hebrew text and adds fields to
        that should use the schema.

        - fields: a list of fields for which to use the Hebrew schema.
        """
        self.session.post(self.schema_url, json=hebrew_text)
        for fieldname in fields:
            yield self.add_heb_field(fieldname)

    def add_heb_field(self, name):
        heb_text_template["add-field"]["name"] = name
        return self.session.post(self.schema_url, json=heb_text_template)

    def add_source_field(self):
        self.session.post(
            self.schema_url,
            json={
                "add-field-type": {
                    "name": "text",
                    "class": "solr.TextField",
                    "analyzer": {
                        "tokenizer": {"class": "solr.StandardTokenizerFactory"}
                    },
                }
            },
        )
        return self.session.post(
            self.schema_url,
            json={
                "add-field": {
                    "name": "originalData",
                    "type": "text",
                    "multiValued": False,
                    "stored": True,
                    "tokenized": False,
                    "indexed": False,
                }
            },
        )

    def add_copy_fields(self, name: str, fields: t.Iterable[str]):
        """create a new copy field

        - name: name of copy field
        - fields: list fields to add to be copied into it.
        """
        self.add_heb_field(name)
        resps = []
        for field in fields:
            copy_field = {"add-copy-field": {"source": field, "dest": name}}
            resps.append(self.session.post(self.schema_url, json=copy_field))
        return resps

    def add_copy_all(self):
        """adds an "all" copy field which contains all fields"""
        return self.add_copy_field("all", ["*"])

    def add_doc(self, doc: t.Union[list, dict]) -> dict:
        """documents to solr over the json api"""
        doc_url = self.url + "/update/json/docs"
        return self.session.post(doc_url, json=doc).json()

    def run_query(self, query: str, fl=None, **kwargs):
        """Run a Lucene query against the Solr database and return the docs
        array as a list.
        """
        select_url = self.url + "/query"
        if fl:
            select_url += "?fl={}".format(",".join(fl))
        try:
            resp = self.session.get(
                select_url, json={"query": query, **kwargs}
            )
            return resp.json()["response"]
        except KeyError:
            raise QueryError(resp.text, query)

    def update(self, message: dict):
        """general update command"""
        update_url = self.url + "/update"
        return self.session.post(update_url, json=message).json()

    def commit(self):
        self.update({"commit": {}})


async def run_query_async(
    url,
    http: tornado.httpclient.AsyncHTTPClient,
    query: str,
    fl=None,
    **kwargs
):
    """Run a Lucene query against the Solr database and return the docs
    array as a list.
    """
    select_url = url + "/query"
    if fl:
        select_url += "?fl={}".format(",".join(fl))
    try:
        header = {"Content-Type": "application/json"}
        body = encode({"query": query, **kwargs})
        resp = await http.fetch(
            select_url, method="POST", headers=header, body=body
        )
        return decode(resp.body.decode())["response"]
    except KeyError:
        raise QueryError(resp.text, query)
