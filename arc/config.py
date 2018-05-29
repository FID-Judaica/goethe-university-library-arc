from pathlib import Path
from . import Decoder
from arc.db import ArcDB
import deromanize


class Config(deromanize.Config):
    def __init__(self, path=None, loader=None):
        super().__init__(path, loader)
        self.db_path = Path(self.user_conf.get('pica_db')).expanduser()

    def from_schema(self, schema_name, *args, **kwargs):
        return Decoder(self.loader(self.schemas[schema_name]),
                       *args, **kwargs)

    def get_db(self):
        return ArcDB('sqlite:///' + str(self.db_path))
