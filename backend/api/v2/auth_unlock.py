"""Unlock a locked session with a factor of its own account.

POST /api/v2/auth/unlock/password                  the account's password (local, or its LDAP directory)
POST /api/v2/auth/unlock/2fa                       then the second factor a sign-in would ask: a code
POST /api/v2/auth/unlock/2fa/webauthn/options|verify   ... or a security key
POST /api/v2/auth/unlock/certificate               the client certificate of this request
POST /api/v2/auth/unlock/webauthn/options|verify   a passkey of the account

Each attempt is counted as the same sign-in door counts it and audited; success opens a
new session for the account under a new identifier, failure leaves the lock as it was.
"""
import logging

from flask import request, session

from api.v2.auth_methods import (
    TWO_FA, WEBAUTHN, _clear_2fa_failures, _get_2fa_lockout_settings, _reserve_2fa_attempt,
    bp, check_second_factor_code, presented_certificate, too_many_attempts,
)
from api.v2.sso.connection_tests import ATTEMPT_REFUSED, GROUPS_UNREADABLE, _ldap_authenticate_user
from api.v2.sso.ldap_routes import _ldap_local_account
from auth.session_lock import (
    UNLOCK_2FA_KEY, audit_unlock_failure, is_locked, locked_account, password_source,
)
from auth.session_start import begin_session
from models import db
from services.mtls_auth_service import MTLSAuthService
from services.webauthn_service import WebAuthnService
from utils.datetime_utils import utc_now
from utils.response import AUTHENTICATION_REQUIRED_PROBLEM, error_response, success_response

try:
    from app import limiter
except ImportError:  # pragma: no cover - the app always provides it
    limiter = None

logger = logging.getLogger(__name__)

_PASSKEY_CHALLENGE = 'unlock_webauthn_challenge'
_2FA_KEY_CHALLENGE = 'unlock_2fa_webauthn_challenge'
# How the session reopened says how it was proved, as the sign-in doors name it
_SESSION_METHOD = {'password': 'password', 'ldap': 'ldap', 'certificate': 'mtls', 'passkey': 'webauthn'}
_LABEL = {'password': 'password', 'ldap': 'directory password', 'certificate': 'client certificate',
          'passkey': 'passkey'}


def _limit(rule):
    return limiter.limit(rule) if limiter is not None else (lambda f: f)


def _locked_user():
    """(user, None) for the locked session's account, else (None, refusal)."""
    if not is_locked():
        if session.get('user_id'):
            return None, error_response('Session is not locked', 409)
        return None, error_response('Authentication required', 401,
                                    problem_type=AUTHENTICATION_REQUIRED_PROBLEM)
    user = locked_account()
    if user is None:
        audit_unlock_failure(session.get('username'), session.get('user_id'),
                             f"Unlock refused for {session.get('username')} (account disabled or gone)")
        return None, error_response('Invalid credentials', 401)
    return user, None


def _failed(user, method, reason, message='Invalid credentials', status=401):
    audit_unlock_failure(user.username, user.id,
                         f'Unlock refused for {user.username} ({_LABEL[method]}: {reason})')
    return error_response(message, status)


def _reopen(user, method, provider=None, second=None):
    """A new session of ``user`` in place of the locked one, as its sign-in would open it."""
    from auth.permissions import get_effective_permissions
    from auth.session_payload import auth_session_payload
    from auth.twofa_enforcement import ENROLL_SESSION_KEY, must_enroll_2fa
    from services.audit_service import AuditService
    now = utc_now()
    auth_method = _SESSION_METHOD[method]
    begin_session(user, unlocking=True)
    session['user_id'] = user.id
    session['username'] = user.username
    session['auth_method'] = auth_method
    if provider is not None:
        session['auth_provider'] = provider.display_name or provider.name
    session['login_time'] = now.isoformat()
    session['last_activity'] = now.isoformat()
    session.permanent = True
    enrol = must_enroll_2fa(user, auth_method='sso' if method == 'ldap' else auth_method,
                            provider=provider)
    if enrol:
        session[ENROLL_SESSION_KEY] = True
    how = _LABEL[method] + (f' and {second}' if second else '')
    AuditService.log_auth('session_unlocked', username=user.username, user_id=user.id,
                          details=f'Session unlocked by {user.username} ({how})')
    csrf_token = None
    try:
        from security.csrf import CSRFProtection
        csrf_token = CSRFProtection.generate_token(user.id)
    except ImportError:  # pragma: no cover
        pass
    extra = {'requires_2fa_enrollment': True} if enrol else {}
    return success_response(data=auth_session_payload(
        user, permissions=get_effective_permissions(user), auth_method=auth_method,
        csrf_token=csrf_token, **extra), message='Session unlocked')


# --- Password, then the second factor a sign-in asks -----------------------------------

@bp.route('/api/v2/auth/unlock/password', methods=['POST'])
@_limit('5/minute')
def unlock_password():
    user, err = _locked_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    password = data.get('password') if isinstance(data, dict) else None
    if not password:
        return error_response('Password required', 400)
    password = str(password)[:4096]
    source, provider = password_source(user)
    if source is None:
        return error_response('This account has no password to unlock with', 400)
    if source == 'ldap':
        refused = _check_directory_password(user, provider, password)
        method = 'ldap'
    else:
        refused = _check_local_password(user, password)
        method = 'password'
    if refused:
        return refused

    from auth.twofa_enforcement import second_factor_methods
    factors = second_factor_methods(user)
    if factors:
        # The lock stays until the second factor: the password alone opens nothing
        session[UNLOCK_2FA_KEY] = {'user_id': user.id, 'method': method,
                                   'provider_id': provider.id if provider is not None else None}
        return success_response(data={'requires_2fa': True, 'methods': factors},
                                message='2FA verification required')
    return _reopen(user, method, provider)


def _check_local_password(user, password):
    """None once the password is right, counted and admitted as the password sign-in does."""
    from api.v2.sso.helpers import announce_account_locked
    max_attempts, lockout_seconds = _get_2fa_lockout_settings()
    try:
        rank, armed = user.reserve_login_attempt(max_attempts, lockout_seconds)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to record the unlock attempt of {user.username}: {e}", exc_info=True)
        return error_response('Failed to record login attempt', 500)
    if rank is None or not user.check_password(password):
        if armed:
            announce_account_locked(f'Account {user.username}', user.username, max_attempts)
        return _failed(user, 'password', 'account locked' if rank is None else 'invalid password')
    try:
        user.clear_failed_logins()
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to clear the failed logins of {user.username}: {e}", exc_info=True)
        return error_response('Failed to update login stats', 500)
    return None


def _check_directory_password(user, provider, password):
    """None once the directory accepts the password of the entry this account opens with,
    counted as the LDAP sign-in counts it; the entry of another account is never bound."""
    from api.v2.sso.helpers import (
        _clear_ldap_failed_attempts, _ldap_attempt_failed, _release_ldap_attempt,
        _reserve_ldap_attempt)
    attempt = {}

    def reserve(identity):
        local = _ldap_local_account(provider, identity)
        if local is None or local.id != user.id:
            attempt['other'] = True
            return False
        try:
            attempt['local'], attempt['rank'], attempt['armed'] = _reserve_ldap_attempt(local)
        except Exception as e:
            logger.error(f"Failed to record the unlock attempt of {user.username}: {e}", exc_info=True)
            attempt['failed'] = True
            return False
        return attempt['rank'] is not None

    identity, error = _ldap_authenticate_user(provider, user.username, password, before_bind=reserve)
    local, armed = attempt.get('local'), attempt.get('armed')
    if attempt.get('failed'):
        return error_response('Failed to record login attempt', 500)
    if not error:
        opened = _ldap_local_account(provider, identity)
        if opened is None or opened.id != user.id:
            _release_ldap_attempt(local, armed)
            return _failed(user, 'ldap', 'directory entry of another account')
    if error:
        if error == ATTEMPT_REFUSED and attempt.get('other'):
            return _failed(user, 'ldap', 'directory entry of another account')
        if error in ('account_disabled', 'group_denied', GROUPS_UNREADABLE):
            _release_ldap_attempt(local, armed)
            return _failed(user, 'ldap', f'refused by the directory ({error})', 'Access denied', 403)
        _ldap_attempt_failed(local, armed)
        return _failed(user, 'ldap', 'account locked' if error == ATTEMPT_REFUSED else 'invalid password')
    if not _clear_ldap_failed_attempts(local):
        _ldap_attempt_failed(local, armed)
        return error_response('Failed to update login stats', 500)
    return None


def _pending_second_factor():
    """(user, pending, None) for an unlock whose password was right, else (None, None, refusal)."""
    user, err = _locked_user()
    if err:
        return None, None, err
    pending = session.get(UNLOCK_2FA_KEY)
    if not isinstance(pending, dict) or pending.get('user_id') != user.id:
        return None, None, error_response('No pending 2FA verification', 401)
    if not _reserve_2fa_attempt(TWO_FA, str(user.id)):
        return None, None, too_many_attempts(TWO_FA, str(user.id))
    return user, pending, None


def _reopen_after_second_factor(user, pending, second):
    from models.sso import SSOProvider
    session.pop(UNLOCK_2FA_KEY, None)
    _clear_2fa_failures(TWO_FA, str(user.id))
    provider_id = pending.get('provider_id')
    provider = db.session.get(SSOProvider, provider_id) if provider_id else None
    return _reopen(user, pending['method'], provider, second)


@bp.route('/api/v2/auth/unlock/2fa', methods=['POST'])
@_limit('10/minute')
def unlock_2fa():
    _user, err = _locked_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    code = str(data.get('code') or '').strip().upper()[:32] if isinstance(data, dict) else ''
    if len(code) < 6:
        return error_response('Invalid verification code format', 400)
    user, pending, err = _pending_second_factor()
    if err:
        return err
    ok, err = check_second_factor_code(user, code)
    if err:
        return err
    if not ok:
        return _failed(user, pending['method'], 'invalid two-factor code', 'Invalid verification code')
    return _reopen_after_second_factor(user, pending, 'two-factor code')


@bp.route('/api/v2/auth/unlock/2fa/webauthn/options', methods=['POST'])
@_limit('10/minute')
def unlock_2fa_webauthn_options():
    user, err = _locked_user()
    if err:
        return err
    pending = session.get(UNLOCK_2FA_KEY)
    if not isinstance(pending, dict) or pending.get('user_id') != user.id:
        return error_response('No pending 2FA verification', 401)
    options, challenge = WebAuthnService.authentication_options_for(user, request.host, '2fa')
    if not options:
        return error_response('No security key registered', 400)
    session[_2FA_KEY_CHALLENGE] = challenge
    return success_response(data={'options': options})


@bp.route('/api/v2/auth/unlock/2fa/webauthn/verify', methods=['POST'])
@_limit('10/minute')
def unlock_2fa_webauthn_verify():
    _user, err = _locked_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    response = data.get('response') if isinstance(data, dict) else None
    if not isinstance(response, dict) or len(str(response)) > 50000:
        return error_response('Invalid WebAuthn response format', 400)
    user, pending, err = _pending_second_factor()
    if err:
        return err
    # One attempt per challenge: whatever the outcome, the next try needs new options
    expected = session.pop(_2FA_KEY_CHALLENGE, None)
    ok = bool(expected) and WebAuthnService.verify_authentication(
        user.id, response, request.host, challenge_type='2fa', expected_challenge=expected)[0]
    if not ok:
        return _failed(user, pending['method'], 'invalid security key', 'Security key verification failed')
    return _reopen_after_second_factor(user, pending, 'security key')


# --- Client certificate -----------------------------------------------------------------

@bp.route('/api/v2/auth/unlock/certificate', methods=['POST'])
@_limit('10/minute')
def unlock_certificate():
    user, err = _locked_user()
    if err:
        return err
    if not MTLSAuthService.is_mtls_enabled():
        return error_response('Client certificate authentication is disabled', 400)
    cert_info, err = presented_certificate()
    if err:
        return err
    if not cert_info:
        return _failed(user, 'certificate', 'no certificate presented', 'No client certificate presented')
    owner, auth_cert, error = MTLSAuthService.authenticate_certificate(cert_info)
    if owner is None or auth_cert is None:
        return _failed(user, 'certificate', f'certificate refused: {error}', 'Certificate authentication failed')
    # The certificate opens its own account only: never another account's session
    if owner.id != user.id:
        return _failed(user, 'certificate', f'certificate of another account, {owner.username}',
                       'Certificate authentication failed')
    return _reopen(user, 'certificate')


# --- Passkey ----------------------------------------------------------------------------

@bp.route('/api/v2/auth/unlock/webauthn/options', methods=['POST'])
@_limit('10/minute')
def unlock_webauthn_options():
    user, err = _locked_user()
    if err:
        return err
    options, challenge = WebAuthnService.authentication_options_for(user, request.host, 'unlock')
    if not options:
        return error_response('No passkey registered', 400)
    session[_PASSKEY_CHALLENGE] = challenge
    return success_response(data={'options': options})


@bp.route('/api/v2/auth/unlock/webauthn/verify', methods=['POST'])
@_limit('5/minute')
def unlock_webauthn_verify():
    user, err = _locked_user()
    if err:
        return err
    data = request.get_json(silent=True) or {}
    response = data.get('response') if isinstance(data, dict) else None
    if not isinstance(response, dict) or len(str(response)) > 50000:
        return error_response('Invalid WebAuthn response format', 400)
    if not _reserve_2fa_attempt(WEBAUTHN, user.username):
        return too_many_attempts(WEBAUTHN, user.username)
    expected = session.pop(_PASSKEY_CHALLENGE, None)
    if not expected:
        return _failed(user, 'passkey', 'no challenge asked', 'WebAuthn verification failed')
    ok = False
    try:
        ok = WebAuthnService.verify_authentication(
            user.id, response, request.host, challenge_type='unlock', expected_challenge=expected)[0]
    except Exception as e:  # noqa: BLE001 - a malformed assertion is a failed one
        db.session.rollback()
        logger.warning(f"Passkey unlock verification error for {user.username}: {e}")
    if not ok:
        owner = _passkey_owner(response)
        reason = (f'passkey of another account, {owner.username}'
                  if owner is not None and owner.id != user.id else 'invalid passkey')
        return _failed(user, 'passkey', reason, 'WebAuthn verification failed')
    _clear_2fa_failures(WEBAUTHN, user.username)
    return _reopen(user, 'passkey')


def _passkey_owner(response):
    """The account the presented credential belongs to, for the audit; None if unknown."""
    from models import User
    from models.webauthn import WebAuthnCredential
    from services.webauthn_service import base64url_decode
    try:
        credential_id = base64url_decode(str(response.get('id') or ''))
    except Exception:  # noqa: BLE001 - not a credential id
        return None
    row = WebAuthnCredential.query.filter_by(credential_id=credential_id).first()
    return db.session.get(User, row.user_id) if row is not None else None
