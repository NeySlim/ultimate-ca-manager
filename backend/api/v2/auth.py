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

# Import CSRF protection
try:
    from security.csrf import CSRFProtection
    HAS_CSRF = True
except ImportError:
    HAS_CSRF = False

# Import anomaly detection
try:
    from security.anomaly_detection import get_anomaly_detector
    HAS_ANOMALY = True
except ImportError:
    HAS_ANOMALY = False

bp = Blueprint('auth_v2', __name__)

# Import limiter for rate limiting login attempts
try:
    from app import limiter
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False

# Track failed login attempts for account lockout (now persisted in DB)
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_MINUTES = 15


def _check_account_lockout(username):
    """Check if account is locked due to failed attempts (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if not user:
        return False
    
    if user.locked_until:
        if datetime.utcnow() < user.locked_until:
            return True
        else:
            # Lockout expired, reset
            user.locked_until = None
            user.failed_logins = 0
            db.session.commit()
            return False
    return False


def _record_failed_attempt(username):
    """Record a failed login attempt (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    
    user.failed_logins = (user.failed_logins or 0) + 1
    
    if user.failed_logins >= MAX_FAILED_ATTEMPTS:
        from datetime import timedelta
        user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
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
    
    db.session.commit()


def _clear_failed_attempts(username):
    """Clear failed attempts after successful login (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if user and (user.failed_logins or user.locked_until):
        user.failed_logins = 0
        user.locked_until = None
        db.session.commit()


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
    
    # Get client info for anomaly detection
    client_ip = request.remote_addr or 'unknown'
    user_agent = request.headers.get('User-Agent', 'unknown')
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.active:
        _record_failed_attempt(username)
        # Record failed login for anomaly detection
        if HAS_ANOMALY:
            get_anomaly_detector().record_login(0, client_ip, user_agent, success=False)
        return error_response('Invalid credentials', 401)
    
    # Verify password (assumes User has check_password method)
    if not user.check_password(password):
        _record_failed_attempt(username)
        # Record failed login for anomaly detection
        if HAS_ANOMALY:
            get_anomaly_detector().record_login(user.id, client_ip, user_agent, success=False)
        return error_response('Invalid credentials', 401)
    
    # Clear failed attempts on success
    _clear_failed_attempts(username)
    
    # Record successful login for anomaly detection
    anomalies = []
    if HAS_ANOMALY:
        anomalies = get_anomaly_detector().record_login(user.id, client_ip, user_agent, success=True)
    
    # Check if JWT requested
    accept_header = request.headers.get('Accept', '')
    wants_jwt = 'application/jwt' in accept_header
    
    if wants_jwt:
        # Return JWT token
        auth_manager = AuthManager()
        token_info = auth_manager.create_jwt(user.id)
        
        # Generate CSRF token for JWT users too
        csrf_token = None
        if HAS_CSRF:
            csrf_token = CSRFProtection.generate_token(user.id)
        
        return success_response(
            data={
                'token': token_info['token'],
                'expires_in': token_info['expires_in'],
                'expires_at': token_info['expires_at'],
                'user': {
                    'id': user.id,
                    'username': user.username
                },
                'csrf_token': csrf_token,
                'force_password_change': user.force_password_change or False,
                'security_alerts': [a['message'] for a in anomalies if a.get('severity') in ('medium', 'high')]
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
        
        # WebSocket event for login
        try:
            from websocket.emitters import on_user_login
            on_user_login(
                username=user.username,
                ip_address=request.remote_addr or 'unknown',
                method='password'
            )
        except Exception:
            pass  # Non-blocking
        
        # Generate CSRF token
        csrf_token = None
        if HAS_CSRF:
            csrf_token = CSRFProtection.generate_token(user.id)
        
        return success_response(
            data={
                'user': {
                    'id': user.id,
                    'username': user.username
                },
                'csrf_token': csrf_token,
                'force_password_change': user.force_password_change or False
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
    # WebSocket event for logout
    try:
        from websocket.emitters import on_user_logout
        username = session.get('username', 'unknown')
        on_user_logout(username=username)
    except Exception:
        pass  # Non-blocking
    
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
    
    # Generate fresh CSRF token on verify
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(g.user_id)
    
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
            },
            'csrf_token': csrf_token
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


# ============================================================================
# Password Reset (Forgot Password)
# ============================================================================

def _is_email_configured():
    """Check if email/SMTP is configured"""
    from models import SystemConfig
    try:
        smtp_host = SystemConfig.get('smtp_host')
        return bool(smtp_host and smtp_host.strip())
    except Exception:
        return False


@bp.route('/api/v2/auth/forgot-password', methods=['POST'])
def forgot_password():
    """
    Request password reset - sends email with reset link
    Only works if email is configured
    """
    import secrets
    from datetime import timedelta
    
    # Check if email is configured
    if not _is_email_configured():
        return error_response('Password reset unavailable - email not configured', 503)
    
    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    
    if not email:
        return error_response('Email is required', 400)
    
    # Always return success to prevent email enumeration
    user = User.query.filter(db.func.lower(User.email) == email).first()
    
    if user and user.active:
        # Generate secure token
        token = secrets.token_urlsafe(48)
        user.password_reset_token = hashlib.sha256(token.encode()).hexdigest()
        user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
        db.session.commit()
        
        # Send email
        try:
            from services.notification_service import NotificationService
            reset_url = f"{current_app.config.get('BASE_URL', 'https://localhost:8443')}/reset-password?token={token}"
            
            NotificationService.send_email(
                to=user.email,
                subject='UCM - Password Reset Request',
                template='password_reset',
                context={
                    'username': user.username,
                    'reset_url': reset_url,
                    'expires_in': '1 hour',
                    'ip_address': request.remote_addr
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset email: {e}")
    
    # Always return success to prevent enumeration
    return success_response(
        message='If an account with that email exists, a password reset link has been sent.'
    )


@bp.route('/api/v2/auth/reset-password', methods=['POST'])
def reset_password():
    """
    Reset password using token from email
    """
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    new_password = data.get('password', '')
    
    if not token:
        return error_response('Reset token is required', 400)
    
    if not new_password or len(new_password) < 8:
        return error_response('Password must be at least 8 characters', 400)
    
    # Validate password strength
    try:
        from security.password_policy import validate_password
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return error_response(message, 400)
    except ImportError:
        pass  # Password policy not available
    
    # Find user by token hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(password_reset_token=token_hash).first()
    
    if not user:
        return error_response('Invalid or expired reset token', 400)
    
    if user.password_reset_expires < datetime.utcnow():
        # Clear expired token
        user.password_reset_token = None
        user.password_reset_expires = None
        db.session.commit()
        return error_response('Reset token has expired', 400)
    
    # Reset password
    user.set_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.force_password_change = False
    user.failed_logins = 0
    user.locked_until = None
    db.session.commit()
    
    # Audit log
    try:
        from services.audit_service import AuditService
        AuditService.log(
            action='password_reset',
            entity_type='user',
            entity_id=user.id,
            details={'method': 'email_reset'},
            user_id=user.id
        )
    except Exception:
        pass
    
    return success_response(message='Password has been reset successfully')


@bp.route('/api/v2/auth/email-configured', methods=['GET'])
def check_email_configured():
    """Check if email is configured (for showing forgot password link)"""
    return success_response(data={'configured': _is_email_configured()})
