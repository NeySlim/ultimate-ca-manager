"""
Role-based permissions for UCM
"""

# Role permissions mapping — format: action:resource (matches @require_auth decorators)
ROLE_PERMISSIONS = {
    'admin': ['*'],  # Full access
    'operator': [
        'read:certificates', 'write:certificates', 'delete:certificates',
        'read:cas', 'write:cas',
        'read:csrs', 'write:csrs', 'delete:csrs',
        'read:templates',
        'read:truststore', 'write:truststore',
        'read:crl', 'write:crl',
        'read:acme', 'write:acme',
        'read:scep',
        'read:hsm',
        'read:policies', 'read:approvals', 'write:approvals',
        'read:audit',
        'read:settings',
        'read:groups',
    ],
    'viewer': [
        'read:certificates',
        'read:cas',
        'read:csrs',
        'read:templates',
        'read:truststore',
        'read:crl',
        'read:acme',
        'read:scep',
        'read:hsm',
        'read:policies', 'read:approvals',
        'read:audit',
        'read:groups',
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
    
    # Check wildcard patterns (e.g., 'read:*' or 'write:*')
    parts = required_permission.split(':') if ':' in required_permission else [required_permission, '*']
    action, resource = parts[0], parts[1] if len(parts) > 1 else '*'
    
    for perm in permissions:
        if perm == f'{action}:*':
            return True
        if perm == f'*:{resource}':
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
