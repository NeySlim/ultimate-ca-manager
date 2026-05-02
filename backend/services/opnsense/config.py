"""
OPNsense configuration helpers — read/write import config from SystemConfig.
"""
import json
import logging
from typing import Dict, Optional

from models import db, SystemConfig
from .helpers import OPNSENSE_CONFIG_KEY

logger = logging.getLogger(__name__)


def get_import_config() -> Optional[Dict]:
    """Get OPNsense import configuration from system config."""
    config = SystemConfig.query.filter_by(key=OPNSENSE_CONFIG_KEY).first()
    if not config:
        return None
    return json.loads(config.value)


def save_import_config(base_url: str, username: str = None, password: str = None,
                       api_key: str = None, api_secret: str = None,
                       verify_ssl: bool = False) -> None:
    """
    Save OPNsense import configuration.

    Supports both authentication methods:
    - username/password for web scraping
    - api_key/api_secret for REST API (recommended)
    """
    config = SystemConfig.query.filter_by(key=OPNSENSE_CONFIG_KEY).first()
    if not config:
        config = SystemConfig(key=OPNSENSE_CONFIG_KEY)
        db.session.add(config)

    config_data = {
        "base_url": base_url,
        "verify_ssl": verify_ssl
    }

    if api_key and api_secret:
        config_data["api_key"] = api_key
        config_data["api_secret"] = api_secret
        config_data["auth_method"] = "api"
    else:
        config_data["username"] = username
        config_data["password"] = password
        config_data["auth_method"] = "web"

    config.value = json.dumps(config_data)
    db.session.commit()
