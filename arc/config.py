"""config objects and session objects to build decoders, caches and all
kinds of other useful things for retro-conversion.
"""
from pathlib import Path
import libaaron
import deromanize
import pica_parse
from .db import ArcDB
from . import Decoder
from . import cacheutils as cu
from . import filters

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
        self.db_path = Path(self.user_conf.get("pica_db")).expanduser()
        self.pica_path = Path(self.user_conf.get("pica_file")).expanduser()

    def from_schema(self, schema_name, *args, **kwargs):
        """build a decoder from a schema_name. *args and **kwargs are
        passed on to arc.decode.Decoder.
        """
        profile = self.loader(self.schemas[schema_name])
        return Decoder(profile, *args, fix_k=profile.get("fix_k"), **kwargs)

    def get_db(self):
        """initialize the ARC database, which contains pica records as
        well as some tables for auditing generated results.
        """
        return ArcDB("sqlite:///" + str(self.db_path))

    def get_index(self):
        """returns a pica index, in the event you don't want to bother
        with a database. This is actually much faster than using the
        database, but you can only pull records by ppn.
        """
        return pica_parse.PicaIndex.from_file(self.pica_path)


class Session:
    __slots__ = ("config", "decoders", "caches", "records", "getloc")
    _sessions = {}
    filters = filters

    def __init__(self, config: Config):
        """
        config -- a Config instance to pull data from
        """
        self.config = config
        self.records = config.get_db()
        self.caches = c = libaaron.DotDict()
        c.din, c.loc, c.phon = self.config.get_caches(*CACHE_NAMES)
        self.decoders = libaaron.DotDict()

    @classmethod
    def fromconfig(cls, path=None, loader=None, CfgType=Config):
        """takes the same arguments as the ``Config`` initializer,
        constructs the config object and uses it to build a session.
        """
        s = cls._sessions.get((path, loader))
        if not s:
            s = cls._sessions[path, loader] = cls(
                CfgType(path=path, loader=loader)
            )
        return s

    def add_decoder(self, name, *args, **kwargs):
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
        if line.has("only_new"):
            return self.decoders.new
        return self.decoders.old

    def getchunks(self, string: str):
        decoder = self.pickdecoder(string)
        return decoder.make_chunks(string)

    def usecache(self, chunks, **kwargs):
        decoder = chunks.decoder
        loc, phon = self.caches.loc, self.caches.phon
        words = []
        for chunk in chunks:
            words.append(cu.match_cached(chunk, decoder, loc, phon, **kwargs))
        return words
