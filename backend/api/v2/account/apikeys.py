import json
import logging

from flask import request, g, current_app
from models import db
from models.api_key import APIKey
from auth.unified import AuthManager, require_auth, has_permission
from auth.permissions import get_effective_permissions, VALID_RESOURCES
from services.audit_service import AuditService
from utils.response import success_response, error_response, created_response
from utils.db_transaction import safe_commit

from . import bp

logger = logging.getLogger(__name__)


def _caller_can_grant(perm, owner_perms):
    """A scope is grantable only if both the owner and the requesting credential hold it."""
    caller_perms = g.permissions or []
    if perm == '*':
        return '*' in owner_perms and '*' in caller_perms
    return has_permission(perm, owner_perms) and has_permission(perm, caller_perms)


@bp.route('/api/v2/account/apikeys', methods=['GET'])
@require_auth()
def list_api_keys():
    """
    List all API keys for current user

    GET /api/account/apikeys
    """
    api_keys = APIKey.query.filter_by(
        user_id=g.user_id
    ).order_by(APIKey.created_at.desc()).all()

    return success_response(
        data=[key.to_dict() for key in api_keys],
        meta={'total': len(api_keys)}
    )


@bp.route('/api/v2/account/apikeys', methods=['POST'])
@require_auth()
def create_api_key():
    """
    Create new API key

    POST /api/account/apikeys
    Body: {
        "name": "Automation Script",
        "permissions": ["read:cas", "write:certificates"],
        "expires_days": 365  // optional, default 365
    }

    Returns the key ONLY ONCE!
    """
    data = request.json

    # Validation
    if not data or not data.get('name'):
        return error_response('Name is required', 400)

    if not data.get('permissions'):
        return error_response('Permissions are required', 400)

    if not isinstance(data['permissions'], list):
        return error_response('Permissions must be a list', 400)

    # Validate permissions format — users cannot grant permissions they don't have
    user_perms = get_effective_permissions(g.current_user)
    valid_categories = ['read', 'write', 'delete', 'admin']
    # Canonical resource set (ROLE_PERMISSIONS + admin-only resources) — see auth/permissions.py
    valid_resources = VALID_RESOURCES

    for perm in data['permissions']:
        if perm == '*':
            if not _caller_can_grant('*', user_perms):
                return error_response('Only admins can create wildcard API keys', 403)
            continue

        if ':' in perm:
            category, resource = perm.split(':', 1)
            if category not in valid_categories and category not in ['*']:
                return error_response(f'Invalid permission category: {category}', 400)
            if resource not in valid_resources and resource not in ['*']:
                return error_response(f'Invalid permission resource: {resource}', 400)
        else:
            return error_response(f'Invalid permission format: {perm}', 400)

        if not _caller_can_grant(perm, user_perms):
            return error_response(
                f'Cannot grant permission you do not have: {perm}',
                403,
            )

    # Check limit (max 10 keys per user by default). Expired keys don't
    # count - is_active alone doesn't capture that, expiry is derived live
    # (APIKey.is_expired) rather than persisted.
    max_keys = current_app.config.get('API_KEY_MAX_PER_USER', 10)
    existing_count = sum(
        1 for k in APIKey.query.filter_by(user_id=g.user_id, is_active=True).all()
        if not k.is_expired
    )

    if existing_count >= max_keys:
        return error_response(
            f'Maximum {max_keys} active API keys per user',
            400,
            {'current': existing_count, 'max': max_keys}
        )

    # Create API key
    auth_manager = AuthManager()

    # Resolve expiration:
    #   - key absent           -> default to 365 days
    #   - explicit None / 0    -> never expires
    #   - positive int         -> N days
    if 'expires_days' in data:
        raw_expires = data.get('expires_days')
    elif 'expires_in_days' in data:
        raw_expires = data.get('expires_in_days')
    else:
        raw_expires = 365

    if raw_expires in (None, 0, '', '0'):
        expires_days = None
    else:
        try:
            expires_days = int(raw_expires)
            if expires_days < 0:
                return error_response('expires_days must be >= 0', 400)
        except (TypeError, ValueError):
            return error_response('expires_days must be an integer or null', 400)

    try:
        key_info = auth_manager.create_api_key(
            user_id=g.user_id,
            name=data['name'],
            permissions=data['permissions'],
            expires_days=expires_days
        )

        AuditService.log_action(
            action='apikey_create',
            resource_type='api_key',
            resource_name=data['name'],
            details=f'Created API key: {data["name"]}',
            success=True
        )

        return created_response(
            data=key_info,
            message='API key created successfully. Save the key now - it won\'t be shown again!'
        )

    except Exception as e:
        current_app.logger.error(f"Error creating API key: {e}")
        return error_response('Failed to create API key', 500)


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['GET'])
@require_auth()
def get_api_key(key_id):
    """
    Get API key details
    Note: Does NOT return the actual key (only hash stored)
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()

    if not api_key:
        return error_response('API key not found', 404)

    return success_response(data=api_key.to_dict())


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['PATCH'])
@require_auth()
def update_api_key(key_id):
    """
    Update API key (name only, can't change permissions)

    PATCH /api/account/apikeys/:id
    Body: {"name": "New Name"}
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()

    if not api_key:
        return error_response('API key not found', 404)

    data = request.json

    # Only allow updating name
    if 'name' in data:
        api_key.name = data['name']
        ok, _err = safe_commit(logger, "Failed to update API key")
        if not ok:
            return _err

    return success_response(
        data=api_key.to_dict(),
        message='API key updated'
    )


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['DELETE'])
@require_auth()
def delete_api_key(key_id):
    """
    Revoke/delete API key

    DELETE /api/account/apikeys/:id

    First call on a still-usable key revokes it (is_active=False, kept for
    audit history). Calling it again - or calling it on a key that has
    already expired - permanently removes the row; this is the only way
    to actually delete one.
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()

    if not api_key:
        return error_response('API key not found', 404)

    key_name = api_key.name

    if api_key.is_active and not api_key.is_expired:
        api_key.is_active = False
        ok, _err = safe_commit(logger, "Failed to revoke API key")
        if not ok:
            return _err

        AuditService.log_action(
            action='apikey_revoke',
            resource_type='api_key',
            resource_id=str(key_id),
            resource_name=key_name,
            details=f'Revoked API key: {key_name}',
            success=True
        )

        return success_response(message='API key revoked')

    db.session.delete(api_key)
    ok, _err = safe_commit(logger, "Failed to delete API key")
    if not ok:
        return _err

    AuditService.log_action(
        action='apikey_delete',
        resource_type='api_key',
        resource_id=str(key_id),
        resource_name=key_name,
        details=f'Deleted API key: {key_name}',
        success=True
    )

    return success_response(message='API key deleted')


@bp.route('/api/v2/account/apikeys/<int:key_id>/regenerate', methods=['POST'])
@require_auth()
def regenerate_api_key(key_id):
    """
    Regenerate API key (creates new key, revokes old one)

    POST /api/account/apikeys/:id/regenerate

    Returns new key ONLY ONCE!
    """
    old_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()

    if not old_key:
        return error_response('API key not found', 404)

    old_perms = json.loads(old_key.permissions)
    owner_perms = get_effective_permissions(g.current_user)
    if not all(_caller_can_grant(p, owner_perms) for p in old_perms):
        return error_response('Cannot regenerate a key wider than the requesting credential', 403)

    # Create new key with same settings
    auth_manager = AuthManager()

    try:
        new_key_info = auth_manager.create_api_key(
            user_id=g.user_id,
            name=old_key.name + ' (regenerated)',
            permissions=old_perms,
            expires_days=365
        )

        # Revoke old key
        old_key.is_active = False
        db.session.commit()

        AuditService.log_action(
            action='apikey_regenerate',
            resource_type='api_key',
            resource_id=str(key_id),
            resource_name=old_key.name,
            details=f'Regenerated API key: {old_key.name}',
            success=True
        )

        return created_response(
            data=new_key_info,
            message='API key regenerated. Old key revoked. Save the new key now!'
        )

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error regenerating API key: {e}")
        return error_response('Failed to regenerate API key', 500)
