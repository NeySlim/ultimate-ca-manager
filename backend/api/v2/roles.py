"""
Roles & Permissions API
Manage user roles and RBAC permissions
"""

from flask import Blueprint, jsonify, request
from api.v2.auth import require_auth
from models import User, db

bp = Blueprint('roles', __name__, url_prefix='/api/v2/roles')


# Default roles (fallback when features module not loaded)
DEFAULT_ROLES = {
    'admin': {
        'name': 'Administrator',
        'description': 'Full system access',
        'permissions': ['*']
    },
    'operator': {
        'name': 'Operator',
        'description': 'Issue and manage certificates',
        'permissions': ['certificates:*', 'csrs:*', 'templates:read']
    },
    'viewer': {
        'name': 'Viewer',
        'description': 'Read-only access',
        'permissions': ['*:read']
    }
}


def get_custom_roles():
    """Get custom roles from database if features module is loaded"""
    try:
        from models.features.rbac import CustomRole
        return CustomRole.query.order_by(CustomRole.is_system.desc(), CustomRole.name).all()
    except ImportError:
        return None


@bp.route('', methods=['GET'])
@require_auth()
def list_roles():
    """List all available roles"""
    # Try to get custom roles from features
    custom_roles = get_custom_roles()
    
    if custom_roles is not None:
        return jsonify({
            'data': [role.to_dict() for role in custom_roles]
        })
    
    # Fallback to default roles
    roles = []
    for role_id, role_data in DEFAULT_ROLES.items():
        roles.append({
            'id': role_id,
            'name': role_data['name'],
            'description': role_data['description'],
            'permissions': role_data['permissions'],
            'is_system': True
        })
    return jsonify({'data': roles})


@bp.route('/<int:role_id>', methods=['GET'])
@require_auth()
def get_role(role_id):
    """Get role details by ID"""
    try:
        from models.features.rbac import CustomRole
        role = CustomRole.query.get(role_id)
        if not role:
            return jsonify({'error': True, 'message': 'Role not found'}), 404
        return jsonify({'data': role.to_dict()})
    except ImportError:
        return jsonify({'error': True, 'message': 'Feature not available'}), 404


@bp.route('', methods=['POST'])
@require_auth()
def create_role():
    """Create a new custom role"""
    try:
        from models.features.rbac import CustomRole
    except ImportError:
        return jsonify({'error': True, 'message': 'Feature not available'}), 403
    
    data = request.get_json()
    name = data.get('name', '').strip()
    
    if not name:
        return jsonify({'error': True, 'message': 'Role name is required'}), 400
    
    if CustomRole.query.filter_by(name=name).first():
        return jsonify({'error': True, 'message': 'Role with this name already exists'}), 409
    
    role = CustomRole(
        name=name,
        description=data.get('description', ''),
        permissions=data.get('permissions', []),
        inherits_from=data.get('inherits_from'),
        is_system=False  # User-created roles are never system roles
    )
    db.session.add(role)
    db.session.commit()
    
    return jsonify({'data': role.to_dict(), 'message': 'Role created successfully'}), 201


@bp.route('/<int:role_id>', methods=['PUT'])
@require_auth()
def update_role(role_id):
    """Update an existing role"""
    try:
        from models.features.rbac import CustomRole
    except ImportError:
        return jsonify({'error': True, 'message': 'Feature not available'}), 403
    
    role = CustomRole.query.get(role_id)
    if not role:
        return jsonify({'error': True, 'message': 'Role not found'}), 404
    
    if role.is_system:
        return jsonify({'error': True, 'message': 'System roles cannot be modified'}), 403
    
    data = request.get_json()
    
    if 'name' in data:
        new_name = data['name'].strip()
        if new_name and new_name != role.name:
            if CustomRole.query.filter_by(name=new_name).first():
                return jsonify({'error': True, 'message': 'Role with this name already exists'}), 409
            role.name = new_name
    
    if 'description' in data:
        role.description = data['description']
    
    if 'permissions' in data:
        role.permissions = data['permissions']
    
    if 'inherits_from' in data:
        role.inherits_from = data['inherits_from']
    
    db.session.commit()
    
    return jsonify({'data': role.to_dict(), 'message': 'Role updated successfully'})


@bp.route('/<int:role_id>', methods=['DELETE'])
@require_auth()
def delete_role(role_id):
    """Delete a custom role"""
    try:
        from models.features.rbac import CustomRole
    except ImportError:
        return jsonify({'error': True, 'message': 'Feature not available'}), 403
    
    role = CustomRole.query.get(role_id)
    if not role:
        return jsonify({'error': True, 'message': 'Role not found'}), 404
    
    if role.is_system:
        return jsonify({'error': True, 'message': 'System roles cannot be deleted'}), 403
    
    db.session.delete(role)
    db.session.commit()
    
    return jsonify({'message': 'Role deleted successfully'})


@bp.route('/<int:role_id>/permissions', methods=['GET'])
@require_auth()
def get_role_permissions(role_id):
    """Get all permissions for a role (including inherited)"""
    try:
        from models.features.rbac import CustomRole
        role = CustomRole.query.get(role_id)
        if not role:
            return jsonify({'error': True, 'message': 'Role not found'}), 404
        return jsonify({'data': role.get_all_permissions()})
    except ImportError:
        return jsonify({'error': True, 'message': 'Feature not available'}), 404


@bp.route('/users/<int:user_id>', methods=['POST'])
@require_auth()
def toggle_user_active(user_id):
    """Toggle user active status"""
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 404
    
    user.is_active = not user.is_active
    db.session.commit()
    
    return jsonify({
        'data': user.to_dict(),
        'message': f'User {"activated" if user.is_active else "deactivated"} successfully'
    })
