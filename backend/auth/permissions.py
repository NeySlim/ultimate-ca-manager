"""
Role-based permissions for UCM
"""

# Role permissions mapping
ROLE_PERMISSIONS = {
    'admin': ['*'],  # Full access
    'operator': [
        'certificates:read', 'certificates:write', 'certificates:delete',
        'csrs:read', 'csrs:write', 'csrs:delete',
        'templates:read',
        'cas:read',
        'dashboard:read',
        'settings:read',
    ],
    'viewer': [
        'certificates:read',
        'csrs:read',
        'templates:read',
        'cas:read',
        'dashboard:read',
    ]
}


def get_role_permissions(role: str) -> list:
    """Get permissions for a role"""
    return ROLE_PERMISSIONS.get(role, [])


def has_permission(user_role: str, required_permission: str) -> bool:
    """Check if a role has a specific permission"""
    permissions = get_role_permissions(user_role)
    
    # Admin has full access
    if '*' in permissions:
        return True
    
    # Check exact match
    if required_permission in permissions:
        return True
    
    # Check wildcard patterns (e.g., 'certificates:*')
    resource, action = required_permission.split(':') if ':' in required_permission else (required_permission, '*')
    
    for perm in permissions:
        if perm == f'{resource}:*':
            return True
        if perm == '*:read' and action == 'read':
            return True
    
    return False


def require_permission(permission: str):
    """Decorator to require a specific permission"""
    from functools import wraps
    from flask import g, jsonify
    
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not hasattr(g, 'current_user') or not g.current_user:
                return jsonify({'error': 'Unauthorized', 'message': 'Authentication required'}), 401
            
            user_role = g.current_user.role
            if not has_permission(user_role, permission):
                return jsonify({
                    'error': 'Forbidden',
                    'message': f'Permission required: {permission}'
                }), 403
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
