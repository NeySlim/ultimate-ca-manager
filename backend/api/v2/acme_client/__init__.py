"""
ACME Client API Routes package

Routes for requesting certificates from external ACME CAs (Let's Encrypt, etc.)
split into thematic modules.
"""

import logging
from flask import Blueprint
from models import db, SystemConfig

logger = logging.getLogger(__name__)

bp = Blueprint('acme_client', __name__)


def _set_config(key: str, value: str, description: str = ''):
    """Helper to set SystemConfig value"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value, description=description))


def _coerce_bool(value, default=True, strict=False) -> bool:
    """Coerce bool-like values from JSON/config strings."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    parsed = str(value).strip().lower()
    if parsed in ('true', '1', 'yes', 'on'):
        return True
    if parsed in ('false', '0', 'no', 'off'):
        return False
    if strict:
        raise ValueError(f'Invalid boolean value: {value}')
    return default


# Note: Route modules are imported in api/v2/__init__.py to register routes
# This avoids circular import issues
