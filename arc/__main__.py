import yaml
from pathlib import Path
from arc import Decoder

PROJ_PATH = Path(__file__).absolute().parents[1]
CONF_PATH = PROJ_PATH/'data'/'old.yml'
dr = Decoder(yaml.safe_load(CONF_PATH.open()))
