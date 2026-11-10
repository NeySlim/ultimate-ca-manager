"""Installation configuration directory: ucm.env and master.key live there.

UCM_CONFIG_DIR moves it (default /etc/ucm); importable before config.settings.
"""
import os
from pathlib import Path

DEFAULT_CONFIG_DIR = Path('/etc/ucm')


def config_dir() -> Path:
    """The one place UCM_CONFIG_DIR is resolved; empty means unset."""
    return Path(os.environ.get('UCM_CONFIG_DIR') or DEFAULT_CONFIG_DIR)


def env_file() -> Path:
    return config_dir() / 'ucm.env'


def master_key_file() -> Path:
    return config_dir() / 'master.key'
