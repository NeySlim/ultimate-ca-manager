"""
Unified Authentication Manager v3.0
Supports: Session Cookies, API Keys

SIMPLE, ROBUST, TESTABLE
"""

import hashlib
import secrets
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify, g, session, current_app

# Import models (will be created)
try:
    from models import User, db
    from models.api_key import APIKey
except ImportError:
    # For testing without full app
    APIKey = None
    User = None
    db = None


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
        Priority: API Key → Session Cookie
        
        Returns:
            dict: User info with permissions, or None if not authenticated
        """
        # 1. Check API Key (highest priority)
        api_key = request_obj.headers.get('X-API-Key')
        if api_key:
            result = self.verify_api_key(api_key)
            if result:
                return result
        
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
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None
        
        # Update last_used timestamp
        api_key.last_used_at = datetime.utcnow()
        db.session.commit()
        
        # Parse permissions from JSON
        try:
            permissions = json.loads(api_key.permissions)
        except:
            permissions = []
        
        return {
            'user_id': api_key.user_id,
            'user': api_key.user,
            'auth_method': 'api_key',
            'permissions': permissions,
            'api_key_id': api_key.id,
            'api_key_name': api_key.name
        }
    
    def verify_session(self):
        """
        Verify Flask session
        
        Returns:
            dict: User info, or None
        """
        if not User:
            return None
        
        user_id = session.get('user_id')
        if not user_id:
            return None
        
        user = User.query.get(user_id)
        if not user or not user.active:
            return None
        
        return {
            'user_id': user.id,
            'user': user,
            'auth_method': 'session',
            'permissions': ['*'],  # Session = full access
            'session_expires': session.get('expires_at')
        }
    
    def create_api_key(self, user_id, name, permissions, expires_days=365):
        """
        Create new API key
        
        Args:
            user_id: User ID
            name: Friendly name for the key
            permissions: List of permissions (e.g., ['read:cas', 'write:certificates'])
            expires_days: Days until expiration
        
        Returns:
            dict: API key info (key is shown ONLY ONCE!)
        """
        if not APIKey:
            raise Exception("APIKey model not available")
        
        # Generate secure random key
        key = f"ucm_ak_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(key.encode()).hexdigest()
        
        # Create API key record
        api_key = APIKey(
            user_id=user_id,
            key_hash=key_hash,
            name=name,
            permissions=json.dumps(permissions),
            expires_at=datetime.utcnow() + timedelta(days=expires_days)
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        # Return key - ONLY TIME WE SHOW IT!
        return {
            'key': key,  # ⚠️ Store this! We won't show it again
            'id': api_key.id,
            'name': name,
            'permissions': permissions,
            'created_at': api_key.created_at.isoformat(),
            'expires_at': api_key.expires_at.isoformat()
        }
    


def create_session_for_user(user):
    """
    Helper function to establish a session for a user.
    Used by SSO callback to establish session.
    
    Args:
        user: User model instance
    
    Returns:
        dict: {'user': dict}
    """
    session['user_id'] = user.id
    session['username'] = user.username
    session['login_time'] = datetime.utcnow().isoformat()
    session.permanent = True
    session.modified = True
    
    return {
        'user': user.to_dict() if hasattr(user, 'to_dict') else {'id': user.id, 'username': user.username}
    }


def require_auth(permissions=None):
    """
    Decorator to protect routes with authentication
    Supports: Session, JWT, API Key (auto-detected)
    
    Args:
        permissions: Optional list of required permissions
                    Examples: ['read:cas'], ['write:certificates', 'read:cas']
    
    Usage:
        @require_auth()  # Any authenticated user
        @require_auth(['read:cas'])  # Need specific permission
        @require_auth(['write:certificates'])  # Need write access
    """
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Initialize auth manager
            auth_manager = AuthManager()
            
            # Authenticate request
            auth_result = auth_manager.authenticate_request(request)
            
            if not auth_result:
                return jsonify({
                    'error': 'Unauthorized',
                    'message': 'Authentication required'
                }), 401
            
            # Check permissions if specified
            if permissions:
                user_perms = auth_result['permissions']
                
                # Wildcard check - '*' means all permissions
                if '*' not in user_perms:
                    # Check each required permission
                    for perm in permissions:
                        if not has_permission(perm, user_perms):
                            return jsonify({
                                'error': 'Forbidden',
                                'message': f'Missing permission: {perm}',
                                'required': perm,
                                'has': user_perms
                            }), 403
            
            # Inject auth info into Flask's g object
            g.current_user = auth_result['user']
            g.auth_method = auth_result['auth_method']
            g.permissions = auth_result['permissions']
            g.user_id = auth_result['user_id']
            
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
