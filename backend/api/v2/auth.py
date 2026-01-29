"""
Authentication Routes v2.0
/api/auth/* - Login, Logout, Verify

Supports:
- Session cookies (web UI)
- JWT tokens (external APIs)
"""

from flask import Blueprint, request, jsonify, session, current_app
from auth.unified import AuthManager, require_auth, require_permission
from utils.response import success_response, error_response
from models import User, db
from datetime import datetime
import hashlib

bp = Blueprint('auth_v2', __name__)

# Import limiter for rate limiting login attempts
try:
    from app import limiter
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False

# Track failed login attempts for account lockout
_failed_attempts = {}  # {username: {'count': int, 'locked_until': datetime}}
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


def _check_account_lockout(username):
    """Check if account is locked due to failed attempts"""
    if username not in _failed_attempts:
        return False
    
    info = _failed_attempts[username]
    if info.get('locked_until'):
        if datetime.utcnow() < info['locked_until']:
            return True
        else:
            # Lockout expired, reset
            del _failed_attempts[username]
            return False
    return False


def _record_failed_attempt(username):
    """Record a failed login attempt"""
    if username not in _failed_attempts:
        _failed_attempts[username] = {'count': 0, 'locked_until': None}
    
    _failed_attempts[username]['count'] += 1
    
    if _failed_attempts[username]['count'] >= MAX_FAILED_ATTEMPTS:
        from datetime import timedelta
        _failed_attempts[username]['locked_until'] = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
        current_app.logger.warning(f"Account locked for {username} after {MAX_FAILED_ATTEMPTS} failed attempts")
        
        # Send security alert notification
        try:
            from services.notification_service import NotificationService
            ip_address = request.remote_addr or 'unknown'
            NotificationService.on_security_alert(
                event_type='account_locked',
                username=username,
                ip_address=ip_address
            )
        except Exception:
            pass  # Non-blocking


def _clear_failed_attempts(username):
    """Clear failed attempts on successful login"""
    if username in _failed_attempts:
        del _failed_attempts[username]


@bp.route('/api/v2/auth/login', methods=['POST'])
def login():
    """
    Login endpoint - Rate limited to 5 per minute
    Supports 2 modes based on Accept header:
    - Default: Returns session cookie
    - Accept: application/jwt → Returns JWT token
    
    POST /api/auth/login
    Body: {"username": "admin", "password": "xxx"}
    """
    # Apply rate limiting if available
    if HAS_LIMITER:
        try:
            limiter.limit("5 per minute")(lambda: None)()
        except Exception:
            pass  # Rate limit exceeded handled by limiter
    
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return error_response('Username and password required', 400)
    
    username = data['username'].strip()
    password = data['password']
    
    # SECURITY: Check account lockout
    if _check_account_lockout(username):
        return error_response('Account temporarily locked. Try again later.', 429)
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.active:
        _record_failed_attempt(username)
        return error_response('Invalid credentials', 401)
    
    # Verify password (assumes User has check_password method)
    if not user.check_password(password):
        _record_failed_attempt(username)
        return error_response('Invalid credentials', 401)
    
    # Clear failed attempts on success
    _clear_failed_attempts(username)
    
    # Check if JWT requested
    accept_header = request.headers.get('Accept', '')
    wants_jwt = 'application/jwt' in accept_header
    
    if wants_jwt:
        # Return JWT token
        auth_manager = AuthManager()
        token_info = auth_manager.create_jwt(user.id)
        
        return success_response(
            data={
                'token': token_info['token'],
                'expires_in': token_info['expires_in'],
                'expires_at': token_info['expires_at'],
                'user': {
                    'id': user.id,
                    'username': user.username
                }
            },
            message='Login successful'
        )
    
    else:
        # SECURITY: Regenerate session ID to prevent session fixation
        session.clear()
        
        # Create new session with regenerated ID
        session['user_id'] = user.id
        session['username'] = user.username
        session['login_time'] = datetime.utcnow().isoformat()
        session.permanent = True
        session.modified = True
        
        # Log successful login
        current_app.logger.info(f"✅ User {user.username} logged in successfully")
        
        return success_response(
            data={
                'user': {
                    'id': user.id,
                    'username': user.username
                }
            },
            message='Login successful'
        )


@bp.route('/api/v2/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """
    Logout endpoint
    Clears session (for session-based auth)
    """
    session.clear()
    
    return success_response(message='Logout successful')


@bp.route('/api/v2/auth/verify', methods=['GET'])
def verify():
    """
    Verify current authentication
    Returns user info and auth method
    
    Useful for:
    - Checking if token is still valid
    - Getting current user info
    - Determining auth method used
    """
    from flask import g
    from auth.unified import verify_request_auth
    
    # Manually verify auth to handle unauthenticated state gracefully
    auth_result = verify_request_auth()
    
    if not auth_result:
        # Check for mTLS certificate error in request context (set by middleware)
        cert_error = getattr(g, 'cert_error', None)
        
        return jsonify({
            'status': 'success',
            'data': {
                'authenticated': False,
                'cert_error': cert_error
            }
        }), 200
    
    # If authenticated
    return success_response(
        data={
            'authenticated': True,
            'user_id': g.user_id,
            'auth_method': g.auth_method,
            'permissions': g.permissions,
            'user': {
                'id': g.current_user.id,
                'username': g.current_user.username
            }
        }
    )


@bp.route('/api/v2/auth/refresh', methods=['POST'])
@require_auth()
def refresh_token():
    """
    Refresh JWT token
    Only works with JWT auth (not session or API key)
    """
    from flask import g
    
    if g.auth_method != 'jwt':
        return error_response(
            'Refresh only available for JWT tokens',
            400,
            {'current_method': g.auth_method}
        )
    
    # Create new token
    auth_manager = AuthManager()
    token_info = auth_manager.create_jwt(g.user_id)
    
    return success_response(
        data={
            'token': token_info['token'],
            'expires_in': token_info['expires_in'],
            'expires_at': token_info['expires_at']
        },
        message='Token refreshed'
    )
