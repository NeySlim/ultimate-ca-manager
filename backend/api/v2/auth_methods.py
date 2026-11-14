"""
Multi-Method Authentication API
Supports: Password, mTLS, WebAuthn, API Keys

Architecture:
1. GET /api/v2/auth/methods - Detect available auth methods
2. POST /api/v2/auth/login/password - Password login
3. POST /api/v2/auth/login/mtls - mTLS login (auto or manual)
4. POST /api/v2/auth/login/webauthn/start - Start WebAuthn auth
5. POST /api/v2/auth/login/webauthn/verify - Verify WebAuthn response
6. POST /api/v2/auth/login/2fa[/webauthn/options|/webauthn/verify] - Second factor after a password
7. POST /api/v2/auth/logout - Logout (clears session)
"""

from flask import Blueprint, request, jsonify, session, current_app, g
from auth.unified import AuthManager
from auth.session_payload import auth_session_payload
from auth.session_start import begin_session
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils import trusted_proxy
from models import User, db
from models.webauthn import WebAuthnCredential
from services.mtls_auth_service import MTLSAuthService
from services.webauthn_service import WebAuthnService

# Import limiter for rate limiting login attempts
try:
    from app import limiter
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False
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




bp = Blueprint('auth_methods', __name__)

# Second-factor and WebAuthn lockout: one row per target in second_factor_failures,
# shared by every node. '2fa' keys the pending login's user id, 'webauthn' the username.
TWO_FA = '2fa'
WEBAUTHN = 'webauthn'


def _get_2fa_lockout_settings():
    """Read lockout settings from DB config, fallback to defaults.
    Uses shared function from sso.helpers.
    """
    from api.v2.sso.helpers import _get_lockout_settings
    return _get_lockout_settings()


def _check_2fa_lockout(kind: str, key: str) -> bool:
    """Whether the database holds a lock on this target that has not expired."""
    from models.second_factor_failure import SecondFactorFailure
    locked_until = db.session.execute(
        db.select(SecondFactorFailure.locked_until).filter_by(kind=kind, target=key)
    ).scalar_one_or_none()
    return locked_until is not None and utc_now() < locked_until


def _reserve_2fa_attempt(kind: str, key: str) -> bool:
    """Count one attempt before it is verified; False when the target is locked.

    One upsert decides: parallel attempts on any node get at most the threshold, the one
    reaching it arms the lock, and a success clears the row. Expired rows are purged first.
    """
    from sqlalchemy import and_, case, or_
    from models.second_factor_failure import SecondFactorFailure as F
    max_attempts, lockout_seconds = _get_2fa_lockout_settings()
    now = utc_now()
    until = now + timedelta(seconds=lockout_seconds)
    # Rows bounded by the window: a lock past its end, or a count idle for a whole window
    db.session.execute(db.delete(F).where(or_(
        F.locked_until <= now,
        and_(F.locked_until.is_(None), F.updated_at < now - timedelta(seconds=lockout_seconds)),
    )))
    if db.engine.dialect.name == 'postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    expired = and_(F.locked_until.is_not(None), F.locked_until <= now)
    failures = case((expired, 1), else_=F.failures + 1)
    stmt = insert(F).values(
        kind=kind, target=key, failures=1,
        locked_until=None, updated_at=now,
    ).on_conflict_do_update(
        index_elements=[F.kind, F.target],
        set_={'failures': failures,
              'locked_until': case((failures >= max_attempts, until), else_=None),
              'updated_at': now},
        where=or_(F.locked_until.is_(None), F.locked_until <= now),
    )
    if db.session.get_bind().dialect.insert_returning:
        counted = db.session.execute(stmt.returning(F.failures)).scalar_one_or_none()
    else:
        # SQLite before 3.35: no RETURNING; the upsert holds the write lock until the
        # commit, so the read sees this attempt's count. No row changed = target locked.
        counted = None
        if db.session.execute(stmt.execution_options(preserve_rowcount=True)).rowcount:
            counted = db.session.execute(
                db.select(F.failures).filter_by(kind=kind, target=key)).scalar_one()
    db.session.commit()
    return counted is not None and counted <= max_attempts


def _clear_2fa_failures(kind: str, key: str):
    """Clear failed attempts on success."""
    from models.second_factor_failure import SecondFactorFailure
    db.session.execute(db.delete(SecondFactorFailure).filter_by(kind=kind, target=key))
    db.session.commit()


@bp.route('/api/v2/auth/methods', methods=['GET', 'POST'])
def detect_auth_methods():
    """
    Detect available authentication methods.

    GET and POST answer the same, whatever the body: no per-user detail before login.

    If the mTLS middleware already auto-logged the user in (session exists),
    returns mtls_status='auto_logged_in' so the frontend can skip the login form.
    """
    methods = {
        'password': True,
        'mtls': False,
        'mtls_status': 'not_present',
        'webauthn': True,
        'webauthn_credentials': 0,
        'mtls_certificates': 0,
        'api_keys': True,
        'sso_providers': [],
    }

    # If middleware already auto-logged in via cert, signal it
    if session.get('user_id') and session.get('auth_method') == 'certificate':
        methods['mtls'] = True
        methods['mtls_status'] = 'auto_logged_in'
        methods['mtls_user'] = session.get('username')
        return success_response(data=methods)

    # Pre-authentication: never expose per-user credential counts (username oracle).

    # Detect mTLS cert presence (use middleware's parsed cert if available)
    cert_info = getattr(g, 'mtls_cert_info', None)
    if not cert_info:
        try:
            # Native gunicorn TLS — peercert is already validated by the stack.
            if request.environ.get('peercert'):
                cert_info = CertificateParser.extract_from_flask_native(
                    request.environ['peercert']
                )
            else:
                # Reverse-proxy headers — same trusted-proxy gate as login_mtls().
                # Case-insensitive mapping — do NOT dict() it (see login_mtls).
                headers = request.headers
                spoof_attempt = (
                    'X-SSL-Client-Verify' in headers
                    or 'X-SSL-Client-S-DN' in headers
                    or 'X-SSL-Client-Cert' in headers
                )
                if spoof_attempt and not trusted_proxy.is_request_from_trusted_proxy():
                    logger.warning(
                        "auth/methods: ignoring proxy cert headers from untrusted peer %s",
                        trusted_proxy.immediate_peer_addr(),
                    )
                elif 'X-SSL-Client-Verify' in headers:
                    cert_info = CertificateParser.extract_from_nginx_headers(headers)
                elif 'X-SSL-Client-S-DN' in headers:
                    cert_info = CertificateParser.extract_from_apache_headers(headers)
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
@limiter.limit("5/minute")
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

    # Input validation - prevent DoS and normalize input
    username = str(data['username']).strip()[:255]  # Max 255 chars
    password = str(data['password'])[:4096]  # OWASP recommends max 4096 for password

    if not username:
        return error_response('Username and password required', 400)

    # Find user.
    #
    # "not found" and "found but deactivated" deliberately give the same
    # answer, and give it BEFORE the password is checked: at this point the
    # caller has proved nothing, so telling the two apart would let anyone
    # enumerate accounts. The LDAP door says more — "This account has been
    # disabled", 403 — because it only reaches that check after the directory
    # accepted the user's own bind, so the caller has already proved the
    # password. The two messages are not a duplication to reconcile: they
    # answer at different points and must keep saying different things.
    # tests/test_auth_failure_messages.py pins both sides.
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

    # Check account lockout (using centralized settings)
    max_attempts, lockout_seconds = _get_2fa_lockout_settings()
    if user.locked_until and utc_now() < user.locked_until:
        # Same answer as an unknown name: the password is not checked yet, so a
        # distinct status would tell anyone the account exists.
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            resource_id=user.id,
            details=f'Login refused for {username} (account locked)',
            success=False,
            username=username
        )
        return error_response('Invalid credentials', 401)
    if user.locked_until and utc_now() >= user.locked_until:
        user.locked_until = None
        user.failed_logins = 0
        ok, _err = safe_commit(logger, "Failed to clear account lockout")
        if not ok:
            return _err

    # Verify password
    if not user.check_password(password):
        # Increment failed login counter
        user.failed_logins = (user.failed_logins or 0) + 1
        locked = user.failed_logins >= max_attempts
        if locked:
            user.locked_until = utc_now() + timedelta(seconds=lockout_seconds)
            logger.warning(f"Account {username} locked after {max_attempts} failed attempts")
        ok, _err = safe_commit(logger, "Failed to record failed login")
        if not ok:
            return _err
        if locked:
            from api.v2.sso.helpers import notify_account_locked
            notify_account_locked(username)
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
    ok, _err = safe_commit(logger, "Failed to update login stats")
    if not ok:
        return _err

    # Second factor: TOTP (with recovery codes) and/or a security key, the key
    # when 2FA is enforced or the user turned it on as second factor.
    from auth.twofa_enforcement import second_factor_methods
    second_factors = second_factor_methods(user)
    if second_factors:
        begin_session(user)
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
                'methods': second_factors,
                'user': {'id': user.id, 'username': user.username}
            },
            message='2FA verification required'
        )

    # Forced 2FA enrolment (#141): enforcement is ON for this local account and
    # it has no TOTP yet → establish a restricted session that can only reach the
    # 2FA enrolment endpoints until TOTP is confirmed.
    from auth.twofa_enforcement import must_enroll_2fa, ENROLL_SESSION_KEY
    if must_enroll_2fa(user, auth_method='password'):
        now = utc_now()
        begin_session(user)
        session['user_id'] = user.id
        session['username'] = user.username
        session['auth_method'] = 'password'
        session['login_time'] = now.isoformat()
        session['last_activity'] = now.isoformat()
        session[ENROLL_SESSION_KEY] = True
        session.permanent = True

        csrf_token = CSRFProtection.generate_token(user.id) if HAS_CSRF else None

        AuditService.log_action(
            action='login_2fa_enrollment_required',
            resource_type='user',
            resource_id=user.id,
            resource_name=username,
            details=f'2FA enforcement: enrolment required for {username}',
            success=True,
            username=username
        )

        return success_response(
            data={
                'requires_2fa_enrollment': True,
                'csrf_token': csrf_token,
                'user': {'id': user.id, 'username': user.username}
            },
            message='2FA enrolment required'
        )

    # No 2FA - create full session
    now = utc_now()
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = 'password'
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True

    # Get permissions
    from auth.permissions import get_effective_permissions
    permissions = get_effective_permissions(user)

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
        data=auth_session_payload(
            user, permissions=permissions, auth_method='password',
            csrf_token=csrf_token,
        ),
        message='Login successful'
    )


@bp.route('/api/v2/auth/login/2fa', methods=['POST'])
@limiter.limit("10/minute")
def login_2fa():
    """
    Complete login with TOTP 2FA code

    POST /api/v2/auth/login/2fa
    Body: {"code": "123456"}

    Requires a pending 2FA session (from password login)
    """
    from services.audit_service import AuditService

    # Pending 2FA session, with brute-force protection (SEC-03)
    user, lockout_key, err = _pending_2fa_user()
    if err:
        return err
    pending_username = user.username
    auth_method = session.get('pending_2fa_method', 'password')

    data = request.json
    if not data or not data.get('code'):
        return error_response('Verification code required', 400)

    # Input validation. This accepts both a TOTP code (6-8 digits) and a
    # recovery code, which is generated as four 4-hex-char groups joined by
    # dashes (XXXX-XXXX-XXXX-XXXX = 19 chars). The previous [:10] truncation
    # silently cut every recovery code down to 'XXXX-XXXX-', so it could never
    # match a stored code and account recovery was impossible. The cap stays,
    # just above the longest legitimate input rather than below it.
    code = str(data['code']).strip().upper()[:32]
    if not code or len(code) < 6:
        return error_response('Invalid verification code format', 400)
    if not _reserve_2fa_attempt(TWO_FA, lockout_key):
        return error_response('Too many failed attempts. Try again later.', 429)

    # Verify TOTP code (a key-only account has none to check), once only
    from auth.totp import consume_totp
    totp_ok = bool(user.totp_confirmed and user.totp_secret) and consume_totp(user, code)
    if totp_ok:
        ok, _err = safe_commit(logger, "Failed to record the TOTP step")
        if not ok:
            return _err
    else:
        # Check recovery codes - atomic verify-and-consume to prevent
        # double-spend (two parallel logins replaying the same code).
        from utils.backup_codes import consume_code, count_remaining
        if user.backup_codes and consume_code(user, code):
            try:
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Failed to consume backup code for {user.username}: {e}")
                return error_response('Invalid verification code', 401)
            recovery_used = True
            logger.info(
                "Recovery code used for %s, %d remaining",
                user.username, count_remaining(user.backup_codes),
            )
        else:
            AuditService.log_action(
                action='login_2fa_failure',
                resource_type='user',
                resource_id=user.id,
                details=f'Invalid 2FA code for {pending_username}',
                success=False,
                username=pending_username
            )
            return error_response('Invalid verification code', 401)

    _clear_2fa_failures(TWO_FA, lockout_key)
    return _complete_2fa_login(user, auth_method, f'Login successful with 2FA for {user.username}')


def _pending_2fa_user():
    """(user, lockout_key, error_response) for the login waiting on its second factor."""
    pending_user_id = session.get('pending_2fa_user_id')
    if not pending_user_id:
        return None, None, error_response('No pending 2FA verification', 401)
    lockout_key = str(pending_user_id)
    if _check_2fa_lockout(TWO_FA, lockout_key):
        return None, None, error_response('Too many failed attempts. Try again later.', 429)
    user = db.session.get(User, pending_user_id)
    from auth.session_start import session_is_current
    if not user or not user.active or not session_is_current(user):
        session.clear()
        return None, None, error_response('Invalid credentials', 401)
    return user, lockout_key, None


def _complete_2fa_login(user, auth_method, details):
    """Turn the pending 2FA session into a full one."""
    from auth.permissions import get_effective_permissions
    from services.audit_service import AuditService

    now = utc_now()
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = auth_method
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True

    permissions = get_effective_permissions(user)

    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=details,
        success=True,
        username=user.username
    )

    logger.info(f"✅ 2FA login successful: {user.username}")

    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(user.id)

    return success_response(
        data=auth_session_payload(
            user, permissions=permissions, auth_method=auth_method,
            csrf_token=csrf_token,
        ),
        message='Login successful'
    )


_2FA_WEBAUTHN_CHALLENGE = 'pending_2fa_webauthn_challenge'


@bp.route('/api/v2/auth/login/2fa/webauthn/options', methods=['POST'])
@limiter.limit("10/minute")
def login_2fa_webauthn_options():
    """Security-key challenge for the pending 2FA login, bound to this session."""
    user, _key, err = _pending_2fa_user()
    if err:
        return err
    options, challenge = WebAuthnService.authentication_options_for(user, request.host, '2fa')
    if not options:
        return error_response('No security key registered', 400)
    session[_2FA_WEBAUTHN_CHALLENGE] = challenge
    return success_response(data={'options': options})


@bp.route('/api/v2/auth/login/2fa/webauthn/verify', methods=['POST'])
@limiter.limit("10/minute")
def login_2fa_webauthn_verify():
    """Complete the pending 2FA login with a security key assertion."""
    from services.audit_service import AuditService

    user, lockout_key, err = _pending_2fa_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    credential_response = data.get('response')
    if not isinstance(credential_response, dict) or len(str(credential_response)) > 50000:
        return error_response('Invalid WebAuthn response format', 400)
    if not _reserve_2fa_attempt(TWO_FA, lockout_key):
        return error_response('Too many failed attempts. Try again later.', 429)

    # One attempt per challenge: whatever the outcome, the next try needs new options.
    expected = session.pop(_2FA_WEBAUTHN_CHALLENGE, None)
    ok = False
    if expected:
        ok, _msg, _user = WebAuthnService.verify_authentication(
            user.id, credential_response, request.host,
            challenge_type='2fa', expected_challenge=expected,
        )
    if not ok:
        AuditService.log_action(
            action='login_2fa_failure',
            resource_type='user',
            resource_id=user.id,
            details=f'Invalid security key for {user.username}',
            success=False,
            username=user.username
        )
        return error_response('Security key verification failed', 401)

    _clear_2fa_failures(TWO_FA, lockout_key)
    return _complete_2fa_login(
        user, session.get('pending_2fa_method', 'password'),
        f'Login successful with 2FA (security key) for {user.username}',
    )


@bp.route('/api/v2/auth/login/mtls', methods=['POST'])
@limiter.limit("10/minute")
def login_mtls():
    """
    mTLS (client certificate) login

    Certificate must be presented in request (via reverse proxy headers or native TLS)

    Returns session cookie + user info
    """
    # Extract certificate info
    cert_info = None
    try:
        # Native gunicorn TLS - already validated against the configured CA.
        if request.environ.get('peercert'):
            cert_info = CertificateParser.extract_from_flask_native(request.environ['peercert'])
        else:
            # Reverse-proxy headers - only honor when the immediate peer is
            # in UCM_TRUSTED_PROXIES (default: loopback). Without this gate
            # any caller who can reach gunicorn directly can spoof
            # X-SSL-Client-* headers and forge mTLS authentication.
            # request.headers is a case-insensitive mapping. Do NOT wrap it
            # in dict(): WSGI reconstructs header names title-cased
            # (X-Ssl-Client-Verify), so exact-case lookups against
            # dict(request.headers) never match and proxy cert auth dies.
            headers = request.headers
            spoof_attempt = (
                'X-SSL-Client-Verify' in headers
                or 'X-SSL-Client-S-DN' in headers
                or 'X-SSL-Client-Cert' in headers
            )
            if spoof_attempt and not trusted_proxy.is_request_from_trusted_proxy():
                logger.warning(
                    "mTLS login: ignoring proxy cert headers from untrusted peer %s",
                    trusted_proxy.immediate_peer_addr(),
                )
            elif 'X-SSL-Client-Verify' in headers:
                cert_info = CertificateParser.extract_from_nginx_headers(headers)
            elif 'X-SSL-Client-S-DN' in headers:
                cert_info = CertificateParser.extract_from_apache_headers(headers)
    except Exception as e:
        logger.error(f"Error extracting certificate: {e}")
        return error_response('Failed to extract client certificate', 500)

    if not cert_info:
        return error_response('No client certificate presented', 401)

    # Authenticate certificate
    user, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)

    if not user or not user.active:
        return error_response('Certificate authentication failed', 401)

    # Update login stats
    user.last_login = utc_now()
    user.login_count = (user.login_count or 0) + 1
    user.failed_logins = 0  # Reset failed logins on successful login
    ok, _err = safe_commit(logger, "Failed to update login stats")
    if not ok:
        return _err

    # Create session
    now = utc_now()
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = 'mtls'
    session['cert_serial'] = auth_cert.cert_serial
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True

    # Get permissions
    from auth.permissions import get_effective_permissions
    permissions = get_effective_permissions(user)

    logger.info(f"✅ mTLS login successful: {user.username} (cert: {auth_cert.cert_serial})")

    # Audit log success
    from services.audit_service import AuditService
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=f'mTLS login successful for {user.username} (cert: {auth_cert.cert_serial})',
        success=True,
        username=user.username
    )

    # Generate CSRF token
    csrf_token = None
    if HAS_CSRF:
        csrf_token = CSRFProtection.generate_token(user.id)

    return success_response(
        data=auth_session_payload(
            user, permissions=permissions, auth_method='mtls',
            csrf_token=csrf_token,
            certificate={
                'serial': auth_cert.cert_serial,
                'name': auth_cert.name
            },
        ),
        message='Login successful via mTLS'
    )


@bp.route('/api/v2/auth/login/webauthn/start', methods=['POST'])
@limiter.limit("10/minute")
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

    username = str(username).strip()[:255]
    if not username:
        return error_response('Username required', 400)

    # Anti-enumeration: this endpoint MUST return the same well-formed challenge
    # whether or not the username exists or has enabled credentials. A phantom
    # user gets decoy options (see generate_decoy_authentication_options); the
    # response and echoed username never depend on account existence.
    hostname = request.host
    secret = (current_app.secret_key or '').encode('utf-8')

    user = User.query.filter_by(username=username).first()
    creds = []
    if user and user.active:
        creds = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()

    try:
        options = None
        if creds:
            options, _user_id = WebAuthnService.generate_authentication_options(username, hostname)
        if not options:
            options = WebAuthnService.generate_decoy_authentication_options(username, hostname, secret)

        logger.info("WebAuthn auth started")

        return success_response(
            data={
                'options': options,
                'username': username,
            }
        )
    except Exception as e:
        logger.error(f"WebAuthn start error: {e}")
        # Even on failure, do not leak account state — return decoy options.
        try:
            options = WebAuthnService.generate_decoy_authentication_options(username, hostname, secret)
            return success_response(data={'options': options, 'username': username})
        except Exception:
            return error_response('Failed to generate WebAuthn options', 500)


@bp.route('/api/v2/auth/login/webauthn/verify', methods=['POST'])
@limiter.limit("5/minute")
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

    # Input validation - prevent DoS and normalize input
    username = str(data['username']).strip()[:255]  # Max 255 chars
    credential_response = data['response']

    if not username:
        return error_response('Username and response required', 400)

    # Validate credential_response is a dict and not too large
    if not isinstance(credential_response, dict) or len(str(credential_response)) > 50000:
        return error_response('Invalid WebAuthn response format', 400)

    # SEC-04: Brute-force protection on WebAuthn. Counted before the lookup, so an unknown
    # name locks exactly like a known one; its row goes with the purge of expired rows.
    if not _reserve_2fa_attempt(WEBAUTHN, username):
        return error_response('Too many failed attempts. Try again later.', 429)

    # Find user. Return the SAME generic error as a failed verification so this
    # path is not an existence oracle (mirrors webauthn_start's anti-enumeration).
    user = User.query.filter_by(username=username).first()
    if not user or not user.active:
        return error_response('WebAuthn verification failed', 401)
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
            return error_response('WebAuthn verification failed', 401)

        # Update login stats
        _clear_2fa_failures(WEBAUTHN, username)
        user.last_login = utc_now()
        user.login_count = (user.login_count or 0) + 1
        user.failed_logins = 0  # Reset failed logins on successful login
        ok, _err = safe_commit(logger, "Failed to update login stats")
        if not ok:
            return _err

        # Create session
        now = utc_now()
        begin_session(user)
        session['user_id'] = user.id
        session['username'] = user.username
        session['auth_method'] = 'webauthn'
        session['login_time'] = now.isoformat()
        session['last_activity'] = now.isoformat()
        session.permanent = True

        # Get permissions
        from auth.permissions import get_effective_permissions
        permissions = get_effective_permissions(user)

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
            data=auth_session_payload(
                user, permissions=permissions, auth_method='webauthn',
                csrf_token=csrf_token,
            ),
            message='Login successful via WebAuthn'
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"WebAuthn verification error: {e}")
        return error_response('WebAuthn verification failed', 401)


# NOTE: Logout endpoint is in auth.py (with @require_auth and WebSocket events)
