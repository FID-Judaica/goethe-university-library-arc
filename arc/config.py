from pathlib import Path
from . import Decoder
from . import cacheutils as cu
from . import filters
from arc.db import ArcDB
import deromanize
import pica_parse
import libaaron

CACHE_NAMES = "DIN1982", "LOC/ALA", "phonological"


class Config(deromanize.Config):
    def __init__(self, path=None, loader=None):
        super().__init__(path, loader)
        self.db_path = Path(self.user_conf.get("pica_db")).expanduser()
        self.pica_path = Path(self.user_conf.get("pica_file")).expanduser()

    def from_schema(self, schema_name, *args, **kwargs):
        profile = self.loader(self.schemas[schema_name])
        return Decoder(profile, *args, fix_k=profile.get("fix_k"), **kwargs)

    def get_db(self):
        return ArcDB("sqlite:///" + str(self.db_path))

    def get_index(self):
        return pica_parse.PicaIndex.from_file(self.pica_path)


class Session:
    __slots__ = (
        "config",
        "decoders",
        "caches",
        "dicts",
        "predicates",
        "records",
        "getloc",
    )
    _sessions = {}

    def __init__(self, config: Config):
        """

        """
        self.config = config
        self.records = config.get_db()
        self.caches = c = libaaron.DotDict()
        c.din, c.loc, c.phon = self.config.get_caches(*CACHE_NAMES)
        self.decoders = libaaron.DotDict()
        self.dicts = libaaron.DotDict()
        self.predicates = libaaron.DotDict()

    @classmethod
    def fromconfig(cls, path=None, loader=None):
        return cls._sessions.setdefault(
            (path, loader), cls(Config(path=path, loader=loader))
        )

    def add_decoder(self, name, *args, **kwargs):
        d = self.decoders.setdefault(
            name, self.config.from_schema(name, *args, **kwargs)
        )
        if name == "old" and not hasattr(self, "getloc"):
            set_reps = d.profile["to_new"]["sets"]
            simple_reps = d.profile["to_new"]["replacements"]
            self.getloc = cu.loc_converter_factory(simple_reps, set_reps)
        return d

    def add_decoders(self, names, *args, **kwargs):
        return [self.add_decoder(name, *args, **kwargs) for name in names]

    def pickdecoder(self, string: str):
        line = filters.Line(string)
        if line.has("only_new") or line.has("new_digraphs"):
            return self.decoders.new
        else:
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
