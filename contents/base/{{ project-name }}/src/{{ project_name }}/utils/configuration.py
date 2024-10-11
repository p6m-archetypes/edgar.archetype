import logging.config
import os
import yaml
from pathlib import Path


def configure_logging():
    logging_config = os.path.join(Path(__file__).parent.parent.parent.parent, 'logging.yaml')
    with open(logging_config, 'rt') as f:
        config = yaml.safe_load(f.read())

    # Configure the logging module with the config file
    logging.config.dictConfig(config)
