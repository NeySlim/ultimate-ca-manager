"""
Advanced RBAC API - UCM
Custom roles and fine-grained permissions
"""

from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from auth.permissions import (
    BUILTIN_ROLES, CUSTOM_ROLE_GRANTABLE_PERMISSIONS, custom_role_chain,
    get_effective_permissions as effective_permissions_of, normalize_permission,
)
from models import db
from models.rbac import CustomRole, RolePermission
from services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('rbac_pro', __name__)

# What a custom role may grant: the scopes the API enforces, never a path to admin
AVAILABLE_PERMISSIONS = CUSTOM_ROLE_GRANTABLE_PERMISSIONS

@bp.route('/api/v2/rbac/permissions', methods=['GET'])
@require_auth(['admin:users'])
def list_permissions():
    """List all available permissions"""
    return success_response(data=AVAILABLE_PERMISSIONS)

@bp.route('/api/v2/rbac/roles', methods=['GET'])
@require_auth(['read:users'])
def list_custom_roles():
    """List all custom roles"""
    roles = CustomRole.query.all()
    return success_response(data=[r.to_dict() for r in roles])

# Every built-in role name, not a copy of some of them: `auditor` was
# missing here, so a custom role could take the name of a built-in one
# while the other three were refused with a 409.
RESERVED_ROLE_NAMES = frozenset(BUILTIN_ROLES)
MAX_ROLE_NAME_LEN = 64
MAX_ROLE_DESC_LEN = 500
MAX_ROLE_PERMS = 200


def _validate_role_payload(data, *, partial=False, role_id=None):
    """Returns (cleaned_dict, error_response_or_None).

    Validates name (length, charset, reserved), description length,
    and permissions (list of strings, capped, each one in
    AVAILABLE_PERMISSIONS after legacy names are normalised; no wildcard).
    """
    cleaned = {}

    if 'name' in data or not partial:
        name = (data.get('name') or '').strip()
        if not name:
            return None, error_response("Role name is required", 400)
        if len(name) > MAX_ROLE_NAME_LEN:
            return None, error_response(f"Role name too long (max {MAX_ROLE_NAME_LEN})", 400)
        if name.lower() in RESERVED_ROLE_NAMES:
            return None, error_response(f"'{name}' is a reserved built-in role name", 409)
        # Charset: alnum, dash, underscore, space — no control chars / quotes
        import re as _re
        if not _re.fullmatch(r'[A-Za-z0-9 _\-]+', name):
            return None, error_response("Role name contains invalid characters", 400)
        cleaned['name'] = name

    if 'description' in data:
        desc = data.get('description') or ''
        if not isinstance(desc, str):
            return None, error_response("description must be a string", 400)
        if len(desc) > MAX_ROLE_DESC_LEN:
            return None, error_response(f"description too long (max {MAX_ROLE_DESC_LEN})", 400)
        cleaned['description'] = desc

    if 'permissions' in data:
        perms = data.get('permissions') or []
        if not isinstance(perms, list):
            return None, error_response("permissions must be a list", 400)
        if len(perms) > MAX_ROLE_PERMS:
            return None, error_response(f"Too many permissions (max {MAX_ROLE_PERMS})", 400)
        valid_keys = set(AVAILABLE_PERMISSIONS)
        normalized = []
        for p in perms:
            if not isinstance(p, str) or not p.strip():
                return None, error_response("permissions must be non-empty strings", 400)
            if len(p) > 100:
                return None, error_response("permission too long", 400)
            # Wildcards and admin-only scopes are refused: assigned roles now apply
            p = normalize_permission(p)
            if p not in valid_keys:
                return None, error_response(f"Permission not grantable by a custom role: {p}", 400)
            if p not in normalized:
                normalized.append(p)
        cleaned['permissions'] = normalized

    if 'inherits_from' in data:
        inh = data.get('inherits_from')
        if inh is not None and (isinstance(inh, bool) or not isinstance(inh, int)):
            return None, error_response("inherits_from must be an integer role id", 400)
        if inh is not None:
            parent = db.session.get(CustomRole, inh)
            if parent is None:
                return None, error_response("Parent role not found", 404)
            if role_id is not None and role_id in {r.id for r in custom_role_chain(parent)}:
                return None, error_response("A role cannot inherit from itself or a descendant", 400)
        cleaned['inherits_from'] = inh

    return cleaned, None


@bp.route('/api/v2/rbac/roles', methods=['POST'])
@require_auth(['admin:users'])
def create_custom_role():
    """Create a custom role"""
    data = request.get_json() or {}
    cleaned, err = _validate_role_payload(data, partial=False)
    if err:
        return err

    if CustomRole.query.filter(db.func.lower(CustomRole.name) == cleaned['name'].lower()).first():
        return error_response("Role already exists", 409)

    role = CustomRole(
        name=cleaned['name'],
        description=cleaned.get('description', ''),
        permissions=cleaned.get('permissions', []),
        inherits_from=cleaned.get('inherits_from')
    )
    db.session.add(role)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create custom role: {e}")
        return error_response('Failed to create role', 500)
    
    AuditService.log_action(
        action='create',
        resource_type='rbac_role',
        resource_id=role.id,
        resource_name=role.name,
        details=f'Created custom role: {role.name}',
        success=True
    )
    
    return success_response(data=role.to_dict(), message="Custom role created")

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['GET'])
@require_auth(['read:users'])
def get_custom_role(role_id):
    """Get custom role details"""
    role = db.get_or_404(CustomRole, role_id)
    return success_response(data=role.to_dict())

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['PUT'])
@require_auth(['admin:users'])
def update_custom_role(role_id):
    """Update a custom role"""
    role = db.get_or_404(CustomRole, role_id)
    data = request.get_json() or {}

    if getattr(role, 'is_system', False):
        return error_response("System roles cannot be modified", 403)

    cleaned, err = _validate_role_payload(data, partial=True, role_id=role_id)
    if err:
        return err

    if 'name' in cleaned and cleaned['name'].lower() != role.name.lower():
        clash = CustomRole.query.filter(
            db.func.lower(CustomRole.name) == cleaned['name'].lower(),
            CustomRole.id != role_id,
        ).first()
        if clash:
            return error_response("Role name already exists", 409)

    if 'name' in cleaned:
        role.name = cleaned['name']
    if 'description' in cleaned:
        role.description = cleaned['description']
    if 'permissions' in cleaned:
        role.permissions = cleaned['permissions']
    if 'inherits_from' in cleaned:
        role.inherits_from = cleaned['inherits_from']
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update custom role {role_id}: {e}")
        return error_response('Failed to update role', 500)
    
    AuditService.log_action(
        action='update',
        resource_type='rbac_role',
        resource_id=role.id,
        resource_name=role.name,
        details=f'Updated custom role: {role.name}',
        success=True
    )
    
    return success_response(data=role.to_dict(), message="Role updated")

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['DELETE'])
@require_auth(['admin:users'])
def delete_custom_role(role_id):
    """Delete a custom role"""
    role = db.get_or_404(CustomRole, role_id)
    
    if role.is_system:
        return error_response("System roles cannot be deleted", 403)
    
    # Check if role is in use
    from models import User
    user_count = User.query.filter_by(custom_role_id=role_id).count()
    if user_count > 0:
        return error_response(f"Role is assigned to {user_count} user(s). Remove assignments first.", 409)
    if CustomRole.query.filter_by(inherits_from=role_id).count():
        return error_response("Other roles inherit from this role. Change them first.", 409)
    
    role_name = role.name
    db.session.delete(role)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to delete custom role {role_id}: {e}")
        return error_response('Failed to delete role', 500)
    
    AuditService.log_action(
        action='delete',
        resource_type='rbac_role',
        resource_id=role_id,
        resource_name=role_name,
        details=f'Deleted custom role: {role_name}',
        success=True
    )
    
    return success_response(message="Role deleted")

@bp.route('/api/v2/rbac/effective-permissions/<int:user_id>', methods=['GET'])
@require_auth(['admin:users'])
def get_effective_permissions(user_id):
    """Effective permissions of a user: exactly what authorisation applies."""
    from models import User
    user = db.get_or_404(User, user_id)
    return success_response(data=effective_permissions_of(user))
