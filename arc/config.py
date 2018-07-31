from pathlib import Path
from . import Decoder
from arc.db import ArcDB
import deromanize
CACHE_NAMES = 'DIN1982', 'LOC/ALA', 'phonological'


class Config(deromanize.Config):
    def __init__(self, path=None, loader=None):
        super().__init__(path, loader)
        self.db_path = Path(self.user_conf.get("pica_db")).expanduser()

    def from_schema(self, schema_name, *args, **kwargs):
        profile = self.loader(self.schemas[schema_name])
        print(profile.get('fix_k'))
        return Decoder(profile, *args, fix_k=profile.get('fix_k'), **kwargs)

    def get_db(self):
        return ArcDB("sqlite:///" + str(self.db_path))
