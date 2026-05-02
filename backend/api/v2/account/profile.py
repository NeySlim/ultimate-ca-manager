import re
import logging

from flask import request, g
from models import db, User
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.datetime_utils import utc_isoformat
from auth.unified import require_auth

from . import bp

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User preferences (issue #73)
#
# Stored as a JSON object in ``users.preferences`` so they follow the user
# across browsers and devices instead of being limited to localStorage.
# ---------------------------------------------------------------------------

# Whitelist of allowed preference keys + value validators.
# Anything not listed here is silently dropped to avoid storing arbitrary blobs.
_PREF_VALIDATORS = {
    'language': lambda v: isinstance(v, str) and 1 <= len(v) <= 10,
    'theme_family': lambda v: isinstance(v, str) and 1 <= len(v) <= 30,
    'theme_mode': lambda v: v in ('light', 'dark', 'system'),
    'density': lambda v: v in ('compact', 'comfortable', 'spacious'),
    'sidebar_collapsed': lambda v: isinstance(v, bool),
    'force_desktop': lambda v: isinstance(v, bool),
    'date_format': lambda v: isinstance(v, str) and 1 <= len(v) <= 30,
    'show_time': lambda v: isinstance(v, bool),
    'timezone': lambda v: isinstance(v, str) and 1 <= len(v) <= 64,
}


def _sanitize_preferences(payload):
    """Return only valid known preference keys."""
    if not isinstance(payload, dict):
        return {}
    cleaned = {}
    for key, value in payload.items():
        validator = _PREF_VALIDATORS.get(key)
        if validator is None:
            continue
        try:
            if validator(value):
                cleaned[key] = value
        except Exception:  # noqa: BLE001 - reject anything that explodes
            continue
    return cleaned


@bp.route('/api/v2/account/profile', methods=['GET'])
@require_auth()
def get_profile():
    """Get current user profile with full details"""
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    return success_response(
        data={
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'full_name': getattr(user, 'full_name', None),
            'role': user.role,
            'active': getattr(user, 'active', True),
            'created_at': utc_isoformat(user.created_at) if hasattr(user, 'created_at') and user.created_at else None,
            'last_login': utc_isoformat(user.last_login) if hasattr(user, 'last_login') and user.last_login else None,
            'login_count': getattr(user, 'login_count', 0),
            'two_factor_enabled': getattr(user, 'totp_confirmed', False),
            'password_changed_at': utc_isoformat(user.password_changed_at) if hasattr(user, 'password_changed_at') and user.password_changed_at else None,
        }
    )


@bp.route('/api/v2/account/profile', methods=['PATCH'])
@require_auth()
def update_profile():
    """
    Update current user profile

    PATCH /api/account/profile
    Body: {
        "email": "new@email.com",
        "full_name": "John Doe",
        "timezone": "UTC"
    }
    """
    data = request.json

    if not data:
        return error_response('No data provided', 400)

    user = g.current_user

    # Update allowed fields
    if 'email' in data:
        email = data['email']
        if email and not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return error_response('Invalid email format', 400)
        user.email = email

    if 'full_name' in data:
        user.full_name = data.get('full_name')

    if 'timezone' in data:
        user.timezone = data.get('timezone', 'UTC')

    ok, _err = safe_commit(logger, "Failed to update profile")
    if not ok:
        return _err

    return success_response(
        data={
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'full_name': getattr(user, 'full_name', None),
            'timezone': getattr(user, 'timezone', 'UTC')
        },
        message='Profile updated successfully'
    )


@bp.route('/api/v2/account/preferences', methods=['GET'])
@require_auth()
def get_preferences():
    """Return the current user's stored preferences."""
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)
    return success_response(data=user.get_preferences())


@bp.route('/api/v2/account/preferences', methods=['PUT'])
@require_auth()
def update_preferences():
    """
    Replace the current user's preferences with the provided object.

    Body: { "language": "fr", "theme_mode": "dark", "theme_family": "gray", ... }
    Unknown keys are dropped. Returns the persisted preferences.
    """
    payload = request.get_json(silent=True)
    if payload is None:
        return error_response('JSON body required', 400)

    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    # PUT replaces; PATCH would merge — frontend currently uses PUT after
    # merging client-side, which keeps the contract simple.
    cleaned = _sanitize_preferences(payload)
    try:
        user.set_preferences(cleaned)
        db.session.commit()
    except Exception as exc:  # noqa: BLE001
        db.session.rollback()
        logger.error(f"Failed to save preferences for user {user.id}: {exc}")
        return error_response('Failed to save preferences', 500)

    return success_response(data=cleaned, message='Preferences updated')
