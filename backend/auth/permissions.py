"""
Role-based permissions for UCM
"""

# Role permissions mapping — format: action:resource (matches @require_auth decorators)
ROLE_PERMISSIONS = {
    'admin': ['*'],  # Full access
    'operator': [
        'read:certificates', 'write:certificates',
        'read:user_certificates', 'write:user_certificates', 'delete:user_certificates',
        'read:cas', 'write:cas',
        'read:csrs', 'write:csrs', 'delete:csrs',
        'read:templates',
        'read:truststore', 'write:truststore',
        'read:crl', 'write:crl',
        'read:acme', 'write:acme', 'delete:acme',
        'read:scep',
        'read:est',
        'read:hsm',
        'read:ssh', 'write:ssh', 'delete:ssh',
        'read:policies', 'read:approvals', 'write:approvals',
        'read:key_recovery', 'write:key_recovery',
        'read:audit',
        'read:settings', 'write:settings',
        'read:groups', 'write:groups',
    ],
    'auditor': [
        'read:certificates',
        'read:user_certificates',
        'read:cas',
        'read:csrs',
        'read:templates',
        'read:truststore',
        'read:crl',
        'read:acme',
        'read:scep',
        'read:est',
        'read:hsm',
        'read:ssh',
        'read:policies', 'read:approvals',
        'read:audit',
        'read:groups',
    ],
    'viewer': [
        'read:certificates',
        'read:user_certificates',
        'read:cas',
        'read:csrs',
        'read:templates',
        'read:truststore',
        'read:ssh',
    ]
}


# Resources enforced by @require_auth but reachable ONLY through the '*' (admin) wildcard,
# so they never appear in a named role's explicit scope list in ROLE_PERMISSIONS above.
# They must still be scope-able on an API key (e.g. an admin minting a key for user
# management or SSO config), so they're unioned into VALID_RESOURCES below. Keep in sync
# with @require_auth usage — tests/test_apikey_valid_resources.py fails if a new enforced
# scope is added without registering its resource here (or granting it to a role above).
ADMIN_ONLY_RESOURCES = {'users', 'system', 'sso'}

# Canonical set of resources an API key can be scoped to: every resource granted to a role
# in ROLE_PERMISSIONS PLUS the admin-only resources above. Derived from these sources of
# truth so this validator can't silently drift from the `action:resource` scopes that
# @require_auth actually enforces (the previous hardcoded list had drifted — it was missing
# csrs/user_certificates/templates/... — and deriving from ROLE_PERMISSIONS alone dropped
# the admin-only users/system/sso resources).
VALID_RESOURCES = sorted(
    {perm.split(':', 1)[1]
     for perms in ROLE_PERMISSIONS.values()
     for perm in perms
     if ':' in perm}
    | ADMIN_ONLY_RESOURCES
)


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
