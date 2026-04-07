"""
Multi-Method Authentication API
Supports: Password, mTLS, WebAuthn, API Keys

Architecture:
1. GET /api/v2/auth/methods - Detect available auth methods
2. POST /api/v2/auth/login/password - Password login
3. POST /api/v2/auth/login/mtls - mTLS login (auto or manual)
4. POST /api/v2/auth/login/webauthn/start - Start WebAuthn auth
5. POST /api/v2/auth/login/webauthn/verify - Verify WebAuthn response
6. POST /api/v2/auth/logout - Logout (clears session)
"""

from flask import Blueprint, request, jsonify, session, current_app, g
from auth.unified import AuthManager
from utils.response import success_response, error_response
from models import User, db
from services.mtls_auth_service import MTLSAuthService
from services.webauthn_service import WebAuthnService
from services.certificate_parser import CertificateParser
from datetime import datetime, timedelta
import logging
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# Import CSRF protection
try:
    from security.csrf import CSRFProtection
    HAS_CSRF = True
except ImportError:
    HAS_CSRF = False


def _get_display_settings():
    """Get timezone, date_format, show_time from system_config for login responses."""
    from models import SystemConfig
    tz_row = SystemConfig.query.filter_by(key='timezone').first()
    df_row = SystemConfig.query.filter_by(key='date_format').first()
    st_row = SystemConfig.query.filter_by(key='show_time').first()
    return {
        'timezone': tz_row.value if tz_row else 'UTC',
        'date_format': df_row.value if df_row else 'short',
        'show_time': st_row.value != 'false' if st_row else True,
    }


bp = Blueprint('auth_methods', __name__)

# In-memory 2FA/WebAuthn brute-force tracking (per-session, cleared on success)
_2fa_failed_attempts = {}  # key: pending_user_id, value: {'count': int, 'locked_until': datetime}
_WEBAUTHN_FAILED = {}      # key: username, value: {'count': int, 'locked_until': datetime}
_MAX_2FA_ATTEMPTS = 5
_2FA_LOCKOUT_SECONDS = 900  # 15 minutes


def _check_2fa_lockout(key: str, tracker: dict) -> bool:
    """Check if key is locked out from 2FA/WebAuthn attempts."""
    entry = tracker.get(key)
    if not entry:
        return False
    if entry.get('locked_until') and utc_now() < entry['locked_until']:
        return True
    if entry.get('locked_until') and utc_now() >= entry['locked_until']:
        tracker.pop(key, None)
    return False


def _record_2fa_failure(key: str, tracker: dict):
    """Record a failed 2FA/WebAuthn attempt."""
    from datetime import timedelta
    entry = tracker.setdefault(key, {'count': 0, 'locked_until': None})
    entry['count'] += 1
    if entry['count'] >= _MAX_2FA_ATTEMPTS:
        entry['locked_until'] = utc_now() + timedelta(seconds=_2FA_LOCKOUT_SECONDS)


def _clear_2fa_failures(key: str, tracker: dict):
    """Clear failed attempts on success."""
    tracker.pop(key, None)


@bp.route('/api/v2/auth/methods', methods=['GET', 'POST'])
def detect_auth_methods():
    """
    Detect available authentication methods.
    
    GET: Global methods + mTLS cert status (no username needed)
    POST with {"username": "xxx"}: User-specific (WebAuthn credential count, etc.)
    
    If the mTLS middleware already auto-logged the user in (session exists),
    returns mtls_status='auto_logged_in' so the frontend can skip the login form.
    """
    methods = {
        'password': True,
        'mtls': False,
        'mtls_status': 'not_present',
        'webauthn': True,
        'webauthn_credentials': 0,
        'api_keys': True,
        'sso_providers': [],
    }

    # If middleware already auto-logged in via cert, signal it
    if session.get('user_id') and session.get('auth_method') == 'certificate':
        methods['mtls'] = True
        methods['mtls_status'] = 'auto_logged_in'
        methods['mtls_user'] = session.get('username')
        return success_response(data=methods)

    # Check for username in POST body
    username = None
    if request.method == 'POST' and request.json:
        username = request.json.get('username')

    # User-specific info
    if username:
        user = User.query.filter_by(username=username).first()
        if user and user.active:
            from models.webauthn import WebAuthnCredential
            webauthn_count = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).count()
            methods['webauthn_credentials'] = webauthn_count

            from models.auth_certificate import AuthCertificate
            mtls_count = AuthCertificate.query.filter_by(user_id=user.id, enabled=True).count()
            methods['mtls_certificates'] = mtls_count

    # Detect mTLS cert presence (use middleware's parsed cert if available)
    cert_info = getattr(g, 'mtls_cert_info', None)
    if not cert_info:
        try:
            headers = dict(request.headers)
            if 'X-SSL-Client-Verify' in headers:
                cert_info = CertificateParser.extract_from_nginx_headers(headers)
            elif 'X-SSL-Client-S-DN' in headers:
                cert_info = CertificateParser.extract_from_apache_headers(headers)
            elif request.environ.get('peercert'):
                cert_info = CertificateParser.extract_from_flask_native(request.environ['peercert'])
        except Exception as e:
            logger.error(f"Error detecting mTLS: {e}")
            methods['mtls_status'] = 'error'
            return success_response(data=methods)

    if cert_info:
        methods['mtls'] = True
        user_match, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)
        if user_match:
            methods['mtls_status'] = 'enrolled'
            methods['mtls_user'] = user_match.username
        else:
            methods['mtls_status'] = 'present_not_enrolled'

    # Fetch SSO providers for login page
    try:
        from models.sso_provider import SSOProvider
        providers = SSOProvider.query.filter_by(enabled=True).all()
        methods['sso_providers'] = [
            {'id': p.id, 'name': p.name, 'provider_type': p.provider_type}
            for p in providers
        ]
    except Exception:
        pass

    return success_response(data=methods)


@bp.route('/api/v2/auth/login/password', methods=['POST'])
def login_password():
    """
    Password-based login
    
    POST /api/v2/auth/login/password
    Body: {"username": "admin", "password": "xxx"}
    
    Returns session cookie + user info
    """
    from services.audit_service import AuditService
    
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return error_response('Username and password required', 400)
    
    username = data['username']
    password = data['password']
    
    # Find user
    user = User.query.filter_by(username=username).first()
    
    if not user or not user.active:
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            details=f'Login failed for username: {username} (user not found or inactive)',
            success=False,
            username=username
        )
        return error_response('Invalid credentials', 401)
    
    # Check account lockout (5 failed attempts = 15 min lockout)
    MAX_FAILED = 5
    LOCKOUT_MINUTES = 15
    if user.locked_until and utc_now() < user.locked_until:
        return error_response('Account temporarily locked. Try again later.', 429)
    if user.locked_until and utc_now() >= user.locked_until:
        user.locked_until = None
        user.failed_logins = 0
        db.session.commit()
    
    # Verify password
    if not user.check_password(password):
        # Increment failed login counter
        user.failed_logins = (user.failed_logins or 0) + 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until = utc_now() + timedelta(minutes=LOCKOUT_MINUTES)
            logger.warning(f"Account {username} locked after {MAX_FAILED} failed attempts")
        db.session.commit()
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            resource_id=user.id,
            details=f'Login failed for {username} (invalid password)',
            success=False,
            username=username
        )
        return error_response('Invalid credentials', 401)
    
    # Update login stats
    user.last_login = utc_now()
    user.login_count = (user.login_count or 0) + 1
    user.failed_logins = 0  # Reset failed logins on successful login
    db.session.commit()
    
    # Check if 2FA is enabled — require TOTP verification before creating session
    if user.totp_confirmed:
        session.clear()
        session['pending_2fa_user_id'] = user.id
        session['pending_2fa_username'] = user.username
        session['pending_2fa_method'] = 'password'
        session.permanent = True
        
        AuditService.log_action(
            action='login_2fa_required',
            resource_type='user',
            resource_id=user.id,
            resource_name=username,
            details=f'Password verified, 2FA required for {username}',
            success=True,
            username=username
        )
        
        return success_response(
            data={
                'requires_2fa': True,
                'user': {'id': user.id, 'username': user.username}
            },
            message='2FA verification required'
        )
    
    # No 2FA — create full session
    now = utc_now()
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = 'password'
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True
    
    # Get permissions
    from auth.permissions import get_role_permissions
    permissions = get_role_permissions(user.role)
    
    # Audit log success
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=username,
        details=f'Password login successful for {username}',
        success=True,
        username=username
    )
    
    logger.info(f"✅ Password login successful: {user.username}")
    
    # Generate CSRF token
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(user.id)
    
    return success_response(
        data={
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'active': user.active
            },
            'role': user.role,
            'permissions': permissions,
            'auth_method': 'password',
            'csrf_token': csrf_token,
            'force_password_change': user.force_password_change or False,
            **_get_display_settings()
        },
        message='Login successful'
    )


@bp.route('/api/v2/auth/login/2fa', methods=['POST'])
def login_2fa():
    """
    Complete login with TOTP 2FA code
    
    POST /api/v2/auth/login/2fa
    Body: {"code": "123456"}
    
    Requires a pending 2FA session (from password login)
    """
    import pyotp
    from auth.permissions import get_role_permissions
    from services.audit_service import AuditService
    
    # Check for pending 2FA session
    pending_user_id = session.get('pending_2fa_user_id')
    pending_username = session.get('pending_2fa_username')
    auth_method = session.get('pending_2fa_method', 'password')
    
    if not pending_user_id:
        return error_response('No pending 2FA verification', 401)
    
    # SEC-03: Brute-force protection on 2FA
    lockout_key = str(pending_user_id)
    if _check_2fa_lockout(lockout_key, _2fa_failed_attempts):
        return error_response('Too many failed attempts. Try again later.', 429)
    
    data = request.json
    code = data.get('code') if data else None
    
    if not code:
        return error_response('Verification code required', 400)
    
    user = User.query.get(pending_user_id)
    if not user or not user.active:
        session.clear()
        return error_response('Invalid credentials', 401)
    
    # Verify TOTP code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(str(code), valid_window=1):
        # Check recovery codes
        recovery_used = False
        if user.backup_codes:
            import json
            try:
                codes = json.loads(user.backup_codes)
                if str(code) in codes:
                    codes.remove(str(code))
                    user.backup_codes = json.dumps(codes)
                    db.session.commit()
                    recovery_used = True
                    logger.info(f"Recovery code used for {user.username}, {len(codes)} remaining")
                else:
                    AuditService.log_action(
                        action='login_2fa_failure',
                        resource_type='user',
                        resource_id=user.id,
                        details=f'Invalid 2FA code for {pending_username}',
                        success=False,
                        username=pending_username
                    )
                    _record_2fa_failure(lockout_key, _2fa_failed_attempts)
                    return error_response('Invalid verification code', 401)
            except (json.JSONDecodeError, ValueError):
                _record_2fa_failure(lockout_key, _2fa_failed_attempts)
                return error_response('Invalid verification code', 401)
        else:
            AuditService.log_action(
                action='login_2fa_failure',
                resource_type='user',
                resource_id=user.id,
                details=f'Invalid 2FA code for {pending_username}',
                success=False,
                username=pending_username
            )
            _record_2fa_failure(lockout_key, _2fa_failed_attempts)
            return error_response('Invalid verification code', 401)
    
    # 2FA verified — create full session
    _clear_2fa_failures(lockout_key, _2fa_failed_attempts)
    now = utc_now()
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = auth_method
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True
    
    permissions = get_role_permissions(user.role)
    
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=f'Login successful with 2FA for {user.username}',
        success=True,
        username=user.username
    )
    
    logger.info(f"✅ 2FA login successful: {user.username}")
    
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(user.id)
    
    return success_response(
        data={
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'active': user.active
            },
            'role': user.role,
            'permissions': permissions,
            'auth_method': auth_method,
            'csrf_token': csrf_token,
            'force_password_change': user.force_password_change or False,
            **_get_display_settings()
        },
        message='Login successful'
    )

@bp.route('/api/v2/auth/login/mtls', methods=['POST'])
def login_mtls():
    """
    mTLS (client certificate) login
    
    Certificate must be presented in request (via reverse proxy headers or native TLS)
    
    Returns session cookie + user info
    """
    # Extract certificate info
    cert_info = None
    try:
        headers = dict(request.headers)
        if 'X-SSL-Client-Verify' in headers:
            cert_info = CertificateParser.extract_from_nginx_headers(headers)
        elif 'X-SSL-Client-S-DN' in headers:
            cert_info = CertificateParser.extract_from_apache_headers(headers)
        elif request.environ.get('peercert'):
            cert_info = CertificateParser.extract_from_flask_native(request.environ['peercert'])
    except Exception as e:
        logger.error(f"Error extracting certificate: {e}")
        return error_response('Failed to extract client certificate', 500)
    
    if not cert_info:
        return error_response('No client certificate presented', 401)
    
    # Authenticate certificate
    user, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)
    
    if not user:
        return error_response(error or 'Certificate authentication failed', 401)
    
    # Update login stats
    user.last_login = utc_now()
    user.login_count = (user.login_count or 0) + 1
    user.failed_logins = 0  # Reset failed logins on successful login
    db.session.commit()
    
    # Create session
    now = utc_now()
    session.clear()
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = 'mtls'
    session['cert_serial'] = auth_cert.cert_serial
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True
    
    # Get permissions
    from auth.permissions import get_role_permissions
    permissions = get_role_permissions(user.role)
    
    logger.info(f"✅ mTLS login successful: {user.username} (cert: {auth_cert.cert_serial})")
    
    # Generate CSRF token
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(user.id)
    
    return success_response(
        data={
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': user.full_name,
                'role': user.role,
                'active': user.active
            },
            'role': user.role,
            'permissions': permissions,
            'auth_method': 'mtls',
            'csrf_token': csrf_token,
            'certificate': {
                'serial': auth_cert.cert_serial,
                'name': auth_cert.name
            },
            **_get_display_settings()
        },
        message='Login successful via mTLS'
    )


@bp.route('/api/v2/auth/login/webauthn/start', methods=['POST'])
def webauthn_start():
    """
    Start WebAuthn authentication
    
    POST /api/v2/auth/login/webauthn/start
    Body: {"username": "admin"}  # Optional for resident keys
    
    Returns challenge options for navigator.credentials.get()
    """
    data = request.json or {}
    username = data.get('username')
    
    if not username:
        return error_response('Username required', 400)
    
    # Find user
    user = User.query.filter_by(username=username).first()
    if not user or not user.active:
        # Don't reveal if user exists
        return error_response('Invalid username', 401)
    
    # Check if user has WebAuthn credentials
    from models.webauthn import WebAuthnCredential
    creds = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
    if not creds:
        # SEC-05: Don't reveal whether user exists or has credentials
        return error_response('WebAuthn authentication not available', 401)
    
    # Generate authentication options
    try:
        hostname = request.host
        options, user_id = WebAuthnService.generate_authentication_options(username, hostname)
        
        if not options:
            return error_response('Failed to generate WebAuthn options', 500)
        
        logger.info(f"WebAuthn auth started for: {user.username}")
        
        return success_response(
            data={
                'options': options,
                'username': user.username
            }
        )
    except Exception as e:
        logger.error(f"WebAuthn start error: {e}")
        return error_response('Failed to generate WebAuthn options', 500)


@bp.route('/api/v2/auth/login/webauthn/verify', methods=['POST'])
def webauthn_verify():
    """
    Verify WebAuthn authentication response
    
    POST /api/v2/auth/login/webauthn/verify
    Body: {
        "username": "admin",
        "response": {...}  # From navigator.credentials.get()
    }
    
    Returns session cookie + user info
    """
    data = request.json
    
    if not data or not data.get('username') or not data.get('response'):
        return error_response('Username and response required', 400)
    
    username = data['username']
    credential_response = data['response']
    
    # SEC-04: Brute-force protection on WebAuthn
    if _check_2fa_lockout(username, _WEBAUTHN_FAILED):
        return error_response('Too many failed attempts. Try again later.', 429)
    
    # Find user
    user = User.query.filter_by(username=username).first()
    if not user or not user.active:
        return error_response('Invalid credentials', 401)
    
    # Verify authentication response
    try:
        from services.audit_service import AuditService
        
        hostname = request.host
        success, message, auth_user = WebAuthnService.verify_authentication(
            user.id, credential_response, hostname
        )
        
        if not success or not auth_user:
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                resource_id=user.id,
                details=f'WebAuthn login failed for {username}',
                success=False,
                username=username
            )
            _record_2fa_failure(username, _WEBAUTHN_FAILED)
            return error_response('WebAuthn verification failed', 401)
        
        # Update login stats
        _clear_2fa_failures(username, _WEBAUTHN_FAILED)
        user.last_login = utc_now()
        user.login_count = (user.login_count or 0) + 1
        user.failed_logins = 0  # Reset failed logins on successful login
        db.session.commit()
        
        # Create session
        now = utc_now()
        session.clear()
        session['user_id'] = user.id
        session['username'] = user.username
        session['auth_method'] = 'webauthn'
        session['login_time'] = now.isoformat()
        session['last_activity'] = now.isoformat()
        session.permanent = True
        
        # Get permissions
        from auth.permissions import get_role_permissions
        permissions = get_role_permissions(user.role)
        
        # Audit log success
        AuditService.log_action(
            action='login_success',
            resource_type='user',
            resource_id=user.id,
            resource_name=username,
            details=f'WebAuthn login successful for {username}',
            success=True,
            username=username
        )
        
        logger.info(f"✅ WebAuthn login successful: {user.username}")
        
        # Generate CSRF token
        csrf_token = None
        if HAS_CSRF:
            csrf_token = CSRFProtection.generate_token(user.id)
        
        return success_response(
            data={
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'full_name': user.full_name,
                    'role': user.role,
                    'active': user.active
                },
                'role': user.role,
                'permissions': permissions,
                'auth_method': 'webauthn',
                'csrf_token': csrf_token,
                **_get_display_settings()
            },
            message='Login successful via WebAuthn'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"WebAuthn verification error: {e}")
        return error_response('WebAuthn verification failed', 401)


# NOTE: Logout endpoint is in auth.py (with @require_auth and WebSocket events)
