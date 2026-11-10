"""Page to come back to after an SSO login: the rule of frontend `safeNext`, server side."""
import re

# Module paths and redirect sources of frontend/src/navigation/registry.js (a test keeps them equal).
KNOWN_PATHS = (
    '/', '/dashboard', '/certificates', '/certificates/:id', '/cas', '/cas/:id', '/csrs',
    '/templates', '/ssh/cas', '/ssh/certificates', '/acme', '/scep-config', '/est-config',
    '/tsa-config', '/crl-ocsp', '/truststore', '/truststore/:id', '/operations', '/tools',
    '/policies', '/approvals', '/key-recovery', '/reports', '/discovery', '/users', '/rbac',
    '/hsm', '/audit', '/logs', '/user-certificates', '/settings', '/account',
    '/import', '/groups', '/sso', '/security',
)
NEVER_BACK = ('/login', '/forgot-password', '/reset-password')
MAX_LENGTH = 512

# One leading slash not followed by `/` or `\`, then printable ASCII without space or `\`.
_SHAPE = re.compile(r'/(?![/\\])[\x21-\x5b\x5d-\x7e]*')
_KNOWN = tuple(re.compile(re.sub(r':[^/]+', '[^/]+', p)) for p in KNOWN_PATHS)


def safe_next(raw):
    """``raw`` when it is an internal path the application knows, else None."""
    if not isinstance(raw, str) or len(raw) > MAX_LENGTH or not _SHAPE.fullmatch(raw):
        return None
    path = re.split(r'[?#]', raw, maxsplit=1)[0]
    if '%' in path:
        return None
    if any(path == p or path.startswith(p + '/') for p in NEVER_BACK):
        return None
    clean = path.rstrip('/') if len(path) > 1 else path
    return raw if any(k.fullmatch(clean) for k in _KNOWN) else None
