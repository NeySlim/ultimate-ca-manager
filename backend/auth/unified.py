"""
Unified Authentication Manager v3.0
Supports: Session Cookies, API Keys

SIMPLE, ROBUST, TESTABLE
"""

import hashlib
import logging
import secrets
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g, session, current_app
from utils.datetime_utils import utc_now, utc_isoformat
from utils.db_transaction import commit_or_rollback

# Import models (will be created)
try:
    from models import User, db
    from models.api_key import APIKey
except ImportError:
    # For testing without full app
    APIKey = None
    User = None
    db = None

logger = logging.getLogger(__name__)


# Every UCM API key starts with it; a bearer token without it is not ours.
API_KEY_PREFIX = 'ucm_ak_'


def presented_api_key(request_obj):
    """API key from ``X-API-Key``, or from ``Authorization: Bearer`` when the token
    carries the UCM key prefix; any other bearer token (an IdP token relayed by an
    authenticating proxy) is ignored."""
    key = (request_obj.headers.get('X-API-Key') or '').strip()
    if key:
        return key
    scheme, _, token = (request_obj.headers.get('Authorization') or '').partition(' ')
    token = token.strip()
    if scheme.lower() == 'bearer' and token.startswith(API_KEY_PREFIX):
        return token
    return None


class AuthManager:
    """
    Unified Authentication Manager
    Handles: Sessions, API Keys
    """
    
    def __init__(self):
        """Initialize auth manager"""
        pass
    
    def authenticate_request(self, request_obj):
        """
        Auto-detect and authenticate request
        Priority: API Key (X-API-Key or Bearer) → Session Cookie
        
        Returns:
            dict: User info with permissions, or None if not authenticated
        """
        # 1. API key (highest priority). A key that fails is refused outright:
        # its header skipped CSRF, so it must not fall back to the session.
        api_key = presented_api_key(request_obj)
        if api_key:
            return self.verify_api_key(api_key)
        
        # 2. Check Session Cookie (Flask session)
        if 'user_id' in session:
            result = self.verify_session()
            if result:
                return result
        
        return None
    
    def verify_api_key(self, key):
        """
        Verify API key and return user info
        
        Args:
            key: API key string (ucm_ak_...)
        
        Returns:
            dict: User info with permissions, or None
        """
        if not APIKey or not User:
            return None
        
        # Hash the key
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        # Find API key in database
        api_key = APIKey.query.filter_by(
            key_hash=key_hash,
            is_active=True
        ).first()
        
        if not api_key:
            return None
        
        # Check expiration
        if api_key.expires_at and api_key.expires_at < utc_now():
            return None
        
        # Reject if the linked user is missing or deactivated. Without this,
        # API keys belonging to a disabled user remain valid until the key
        # itself is revoked.
        linked_user = api_key.user
        if not linked_user or not getattr(linked_user, 'active', False):
            return None
        
        # last_used is telemetry: a lock its write swallows is not the request's
        from utils.sqlite_wait import lock_not_marked
        api_key.last_used_at = utc_now()
        with lock_not_marked():
            commit_or_rollback(logger, "Failed to update api_key.last_used_at")
        
        # Parse permissions from JSON
        try:
            permissions = json.loads(api_key.permissions)
        except Exception:
            permissions = []

        # Re-bind the key's scopes to the owner's CURRENT effective permissions.
        # The stored list is a snapshot from mint time, so without this a key
        # minted while its owner was an admin/operator keeps those scopes after
        # the owner is demoted (e.g. to viewer) — privilege that outlives the
        # role change. A key may narrow what its owner can do, never widen it.
        from auth.permissions import get_effective_permissions
        owner_permissions = get_effective_permissions(linked_user)
        if '*' not in owner_permissions:
            if '*' in permissions:
                # A wildcard key is worth exactly its owner's current scopes.
                permissions = list(owner_permissions)
            else:
                # Category wildcards ('read:*', 'write:*' — the shapes the UI's
                # scope presets mint) expand to the owner's current scopes in
                # that category, symmetric with the bare-'*' branch above.
                # Filtering them through has_permission() alone would drop them
                # entirely, because named roles hold only concrete scopes: a
                # demoted admin's ['read:*'] key would authenticate with NO
                # permissions even though the owner legitimately retains
                # read:cas, read:certificates, etc.
                rebound = []
                for perm in permissions:
                    if ':' in perm and perm.endswith(':*'):
                        category = perm.split(':', 1)[0]
                        matched = [
                            p for p in owner_permissions
                            if p == perm or p.split(':', 1)[0] == category
                        ]
                    elif has_permission(perm, owner_permissions):
                        matched = [perm]
                    else:
                        matched = []
                    for p in matched:
                        if p not in rebound:
                            rebound.append(p)
                permissions = rebound

        return {
            'user_id': api_key.user_id,
            'user': api_key.user,
            'auth_method': 'api_key',
            'permissions': permissions,
            'api_key_id': api_key.id,
            'api_key_name': api_key.name,
            'api_key_expires_at': api_key.expires_at
        }
    
    def verify_session(self):
        """
        Verify Flask session with inactivity + absolute lifetime checks.
        
        Returns:
            dict: User info, or None if session is invalid/expired
        """
        if not User:
            return None
        
        user_id = session.get('user_id')
        if not user_id:
            return None
        # A locked session opens nothing, and stays as it is until unlocked or signed out
        from auth.session_lock import is_locked
        if is_locked():
            return None
        
        user = db.session.get(User, user_id)
        if not user or not user.active:
            return None

        from auth.session_start import session_is_current
        if not session_is_current(user):
            logger.info(f"Session closed by a credential change: user={user.username}")
            session.clear()
            return None

        now = utc_now()
        if self.session_ended(session, now, label=user.username):
            session.clear()
            return None

        # Update last activity timestamp
        session['last_activity'] = now.isoformat()
        
        from auth.permissions import get_effective_permissions
        permissions = get_effective_permissions(user)
        
        return {
            'user_id': user.id,
            'user': user,
            'auth_method': 'session',
            'permissions': permissions,
            'session_expires': session.get('expires_at')
        }
    
    @classmethod
    def session_ended(cls, data, now, label='', limits=None, log=True):
        """Whether the session ``data`` is past its maximum lifetime or its inactivity
        timeout at ``now``; ``limits`` = (max lifetime, inactivity timeout) in seconds."""
        max_lifetime, inactivity_timeout = limits or cls.session_limits()
        for key, limit, reason, name in (('login_time', max_lifetime, 'max lifetime', 'max'),
                                         ('last_activity', inactivity_timeout, 'inactivity',
                                          'timeout')):
            value = data.get(key)
            if not value:
                continue
            try:
                if (now - datetime.fromisoformat(value)).total_seconds() > limit:
                    if log:
                        logger.info(f"Session expired ({reason}): user={label}, {key}={value}, "
                                    f"{name}={limit}s")
                    return True
            except (ValueError, TypeError) as e:
                if log:
                    logger.warning(f"Malformed session {key}={value!r} for user={label}: {e}")
        return False

    @classmethod
    def session_limits(cls):
        return cls._get_session_max_lifetime(), cls._get_session_timeout()

    @staticmethod
    def _get_session_timeout():
        """Get inactivity timeout in seconds from DB config (default 8h = 28800s)"""
        try:
            from models import SystemConfig
            config = SystemConfig.query.filter_by(key='session_timeout').first()
            if config and config.value:
                return int(config.value)
        except Exception as e:
            logger.warning(f"Failed to read session_timeout from SystemConfig, using 8h default: {e}")
        return 28800  # 8 hours default
    
    @staticmethod
    def _get_session_max_lifetime():
        """Get absolute max session lifetime in seconds from DB config (default 24h = 86400s)"""
        try:
            from models import SystemConfig
            config = SystemConfig.query.filter_by(key='session_max_lifetime').first()
            if config and config.value:
                return int(config.value)
        except Exception as e:
            logger.warning(f"Failed to read session_max_lifetime from SystemConfig, using 24h default: {e}")
        return 86400  # 24 hours default
    
    def create_api_key(self, user_id, name, permissions, expires_days=365, not_after=None):
        """
        Create new API key

        Args:
            user_id: User ID
            name: Friendly name for the key
            permissions: List of permissions (e.g., ['read:cas', 'write:certificates'])
            expires_days: Days until expiration. Pass ``None`` or ``0`` for a
                key that never expires.
            not_after: Latest expiry allowed, e.g. that of the key asking.

        Returns:
            dict: API key info (key is shown ONLY ONCE!)
        """
        if not APIKey:
            raise Exception("APIKey model not available")

        # Generate secure random key
        key = f"{API_KEY_PREFIX}{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        # First 12 chars are enough to identify a key in the UI
        # (e.g. 'ucm_ak_AbC1') without revealing it.
        key_prefix = key[:12]

        # ``None`` or ``0`` => no expiration
        if expires_days in (None, 0):
            expires_at = None
        else:
            expires_at = utc_now() + timedelta(days=int(expires_days))
        if not_after is not None and (expires_at is None or expires_at > not_after):
            expires_at = not_after

        # Create API key record
        api_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            permissions=json.dumps(permissions),
            expires_at=expires_at
        )

        db.session.add(api_key)
        if not commit_or_rollback(logger, "Failed to create api_key"):
            raise RuntimeError("Failed to persist API key, see logs")

        # Return key - ONLY TIME WE SHOW IT!
        return {
            'key': key,  # ⚠️ Store this! We won't show it again
            'id': api_key.id,
            'name': name,
            'key_prefix': key_prefix,
            'permissions': permissions,
            'created_at': utc_isoformat(api_key.created_at),
            'expires_at': utc_isoformat(api_key.expires_at)
        }
    


def refuse_api_key_on_own_account(user_id):
    """403 when an API key reaches its owner's own account through an admin
    route, which would undo ``session_only`` on the account routes; else None."""
    if getattr(g, 'auth_method', None) == 'api_key' and g.current_user.id == user_id:
        return jsonify({
            'error': 'Forbidden',
            'message': 'This operation requires an interactive session'
        }), 403
    return None


def require_auth(permissions=None, session_only=False, any_of=False):
    """
    Decorator to protect routes with authentication
    Supports: Session, JWT, API Key (auto-detected)
    
    Args:
        permissions: Optional list of required permissions
                    Examples: ['read:cas'], ['write:certificates', 'read:cas']
        session_only: refuse API keys; for routes that change how the
                    account signs in, whatever scopes the key holds
        any_of: one of the permissions suffices instead of all of them
    
    Usage:
        @require_auth()  # Any authenticated user
        @require_auth(['read:cas'])  # Need specific permission
        @require_auth(['write:certificates'])  # Need write access
    """
    def decorator(f):
        # Recorded so custom role validation knows every scope a route checks
        from auth.permissions import ENFORCED_PERMISSIONS
        ENFORCED_PERMISSIONS.update(permissions or [])

        @wraps(f)
        def wrapper(*args, **kwargs):
            # Initialize auth manager
            auth_manager = AuthManager()
            
            # Authenticate request
            auth_result = auth_manager.authenticate_request(request)
            
            if not auth_result:
                from auth import restore_hold
                restore_hold.forget()
                from auth.session_lock import locked_refusal, locks_this_request
                if locks_this_request():
                    return locked_refusal()
                from utils.response import error_response, AUTHENTICATION_REQUIRED_PROBLEM
                return error_response('Authentication required', 401,
                                      problem_type=AUTHENTICATION_REQUIRED_PROBLEM)
            if session_only and auth_result['auth_method'] != 'session':
                return jsonify({
                    'error': 'Forbidden',
                    'message': 'This operation requires an interactive session'
                }), 403

            # Forced-2FA-enrolment gate (#141): a session flagged for mandatory
            # enrolment may only reach the enrolment endpoints (and logout) until
            # TOTP is confirmed. Checked before permissions so an un-enrolled
            # session is uniformly blocked regardless of its permissions.
            from auth.twofa_enforcement import ENROLL_SESSION_KEY, ENROLL_ALLOWED_PATHS, PROMPT_READABLE_PATHS
            if session.get(ENROLL_SESSION_KEY) and request.path not in ENROLL_ALLOWED_PATHS \
                    and not (request.method == 'GET' and request.path in PROMPT_READABLE_PATHS):
                return jsonify({
                    'error': 'Forbidden',
                    'message': '2FA enrolment required',
                    'must_enroll_2fa': True
                }), 403

            from auth.password_change_gate import password_change_allows, password_change_pending
            if password_change_pending(auth_result) and not password_change_allows(request.path, request.method):
                return jsonify({
                    'error': 'Forbidden',
                    'message': 'Password change required',
                    'must_change_password': True
                }), 403

            # Check permissions if specified
            if permissions:
                user_perms = auth_result['permissions']
                
                # Wildcard check - '*' means all permissions
                held = [has_permission(perm, user_perms) for perm in permissions]
                if '*' not in user_perms and not (any(held) if any_of else all(held)):
                    return jsonify({
                        'error': 'Forbidden',
                        'message': 'Insufficient permissions'
                    }), 403
            
            # Inject auth info into Flask's g object
            g.current_user = auth_result['user']
            g.auth_method = auth_result['auth_method']
            g.permissions = auth_result['permissions']
            g.user_id = auth_result['user_id']
            g.api_key_id = auth_result.get('api_key_id')
            # Checked against the database during a restore's gate: kept for its held window
            from auth import restore_hold
            restore_hold.remember(auth_result)

            # Call the actual route function
            return f(*args, **kwargs)
        
        return wrapper
    return decorator


def has_permission(required, user_permissions):
    """
    Check if user has required permission
    Supports wildcards: 'write:*' matches 'write:cas'
    
    Args:
        required: Required permission (e.g., 'read:cas')
        user_permissions: List of user's permissions
    
    Returns:
        bool: True if user has permission
    """
    # Admin wildcard - '*' grants everything
    if '*' in user_permissions:
        return True
    
    # Exact match
    if required in user_permissions:
        return True
    
    # Wildcard match: 'write:*' matches 'write:cas'
    if ':' in required:
        category = required.split(':')[0]
        if f"{category}:*" in user_permissions:
            return True
    
    return False


def hsm_binding_refusal(authority):
    """403 naming read:hsm when the caller may not put *authority* ('an SSH CA', 'an X.509 CA')
    on an HSM key: binding a key takes the right to see the HSM inventory too. None otherwise."""
    if has_permission('read:hsm', getattr(g, 'permissions', None) or []):
        return None
    from utils.response import error_response
    return error_response(f'Creating {authority} on an HSM key requires the read:hsm permission', 403)


def verify_request_auth(request_obj=None):
    """
    Manually verify authentication without aborting with 401.
    Useful for 'check auth' endpoints that should return {authenticated: false} instead of error.
    
    Returns:
        dict: User info or None if not authenticated
    """
    if request_obj is None:
        request_obj = request
        
    auth_manager = AuthManager()
    result = auth_manager.authenticate_request(request_obj)
    
    if result:
        # Inject into g context if successful, just like require_auth
        g.current_user = result['user']
        g.auth_method = result['auth_method']
        g.permissions = result['permissions']
        g.user_id = result['user_id']
        return result
        
    return None


# Convenience function for testing
def mock_auth(user_id=1, permissions=None):
    """
    Mock authentication for testing
    Bypasses actual auth and sets g.current_user
    
    Usage:
        with app.test_request_context():
            mock_auth(user_id=1, permissions=['read:cas'])
            # Now g.current_user is set
    """
    class MockUser:
        def __init__(self, user_id):
            self.id = user_id
            self.is_active = True
    
    g.current_user = MockUser(user_id)
    g.auth_method = 'mock'
    g.permissions = permissions or ['*']
    g.user_id = user_id


def require_permission(permission):
    """
    Decorator to require a specific permission.
    Shorthand for @require_auth([permission])
    
    Usage:
        @require_permission('admin:groups')
        def create_group():
            ...
    """
    return require_auth([permission])
