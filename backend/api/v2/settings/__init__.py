"""
Settings Routes v2.0
/api/settings/* - System settings (general, users, backup, email, etc.)
"""

from flask import Blueprint
from models import db, SystemConfig
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('settings_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)
