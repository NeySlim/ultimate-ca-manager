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
from utils.public_endpoints import get_admin_canonical_origin
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

@bp.route('/api/v2/auth/login', methods=['POST'])
def login():
    """
    Legacy login endpoint - delegates to auth_methods.login_password()
    which has proper 2FA checks and uses SystemConfig lockout settings
    """
    from api.v2.auth_methods import login_password
    return login_password()


@bp.route('/api/v2/auth/logout', methods=['POST'])
def logout():
    """Sign out: clears the session, a locked one too (the lock screen's way to another account)."""
    from auth.session_lock import locks_this_request
    if locks_this_request():
        return _sign_out()
    return _logout_signed_in()


@require_auth()
def _logout_signed_in():
    return _sign_out()


def _sign_out():
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
    
    from auth.session_start import close_session_sockets
    session_id = getattr(session, 'sid', None)
    session.clear()
    close_session_sockets(session_id, username)
    
    return success_response(message='Logout successful')


@bp.route('/api/v2/auth/lock', methods=['POST'])
def lock():
    """Lock the session, by hand or after inactivity: it keeps its account and serves nothing
    until that account unlocks it (/auth/unlock/*), on every node of a shared store."""
    from auth.session_lock import locks_this_request
    if locks_this_request():
        return success_response(message='Session locked')
    return _lock_signed_in()


@require_auth(session_only=True)
def _lock_signed_in():
    from flask import g
    from auth.session_lock import lock_session
    data = request.get_json(silent=True) or {}
    reason = 'inactivity' if isinstance(data, dict) and data.get('reason') == 'idle' else 'manual'
    username = session.get('username') or g.current_user.username
    try:
        from services.audit_service import AuditService
        AuditService.log_auth('session_locked', username=username, user_id=g.user_id,
                              details=f'Session locked by {username} ({reason})')
    except Exception as e:
        logger.warning(f"Non-blocking: failed to audit-log the lock of {username}: {e}", exc_info=True)
    lock_session(reason)
    # Its open sockets close now, on every node; the handshake refuses a locked session
    from auth.session_start import close_session_sockets
    close_session_sockets(getattr(session, 'sid', None), username)
    return success_response(message='Session locked')


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
        # A locked session: its account and unlock methods, and the CSRF token the unlock needs
        from auth.session_lock import locked_summary, locks_this_request
        if locks_this_request():
            return success_response(data={
                'authenticated': False,
                'locked': locked_summary(),
                'csrf_token': (CSRFProtection.generate_token(session['user_id'])
                               if HAS_CSRF and session.get('user_id') else None),
            })
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
    
    # Get session timeout for frontend warning timer
    from auth.unified import AuthManager
    session_timeout = AuthManager._get_session_timeout()
    
    # Forced-2FA-enrolment state (#141): the session is authenticated but may
    # only reach the enrolment endpoints until TOTP is confirmed. The frontend
    # uses this to route to the mandatory enrolment screen.
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    must_enroll_2fa = bool(session.get(ENROLL_SESSION_KEY))

    # If authenticated. Built from the shared session payload so the forced
    # password change (and anything added to it later) reaches the SPA on a
    # session restore too, not only on the login response. The narrower user
    # block is the one /verify has always returned.
    from auth.session_payload import auth_session_payload
    from auth.twofa_enforcement import second_factor_methods

    auth_method, auth_provider = _signed_in_with()
    factors = second_factor_methods(g.current_user)
    return success_response(
        data=auth_session_payload(
            g.current_user,
            permissions=g.permissions,
            auth_method=auth_method,
            csrf_token=csrf_token,
            user_block={
                'id': g.current_user.id,
                'username': g.current_user.username,
                'email': g.current_user.email,
                'full_name': g.current_user.full_name,
                'role': g.current_user.role
            },
            authenticated=True,
            user_id=g.user_id,
            must_enroll_2fa=must_enroll_2fa,
            session_timeout=session_timeout,
            auth_provider=auth_provider,
            mfa={'enabled': bool(factors), 'methods': factors},
            session=_session_deadlines(session_timeout),
            preferences=g.current_user.get_preferences(),
        )
    )


def _signed_in_with():
    """(method, provider display name) the session was opened with, as its login kept them;
    another credential (an API key) is reported as itself."""
    from flask import g
    if g.auth_method != 'session':
        return g.auth_method, None
    return session.get('auth_method') or 'session', session.get('auth_provider')


def _session_deadlines(idle_timeout):
    """The inactivity timeout and the absolute end (login time + maximum lifetime) of a session."""
    from datetime import timedelta
    from flask import g
    from utils.datetime_utils import utc_isoformat
    if g.auth_method != 'session':
        return {'idle_timeout_s': None, 'expires_at': None}
    expires_at = None
    try:
        started = datetime.fromisoformat(session.get('login_time') or '')
        expires_at = utc_isoformat(started + timedelta(seconds=AuthManager._get_session_max_lifetime()))
    except (TypeError, ValueError):
        pass
    return {'idle_timeout_s': idle_timeout, 'expires_at': expires_at}


# ============================================================================
# Password Reset (Forgot Password)
# ============================================================================

def _is_email_configured():
    """Whether a password-reset mail can actually go out.

    Reads the smtp_config row Settings > Email writes, with the sender's own
    readiness rule (enabled, host, port, From): the old check looked at a
    system_config 'smtp_host' key nothing wrote, so the reset was refused on
    every install (#329).
    """
    from models.email_notification import SMTPConfig
    try:
        smtp = SMTPConfig.query.first()
        return bool(
            smtp and smtp.enabled and (smtp.smtp_host or '').strip()
            and smtp.smtp_port and (smtp.smtp_from or '').strip()
        )
    except Exception as e:
        logger.warning(f"Failed to read SMTP configuration, treating email as not configured: {e}")
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
    
    # The link goes to the operator's public origin (Base URL, else FQDN), never to
    # the Host of this unauthenticated request, which the caller chooses.
    origin = get_admin_canonical_origin()
    if not origin:
        logger.warning("Password reset refused: no Base URL nor server FQDN to build the link from")
        return error_response(
            'Password reset unavailable - set the Base URL in Settings so the link can reach UCM', 503)

    data = request.get_json() or {}
    email = data.get('email', '').strip().lower()
    
    if not email:
        return error_response('Email is required', 400)
    
    # Always return success to prevent email enumeration. An account its SSO provider
    # alone opens gets no link: another account sharing the address may still get one.
    from api.v2.sso.account_state import sso_only
    holders = User.query.filter(db.func.lower(User.email) == email).order_by(User.id).all()
    user = next((u for u in holders if u.active and not sso_only(u)), None)

    if user:
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
            reset_url = f"{origin.rstrip('/')}/reset-password?token={token}"
            
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
    
    # An inactive account, or one its SSO provider alone opens, takes no password this way
    from api.v2.sso.account_state import sso_only
    if not user.active or sso_only(user):
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
    try:
        # The new password restarts its count: in the database, whatever this copy holds
        user.clear_failed_logins()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to reset password for user {user.id}: {e}", exc_info=True)
        return error_response('Failed to reset password', 500)
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
    """Whether a reset e-mail can go out with a link that reaches UCM (shows Forgot password)."""
    return success_response(data={'configured': bool(_is_email_configured() and get_admin_canonical_origin())})
