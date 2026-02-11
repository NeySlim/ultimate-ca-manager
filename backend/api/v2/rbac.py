"""
Advanced RBAC API - UCM
Custom roles and fine-grained permissions
"""

from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db
from models.rbac import CustomRole, RolePermission

bp = Blueprint('rbac_pro', __name__)

# Default permissions available in the system
AVAILABLE_PERMISSIONS = [
    # CAs
    'read:cas', 'write:cas', 'delete:cas', 'admin:cas',
    # Certificates
    'read:certs', 'write:certs', 'delete:certs', 'revoke:certs',
    # CSRs
    'read:csrs', 'write:csrs', 'delete:csrs', 'sign:csrs',
    # Users
    'read:users', 'write:users', 'delete:users', 'admin:users',
    # Groups 
    'read:groups', 'write:groups', 'delete:groups', 'admin:groups',
    # Settings
    'read:settings', 'write:settings', 'admin:system',
    # Audit
    'read:audit', 'export:audit',
    # ACME 
    'read:acme', 'write:acme', 'delete:acme',
    # SCEP 
    'read:scep', 'write:scep', 'delete:scep',
    # Trust Store 
    'read:truststore', 'write:truststore', 'delete:truststore',
    # HSM 
    'read:hsm', 'write:hsm', 'delete:hsm',
    # SSO 
    'read:sso', 'write:sso', 'delete:sso',
    # Templates
    'read:templates', 'write:templates', 'delete:templates',
    # Policies 
    'read:policies', 'write:policies', 'delete:policies',
    # Approvals 
    'read:approvals', 'write:approvals',
]

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

@bp.route('/api/v2/rbac/roles', methods=['POST'])
@require_auth(['admin:users'])
def create_custom_role():
    """Create a custom role"""
    data = request.get_json()
    
    if not data.get('name'):
        return error_response("Role name is required", 400)
    
    if CustomRole.query.filter_by(name=data['name']).first():
        return error_response("Role already exists", 409)
    
    role = CustomRole(
        name=data['name'],
        description=data.get('description', ''),
        permissions=data.get('permissions', []),
        inherits_from=data.get('inherits_from')  # Parent role ID
    )
    db.session.add(role)
    db.session.commit()
    
    return success_response(data=role.to_dict(), message="Custom role created")

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['GET'])
@require_auth(['read:users'])
def get_custom_role(role_id):
    """Get custom role details"""
    role = CustomRole.query.get_or_404(role_id)
    return success_response(data=role.to_dict())

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['PUT'])
@require_auth(['admin:users'])
def update_custom_role(role_id):
    """Update a custom role"""
    role = CustomRole.query.get_or_404(role_id)
    data = request.get_json()
    
    if 'name' in data:
        role.name = data['name']
    if 'description' in data:
        role.description = data['description']
    if 'permissions' in data:
        role.permissions = data['permissions']
    if 'inherits_from' in data:
        role.inherits_from = data['inherits_from']
    
    db.session.commit()
    return success_response(data=role.to_dict(), message="Role updated")

@bp.route('/api/v2/rbac/roles/<int:role_id>', methods=['DELETE'])
@require_auth(['admin:users'])
def delete_custom_role(role_id):
    """Delete a custom role"""
    role = CustomRole.query.get_or_404(role_id)
    
    if role.is_system:
        return error_response("System roles cannot be deleted", 403)
    
    # Check if role is in use
    from models import User
    user_count = User.query.filter_by(custom_role_id=role_id).count()
    if user_count > 0:
        return error_response(f"Role is assigned to {user_count} user(s). Remove assignments first.", 409)
    
    db.session.delete(role)
    db.session.commit()
    return success_response(message="Role deleted")

@bp.route('/api/v2/rbac/effective-permissions/<int:user_id>', methods=['GET'])
@require_auth(['admin:users'])
def get_effective_permissions(user_id):
    """Get effective permissions for a user (role + groups + custom)"""
    from models import User
    user = User.query.get_or_404(user_id)
    
    permissions = set()
    
    # Base role permissions
    if user.role == 'admin':
        permissions.update(AVAILABLE_PERMISSIONS)
    elif user.role == 'operator':
        permissions.update(['read:cas', 'read:certs', 'write:certs', 'read:csrs', 'sign:csrs'])
    else:
        permissions.update(['read:cas', 'read:certs'])
    
    # Custom role permissions
    if getattr(user, 'custom_role_id', None):
        custom_role = CustomRole.query.get(user.custom_role_id)
        if custom_role:
            permissions.update(custom_role.get_all_permissions())
    
    # Group permissions
    try:
        for group in user.groups:
            permissions.update(group.permissions or [])
    except Exception:
        pass
    
    return success_response(data=list(permissions))
