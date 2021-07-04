"""config objects and session objects to build decoders, caches and all
kinds of other useful things for retro-conversion.
"""
from pathlib import Path
import libaaron
import deromanize
import enum
from . import filters
from .decode import Decoder
from typing import NamedTuple

CACHE_NAMES = "DIN1982", "LOC/ALA", "phonological"


class Config(deromanize.Config):
    """type represeting a config file with methods for generating
    appropriate data structures from it.
    """

    def __init__(self, path=None, loader=None):
        """
        - path: path to configuration file
        - loader: function for deserializing the config file. YAML is
          default.
        """
        super().__init__(path, loader)
        try:
            self.db_path = Path(self.user_conf.get("pica_db")).expanduser()
            self.pica_path = Path(self.user_conf.get("pica_file")).expanduser()
        except TypeError:
            pass

        try:
            nli = self["nli_checker"]
        except KeyError:
            return

        self.solr_url = nli["solr_url"]
        try:
            self.ppn_file = Path(nli["ppn_file"]).expanduser()
        except KeyError:
            self.ppn_file = None
        self._term_paths = [Path(p).expanduser() for p in nli["terms"]]

    def from_schema(self, schema_name, *args, **kwargs):
        """build a decoder from a schema_name. *args and **kwargs are
        passed on to arc.decode.Decoder.
        """

        profile = self.loader(self.schemas[schema_name])
        return Decoder(
            profile,
            *args,
            fix_k=profile.get("fix_k"),
            name=schema_name,
            **kwargs
        )

    def get_db(self):
        """initialize the ARC database, which contains pica records as
        well as some tables for auditing generated results.
        """
        from .db import ArcDB

        return ArcDB("sqlite:///" + str(self.db_path))

    def get_index(self):
        """returns a pica index, in the event you don't want to bother
        with a database. This is actually much faster than using the
        database, but you can only pull records by ppn.
        """
        import pica_parse

        return pica_parse.PicaIndex.from_file(self.pica_path)

    def get_term_counts(self):
        from .nlitools import core

        return core.make_dicts(*self._term_paths)


class Standard(enum.Enum):
    old = "Old DIN 31631"
    new = "New DIN 31631"
    pi = "PI"
    unknown = "unknown"
    not_latin = "not_latin"


class InputInfo(NamedTuple):
    standard: Standard
    foreign_tokens: bool
    transliteration_tokens: bool


class ConversionInfo(NamedTuple):
    fully_converted: bool
    all_cached: bool
    # all_singular: bool
    all_recognized: bool


class Session:
    _sessions = {}
    filters = filters

    def __init__(self, config: Config, asynchro=False):
        """
        config -- a Config instance to pull data from
        """
        # NLI stuff
        self.cores = libaaron.DotDict()
        self.termdict = None
        self.asynchro = asynchro
        # Not NLI stuff
        self.config = config
        self.records = config.get_db()
        self.caches = c = libaaron.DotDict()
        c.din, c.loc, c.phon = self.config.get_caches(*CACHE_NAMES)
        self.decoders = libaaron.DotDict()

    @classmethod
    def fromconfig(cls, path=None, loader=None, asynchro=False):
        """takes the same arguments as the ``Config`` initializer,
        constructs the config object and uses it to build a session.
        """
        s = cls._sessions.get((path, loader))
        if not s:
            s = cls._sessions[path, loader, asynchro] = cls(
                Config(path=path, loader=loader), asynchro=asynchro
            )
        return s

    def add_decoder(self, name, *args, **kwargs):
        from . import cacheutils as cu

        decoder = self.decoders.get(name)
        if not decoder:
            decoder = self.decoders[name] = self.config.from_schema(
                name, *args, **kwargs
            )
        if name == "old" and not hasattr(self, "getloc"):
            set_reps = decoder.profile["to_new"]["sets"]
            simple_reps = decoder.profile["to_new"]["replacements"]
            self.getloc = cu.loc_converter_factory(simple_reps, set_reps)
        return decoder

    def add_decoders(self, names, *args, **kwargs):
        return [self.add_decoder(name, *args, **kwargs) for name in names]

    def pickdecoder(self, string: str):
        line = filters.Line(string)
        has_old, has_new, only_new, only_pi, only_old, ascii_letters = map(
            line.has,
            ("old", "new", "only_new", "only_pi", "only_old", "ascii_letters"),
        )
        foreign_tokens = any(
            map(line.has, ("english_y", "foreign", "yiddish_ending"))
        )
        transliteration_tokens = line.has("transliteration")

        def input_info(standard):
            return InputInfo(standard, foreign_tokens, transliteration_tokens)

        if only_new:
            return self.decoders.new, input_info(Standard.new)
        if only_pi:
            return self.decoders.pi, input_info(Standard.pi)
        if only_old:
            return self.decoders.old, input_info(Standard.old)
        if has_new:
            if has_old:
                return self.decoders.old, input_info(Standard.unknown)
            return self.decoders.new, input_info(Standard.new)
        if not ascii_letters:
            return self.decoders.old, input_info(Standard.not_latin)
        return self.decoders.old, input_info(Standard.unknown)

    def getchunks(self, string: str):
        decoder, input_info = self.pickdecoder(string)
        return decoder.make_chunks(string), input_info

    def usecache(self, chunks, **kwargs):
        from . import cacheutils as cu

        decoder = chunks.decoder
        loc, phon = self.caches.loc, self.caches.phon
        words = []

        fully_converted = True
        all_cached = True
        # all_singular = True
        all_recognized = True
        for chunk in chunks:
            rlist, match_info = cu.match_cached(
                chunk, decoder, loc, phon, **kwargs
            )
            words.append(rlist)
            if fully_converted:
                if not filters.Line(str(rlist[0])).has("only_heb"):
                    fully_converted = False
                    all_cached = False
                    # all_singular = False
                    all_recognized = False
                elif all_recognized:
                    if all_cached:
                        if not match_info.cached:
                            all_cached = False
                            # all_singular = False
                            if not match_info.recognized:
                                all_recognized = False
                        # elif all_singular and not match_info.singular:
                        #     all_singular = False

        return words, ConversionInfo(
            fully_converted, all_cached, all_recognized
        )

    # NLI stuff
    def add_core(self, name):

        core = self.cores.get(name)
        if not core:
            from .nlitools import solrmarc

            if self.asynchro:
                CoreType = solrmarc.NliAsyncCore
            else:
                CoreType = solrmarc.NliCore
            core = self.cores[name] = CoreType(
                self.config.solr_url + "/" + name
            )
        return core

    def add_cores(self, names):
        return [self.add_core(n) for n in names]

    def add_termdict(self):
        if self.termdict:
            return self.termdict
        out = self.termdict = self.config.get_term_counts()
        return out


def mk_default(resources="resources"):
    import deromanize.config

    config = deromanize.config.mk_default(resources)
    respath = Path().absolute() / resources
    config["nli_checker"] = {
        "solr_url": "http://localhost:8983/solr",
        "terms": [str(respath / "wordlists" / "terms.json")],
    }
    return config


def dump_config_file(resources="resources"):
    import sys
    import deromanize.config
    import yaml

    if sys.stdout.isatty():
        cfgpath = deromanize.config.CFG_PATHS[1]
        print("# redirect the output of this command to:")
        print("#")
        print("#    ", str(cfgpath))
        print("#")
        print("# Then, edit it.")
        print()
    config = mk_default(resources)
    print(yaml.dump(config))
