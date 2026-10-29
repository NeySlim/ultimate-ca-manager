"""
Role-based permissions for UCM
"""
import logging

logger = logging.getLogger(__name__)

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
        'read:xcep',
        'read:wstep',
        'read:kerberos',
        'read:ad_connector',
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
        'read:xcep',
        'read:wstep',
        'read:kerberos',
        'read:ad_connector',
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


# The built-in role names, which are exactly the keys above: a role is
# built in because this table says what it may do.
#
# Three other modules restated this list and two dropped `auditor`. The CSV
# user import checked against the short list and silently rewrote anything
# else to `viewer`, so a file of auditors became viewers with no error -- and
# `viewer` has no `read:audit`, so the accounts made for people who audit
# could not read the audit log. `api/v2/rbac.RESERVED_ROLE_NAMES` dropped it
# too, leaving `auditor` available as the name of a *custom* role beside the
# built-in one.
BUILTIN_ROLES = tuple(ROLE_PERMISSIONS)


# Resources enforced by @require_auth but reachable ONLY through the '*' (admin) wildcard,
# so they never appear in a named role's explicit scope list in ROLE_PERMISSIONS above.
# They must still be scope-able on an API key (e.g. an admin minting a key for user
# management or SSO config), so they're unioned into VALID_RESOURCES below. Keep in sync
# with @require_auth usage — tests/test_apikey_valid_resources.py fails if a new enforced
# scope is added without registering its resource here (or granting it to a role above).
ADMIN_ONLY_RESOURCES = {'users', 'system', 'sso', 'private_keys', 'deploy'}

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


# Permissions a group may grant. Derived from ROLE_PERMISSIONS so a group can
# only hand out scopes that @require_auth actually enforces — an earlier
# hardcoded list had drifted (it offered `read:certs` while every endpoint
# requires `read:certificates`, so those grants could never have matched).
# `admin:*` and the `*` wildcard are deliberately excluded: group membership
# must never be a path to administrator.
GROUP_GRANTABLE_PERMISSIONS = sorted(
    {perm
     for perms in ROLE_PERMISSIONS.values()
     for perm in perms
     if ':' in perm and not perm.startswith('admin:')}
)


# Every scope @require_auth checks, recorded as routes are declared.
ENFORCED_PERMISSIONS = set()

# Scopes checked inline with has_permission() rather than by the decorator.
INLINE_CHECKED_PERMISSIONS = frozenset({
    'admin:key_recovery', 'admin:settings', 'admin:system', 'read:audit',
    'read:cas', 'read:certificates', 'read:deploy', 'read:private_keys', 'read:system',
    'read:users', 'write:approvals', 'write:cas',
})

# Kept for administrators, beyond `*`, wildcards and every `admin:*` action.
RESERVED_PERMISSIONS = {
    'write:users': 'creates accounts and resets passwords: takes over any account',
    'delete:users': 'removes accounts, administrators included',
    'read:sso': 'shows identity provider settings and every SSO session',
    'write:sso': 'decides which external identity signs in as which account',
    'delete:sso': 'removes the sign-in path of SSO accounts',
    'read:deploy': 'shows remote targets and how UCM reaches them',
    'write:deploy': 'runs commands and pushes private keys on remote hosts',
    'delete:deploy': 'removes deployments other services rely on',
    'read:system': 'receives system-wide events over the WebSocket',
    'delete:audit': 'erases the audit trail',
    'write:ad_connector': 'handles the bind secret of the AD service account',
    'write:hsm': 'loads native PKCS#11 modules into the UCM process',
}


def is_reserved_permission(perm) -> bool:
    """True for what only an administrator may hold."""
    return (not isinstance(perm, str) or '*' in perm
            or perm.split(':', 1)[0] == 'admin' or perm in RESERVED_PERMISSIONS)


# What a custom role may grant: every scope a route checks that is not reserved.
# tests/test_custom_role_grantable.py fails when a new scope is left unclassified.
CUSTOM_ROLE_GRANTABLE_PERMISSIONS = sorted({
    'read:acme', 'write:acme', 'delete:acme',
    'read:ad_connector',
    'read:approvals', 'write:approvals',
    'read:audit', 'export:audit',
    'read:cas', 'write:cas', 'delete:cas',
    'read:certificates', 'write:certificates', 'delete:certificates',
    'read:crl', 'write:crl',
    'read:csrs', 'write:csrs', 'delete:csrs',
    'read:est', 'write:est',
    'read:groups', 'write:groups', 'delete:groups',
    'read:hsm', 'delete:hsm',
    'read:kerberos', 'write:kerberos',
    'read:key_recovery', 'write:key_recovery',
    'read:policies', 'write:policies', 'delete:policies',
    'read:private_keys',
    'read:scep', 'write:scep',
    'read:settings', 'write:settings', 'delete:settings',
    'read:ssh', 'write:ssh', 'delete:ssh',
    'read:templates', 'write:templates', 'delete:templates',
    'read:truststore', 'write:truststore', 'delete:truststore',
    'read:user_certificates', 'write:user_certificates', 'delete:user_certificates',
    'read:users',
    'read:wstep', 'write:wstep',
    'read:xcep', 'write:xcep',
})

# Resource names the role editor used to store, read as the enforced ones.
_LEGACY_RESOURCE_ALIASES = {'certs': 'certificates'}


def normalize_permission(perm):
    """``read:certs`` -> ``read:certificates``; anything else unchanged."""
    if not isinstance(perm, str) or ':' not in perm:
        return perm
    action, resource = perm.split(':', 1)
    return f"{action}:{_LEGACY_RESOURCE_ALIASES.get(resource, resource)}"


MAX_ROLE_DEPTH = 64


def custom_role_chain(role):
    """``role`` then its ancestors; stops at a cycle, a missing parent or 64 levels."""
    chain, seen = [], set()
    while role is not None and role.id not in seen and len(chain) < MAX_ROLE_DEPTH:
        seen.add(role.id)
        chain.append(role)
        role = role.parent
    return chain


def custom_role_permissions(role) -> list:
    """Grantable permissions of ``role`` and the roles it inherits from."""
    grantable = set(CUSTOM_ROLE_GRANTABLE_PERMISSIONS)
    granted = []
    for link in custom_role_chain(role):
        for perm in (link.permissions or []):
            perm = normalize_permission(perm)
            if perm in grantable and perm not in granted:
                granted.append(perm)
    return granted


def get_custom_role_permissions(user) -> list:
    """Permissions granted to ``user`` by the custom role assigned to them.

    Filtered on read like group grants; never raises.
    """
    role_id = getattr(user, 'custom_role_id', None)
    if user is None or not role_id:
        return []
    try:
        from models import db
        from models.rbac import CustomRole
        return custom_role_permissions(db.session.get(CustomRole, role_id))
    except Exception as e:  # noqa: BLE001: authorisation must not 500 on this
        logger.warning(f"Could not resolve custom role permissions for user {getattr(user, 'id', '?')}: {e}")
        return []


def get_role_permissions(role: str) -> list:
    """Get permissions for a role"""
    return ROLE_PERMISSIONS.get(role, [])


def get_group_permissions(user) -> list:
    """Permissions granted to ``user`` through group membership.

    Filtered against GROUP_GRANTABLE_PERMISSIONS on read as well as on write:
    a permission that reached the database by another route (restore of an old
    backup, direct SQL) still cannot confer more than a group is allowed to.
    Never raises — an unavailable group table degrades to "no extra rights".
    """
    if user is None or getattr(user, 'id', None) is None:
        return []
    try:
        from models.group import Group, GroupMember, permission_list

        rows = (Group.query
                .join(GroupMember, GroupMember.group_id == Group.id)
                .filter(GroupMember.user_id == user.id)
                .with_entities(Group.permissions)
                .all())
    except Exception as e:  # noqa: BLE001 — authorisation must not 500 on this
        logger.warning(f"Could not resolve group permissions for user {getattr(user, 'id', '?')}: {e}")
        return []

    grantable = set(GROUP_GRANTABLE_PERMISSIONS)
    granted = []
    for (perms,) in rows:
        for perm in permission_list(perms):
            if perm in grantable and perm not in granted:
                granted.append(perm)
    return granted


def get_effective_permissions(user) -> list:
    """Built-in role, unioned with the user's custom role and groups.

    This is what authorisation and the login response must both use, so the UI
    gates on exactly what the API enforces.
    """
    perms = list(get_role_permissions(getattr(user, 'role', None)))
    if '*' in perms:
        return perms  # administrator: nothing to add
    for extra in (get_custom_role_permissions(user), get_group_permissions(user)):
        perms += [p for p in extra if p not in perms]
    return perms


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
            from utils.response import error_response
            if not hasattr(g, 'current_user') or not g.current_user:
                return error_response('Authentication required', 401)

            user_role = g.current_user.role
            if not has_permission(user_role, permission):
                return error_response(f'Permission required: {permission}', 403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
