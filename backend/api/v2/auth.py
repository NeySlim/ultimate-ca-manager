"""
Authentication Routes v2.0
/api/auth/* - Login, Logout, Verify

Supports:
- Session cookies (web UI)
- JWT tokens (external APIs)
"""

import logging
from flask import Blueprint, request, jsonify, session, current_app
from auth.unified import AuthManager, require_auth, require_permission
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.trusted_proxy import client_ip
from models import User, db
from security.password_policy import validate_password

logger = logging.getLogger(__name__)
from datetime import datetime
import hashlib
from utils.datetime_utils import utc_now

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

# Default lockout settings (overridden by DB config)
DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_LOCKOUT_SECONDS = 900  # 15 minutes


def _get_lockout_settings():
    """Read lockout settings from DB config, fallback to defaults.
    Uses shared function from sso.helpers.
    """
    from api.v2.sso.helpers import _get_lockout_settings as shared_get_lockout
    return shared_get_lockout()


def _check_account_lockout(username):
    """Check if account is locked due to failed attempts (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if not user:
        return False
    
    if user.locked_until:
        if utc_now() < user.locked_until:
            return True
        else:
            # Lockout expired, reset
            user.locked_until = None
            user.failed_logins = 0
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to clear expired lockout: {e}")
            return False
    return False


def _record_failed_attempt(username):
    """Record a failed login attempt (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if not user:
        return
    
    max_attempts, lockout_seconds = _get_lockout_settings()
    user.failed_logins = (user.failed_logins or 0) + 1
    
    if user.failed_logins >= max_attempts:
        from datetime import timedelta
        user.locked_until = utc_now() + timedelta(seconds=lockout_seconds)
        current_app.logger.warning(f"Account locked for {username} after {max_attempts} failed attempts")
        
        # Send security alert notification
        try:
            from services.notification_service import NotificationService
            ip_address = client_ip() or 'unknown'
            NotificationService.on_security_alert(
                event_type='account_locked',
                username=username,
                ip_address=ip_address
            )
        except Exception as e:
            logger.warning(f"Non-blocking: failed to send account_locked notification for {username}: {e}", exc_info=True)
            pass  # Non-blocking
    
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record failed attempt: {e}")


def _clear_failed_attempts(username):
    """Clear failed attempts after successful login (DB-persisted)"""
    user = User.query.filter_by(username=username).first()
    if user and (user.failed_logins or user.locked_until):
        user.failed_logins = 0
        user.locked_until = None
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to clear failed attempts: {e}")


@bp.route('/api/v2/auth/login', methods=['POST'])
def login():
    """
    Legacy login endpoint - delegates to auth_methods.login_password()
    which has proper 2FA checks and uses SystemConfig lockout settings
    """
    from api.v2.auth_methods import login_password
    return login_password()


@bp.route('/api/v2/auth/logout', methods=['POST'])
@require_auth()
def logout():
    """
    Logout endpoint
    Clears session (for session-based auth)
    """
    username = session.get('username', 'unknown')
    
    # Audit log
    try:
        from services.audit_service import AuditService
        AuditService.log_auth('logout', username=username, details=f'User {username} logged out')
    except Exception as e:
        logger.warning(f"Non-blocking: failed to audit-log logout for {username}: {e}", exc_info=True)
    
    # WebSocket event for logout
    try:
        from websocket.emitters import on_user_logout
        on_user_logout(username=username)
    except Exception as e:
        logger.warning(f"Non-blocking: failed to emit on_user_logout WebSocket event for {username}: {e}", exc_info=True)
    
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
        
        return success_response(data={
                'authenticated': False,
                'cert_error': cert_error
            })
    
    # Generate fresh CSRF token on verify
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(g.user_id)
    
    # Include app timezone setting
    from models import SystemConfig
    tz_row = SystemConfig.query.filter_by(key='timezone').first()
    app_timezone = tz_row.value if tz_row else 'UTC'
    df_row = SystemConfig.query.filter_by(key='date_format').first()
    app_date_format = df_row.value if df_row else 'short'
    st_row = SystemConfig.query.filter_by(key='show_time').first()
    app_show_time = st_row.value != 'false' if st_row else True
    
    # Get session timeout for frontend warning timer
    from auth.unified import AuthManager
    session_timeout = AuthManager._get_session_timeout()
    
    # Forced-2FA-enrolment state (#141): the session is authenticated but may
    # only reach the enrolment endpoints until TOTP is confirmed. The frontend
    # uses this to route to the mandatory enrolment screen.
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    must_enroll_2fa = bool(session.get(ENROLL_SESSION_KEY))

    # If authenticated
    return success_response(
        data={
            'authenticated': True,
            'user_id': g.user_id,
            'auth_method': g.auth_method,
            'permissions': g.permissions,
            'role': g.current_user.role,
            'user': {
                'id': g.current_user.id,
                'username': g.current_user.username,
                'role': g.current_user.role
            },
            'must_enroll_2fa': must_enroll_2fa,
            'csrf_token': csrf_token,
            'timezone': app_timezone,
            'date_format': app_date_format,
            'show_time': app_show_time,
            'session_timeout': session_timeout,
            'preferences': g.current_user.get_preferences()
        }
    )


# ============================================================================
# Password Reset (Forgot Password)
# ============================================================================

def _is_email_configured():
    """Check if email/SMTP is configured"""
    from models import SystemConfig
    try:
        smtp_config = SystemConfig.query.filter_by(key='smtp_host').first()
        smtp_host = smtp_config.value if smtp_config else ''
        return bool(smtp_host and smtp_host.strip())
    except Exception as e:
        logger.warning(f"Failed to read smtp_host SystemConfig, treating email as not configured: {e}")
        return False


@bp.route('/api/v2/auth/forgot-password', methods=['POST'])
@limiter.limit("3/hour")
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
        user.password_reset_expires = utc_now() + timedelta(hours=1)
        ok, _err = safe_commit(logger, "Failed to store password reset token")
        if not ok:
            return _err
        
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
                    'ip_address': client_ip()
                }
            )
        except Exception as e:
            current_app.logger.error(f"Failed to send password reset email: {e}")
    
    # Always return success to prevent enumeration
    return success_response(
        message='If an account with that email exists, a password reset link has been sent.'
    )


@bp.route('/api/v2/auth/reset-password', methods=['POST'])
@limiter.limit("5/hour")
def reset_password():
    """
    Reset password using token from email
    """
    data = request.get_json() or {}
    token = data.get('token', '').strip()
    new_password = data.get('password', '')
    
    if not token:
        return error_response('Reset token is required', 400)
    
    if not new_password:
        return error_response('New password is required', 400)

    # Validate password strength against configurable policy
    is_valid, errors = validate_password(new_password)
    if not is_valid:
        first = errors[0] if errors else {'message': 'Invalid password'}
        return error_response(first.get('message', 'Invalid password'), 400)
    
    # Find user by token hash
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    user = User.query.filter_by(password_reset_token=token_hash).first()
    
    if not user:
        return error_response('Invalid or expired reset token', 400)
    
    # Check if user is active
    if not user.active:
        return error_response('Invalid or expired reset token', 400)
    
    if user.password_reset_expires < utc_now():
        # Clear expired token
        user.password_reset_token = None
        user.password_reset_expires = None
        ok, _err = safe_commit(logger, "Failed to clear expired reset token")
        if not ok:
            return _err
        return error_response('Reset token has expired', 400)
    
    # Reset password
    user.set_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires = None
    user.force_password_change = False
    user.failed_logins = 0
    user.locked_until = None
    ok, _err = safe_commit(logger, "Failed to reset password")
    if not ok:
        return _err
    
    # Audit log
    try:
        from services.audit_service import AuditService
        AuditService.log_action(
            action='password_reset',
            resource_type='user',
            resource_id=str(user.id),
            details='Password reset via email',
            user_id=user.id
        )
    except Exception as e:
        logger.warning(f"Non-blocking: failed to audit-log password_reset for user {user.id}: {e}", exc_info=True)
    
    return success_response(message='Password has been reset successfully')


@bp.route('/api/v2/auth/email-configured', methods=['GET'])
def check_email_configured():
    """Check if email is configured (for showing forgot password link)"""
    return success_response(data={'configured': _is_email_configured()})
