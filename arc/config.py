from pathlib import Path
from . import Decoder
from arc.db import ArcDB
import deromanize
import pica_parse
CACHE_NAMES = 'DIN1982', 'LOC/ALA', 'phonological'


class Config(deromanize.Config):
    def __init__(self, path=None, loader=None):
        super().__init__(path, loader)
        self.db_path = Path(self.user_conf.get("pica_db")).expanduser()
        self.pica_path = Path(self.user_conf.get("pica_file")).expanduser()

    def from_schema(self, schema_name, *args, **kwargs):
        profile = self.loader(self.schemas[schema_name])
        return Decoder(profile, *args, fix_k=profile.get('fix_k'), **kwargs)

    def get_db(self):
        return ArcDB("sqlite:///" + str(self.db_path))

    def get_index(self):
        return pica_parse.PicaIndex.from_file(self.pica_path)
