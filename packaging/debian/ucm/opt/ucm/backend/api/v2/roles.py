"""
Roles & Permissions API
Manage user roles and RBAC permissions
"""

from flask import Blueprint, jsonify, request
from api.v2.auth import require_auth
from models import User, db

bp = Blueprint('roles', __name__, url_prefix='/api/v2/roles')


# Default roles with their permissions
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


@bp.route('', methods=['GET'])
@require_auth()
def list_roles():
    """List all available roles"""
    roles = []
    for role_id, role_data in DEFAULT_ROLES.items():
        roles.append({
            'id': role_id,
            **role_data
        })
    return jsonify({'data': roles})


@bp.route('/<role_id>', methods=['GET'])
@require_auth()
def get_role(role_id):
    """Get role details"""
    if role_id not in DEFAULT_ROLES:
        return jsonify({'error': True, 'message': 'Role not found'}), 404
    
    role = DEFAULT_ROLES[role_id]
    return jsonify({
        'data': {
            'id': role_id,
            **role
        }
    })


@bp.route('/<role_id>/permissions', methods=['GET'])
@require_auth()
def get_role_permissions(role_id):
    """Get permissions for a role"""
    if role_id not in DEFAULT_ROLES:
        return jsonify({'error': True, 'message': 'Role not found'}), 404
    
    return jsonify({
        'data': DEFAULT_ROLES[role_id]['permissions']
    })


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
