"""Pipeline configuration, read from config/pipeline.yml (path overridable with PIPELINE_CONFIG)."""
import os
from pathlib import Path

import yaml

CONFIG_PATH = Path(os.getenv('PIPELINE_CONFIG', Path(__file__).resolve().parents[2] / 'config' / 'pipeline.yml'))


def load_config(path=None):
    return yaml.safe_load(Path(path or CONFIG_PATH).read_text())
