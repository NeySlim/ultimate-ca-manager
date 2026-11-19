import io
import base64
import secrets
import logging

from flask import request, g, session
from models import db, User
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.backup_codes import (
    count_remaining as backup_count,
    hash_codes as backup_hash_codes,
    verify_code_only as backup_verify,
)
from auth.unified import require_auth
from auth.twofa_enforcement import (
    enforcement_active_for, has_security_key, lock_for_factor_change, lock_user,
)
import pyotp
from auth.totp import consume_totp
import qrcode

from . import bp

logger = logging.getLogger(__name__)


def _code_checks_locked(user_id):
    """The 429 to answer while the account's second factor is locked, or None.

    Same counter as the login's second step: the secret guessed is the same, so a
    stolen session gets no tries beyond what the login allows."""
    from api.v2.auth_methods import _2fa_failed_attempts, _check_2fa_lockout
    if _check_2fa_lockout(str(user_id), _2fa_failed_attempts):
        return error_response('Too many failed attempts. Try again later.', 429)
    return None


def _code_check_failed(user_id):
    from api.v2.auth_methods import _2fa_failed_attempts, _record_2fa_failure
    _record_2fa_failure(str(user_id), _2fa_failed_attempts)


def _code_check_passed(user_id):
    from api.v2.auth_methods import _2fa_failed_attempts, _clear_2fa_failures
    _clear_2fa_failures(str(user_id), _2fa_failed_attempts)


# ============================================================================
# 2FA Management
# ============================================================================

@bp.route('/api/v2/account/2fa/enable', methods=['POST'])
@require_auth(session_only=True)
def enable_2fa():
    """Enable 2FA (TOTP) - generates QR code and secret"""
    user = db.session.get(User, g.current_user.id)
    if not user:
        return error_response('User not found', 404)
    if user.totp_confirmed:
        return error_response('2FA is already enabled; disable it first', 409)

    # Generate new TOTP secret
    secret = pyotp.random_base32()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.username,
        issuer_name='UCM'
    )

    # Store secret temporarily (will be confirmed with code)
    user.totp_secret = secret  # Store unconfirmed
    user.totp_last_step = None  # steps of the old secret say nothing about this one
    ok, _err = safe_commit(logger, "Failed to initialize 2FA")
    if not ok:
        return _err

    # Generate QR code
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(totp_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    qr_base64 = base64.b64encode(buffer.getvalue()).decode()

    return success_response(
        data={
            'secret': secret,
            'qr_code': f'data:image/png;base64,{qr_base64}',
        },
        message='Scan QR code with authenticator app, then verify with code'
    )


@bp.route('/api/v2/account/2fa/confirm', methods=['POST'])
@require_auth(session_only=True)
def confirm_2fa():
    """Confirm 2FA setup with verification code"""
    data = request.json
    code = data.get('code') if data else None

    if not code:
        return error_response('Verification code required', 400)

    user = db.session.get(User, g.current_user.id)
    if not user or not user.totp_secret:
        return error_response('2FA setup not initiated', 400)
    # A confirmed secret is the login's factor: no code of it is checked here
    if user.totp_confirmed:
        return error_response('2FA is already enabled; disable it first', 409)

    # Verify code, once only
    if not consume_totp(user, code):
        return error_response('Invalid verification code', 400)

    # Generate backup codes
    backup_codes = [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(8)]

    # Enable 2FA — backup codes are stored hashed; the
    # plaintext list is only ever returned here.
    user.totp_confirmed = True
    user.backup_codes = backup_hash_codes(backup_codes)
    ok, _err = safe_commit(logger, "Failed to enable 2FA")
    if not ok:
        return _err

    # If this confirmation satisfied a forced-enrolment session (#141), lift the
    # gate so the now-enrolled user gets a full session.
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    if session.pop(ENROLL_SESSION_KEY, None) is not None:
        session.modified = True

    AuditService.log_action(
        action='mfa_enable',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'2FA enabled for user: {user.username}',
        success=True
    )

    return success_response(
        data={'backup_codes': backup_codes},
        message='2FA enabled successfully. Save backup codes!'
    )


@bp.route('/api/v2/account/2fa/disable', methods=['POST'])
@require_auth(session_only=True)
def disable_2fa():
    """Disable 2FA"""
    data = request.json

    if not data:
        return error_response('Verification required', 400)

    code = data.get('code')
    backup_code = data.get('backup_code')

    if not code and not backup_code:
        return error_response('Code or backup code required', 400)

    # Required 2FA (#141, or a key turned on as second factor) keeps one factor;
    # checked under the user row lock so a concurrent key removal cannot race it.
    user, refused = lock_for_factor_change(g.current_user.id, dropping_totp=True)
    if not user:
        return error_response('User not found', 404)
    if refused:
        return error_response(
            'Your account requires a second factor: register a security key before disabling TOTP', 403)
    # Refused whatever the code, so checked before the lockout: no attempt is used up
    if not user.totp_secret:
        return error_response('2FA not enabled', 400)
    # A secret not confirmed yet is no factor of the login: its codes are not counted
    counted = bool(user.totp_confirmed)
    locked = _code_checks_locked(user.id) if counted else None
    if locked:
        return locked

    # Verify with TOTP code
    if code:
        if not consume_totp(user, code):
            if counted:
                _code_check_failed(user.id)
            return error_response('Invalid verification code', 400)
    # Or verify with backup code
    elif backup_code:
        if not backup_verify(user.backup_codes, backup_code):
            if counted:
                _code_check_failed(user.id)
            return error_response('Invalid backup code', 400)

    # Disable 2FA. Under enforcement the remaining key becomes the user's own
    # second factor, so lifting enforcement later does not silently drop it.
    if enforcement_active_for(user) and has_security_key(user):
        user.webauthn_2fa = True
    user.totp_confirmed = False
    user.totp_secret = None
    user.backup_codes = None
    ok, _err = safe_commit(logger, "Failed to disable 2FA")
    if not ok:
        return _err
    if counted:
        _code_check_passed(user.id)

    AuditService.log_action(
        action='mfa_disable',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'2FA disabled for user: {user.username}',
        success=True
    )

    return success_response(message='2FA disabled successfully')


@bp.route('/api/v2/account/2fa/webauthn', methods=['PUT'])
@require_auth(session_only=True)
def set_webauthn_second_factor():
    """Turn a security key on or off as the second factor of password logins.

    PUT /api/v2/account/2fa/webauthn
    Body: {"enabled": true} or {"enabled": false, "password": "..."}
    """
    data = request.get_json(silent=True) or {}
    enabled = data.get('enabled') if isinstance(data, dict) else None
    if not isinstance(enabled, bool):
        return error_response('enabled must be true or false', 400)

    user = lock_user(g.current_user.id)
    if not user:
        return error_response('User not found', 404)
    if enabled and not has_security_key(user):
        return error_response('Register a security key first', 400)
    if not enabled and (user.auth_source or 'local') == 'local':
        password = data.get('password')
        if not isinstance(password, str) or not user.check_password(password):
            return error_response('Invalid password', 403)

    user.webauthn_2fa = enabled
    ok, _err = safe_commit(logger, "Failed to update the security key second factor")
    if not ok:
        return _err

    AuditService.log_action(
        action='mfa_webauthn_enable' if enabled else 'mfa_webauthn_disable',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Security key as second factor {"enabled" if enabled else "disabled"} for {user.username}',
        success=True
    )
    return success_response(data={'webauthn_2fa': enabled})


@bp.route('/api/v2/account/2fa/recovery-codes', methods=['GET'])
@require_auth(session_only=True)
def get_recovery_codes():
    """Get current recovery codes (masked)"""
    user = db.session.get(User, g.current_user.id)
    if not user or not user.totp_confirmed:
        return error_response('2FA not enabled', 400)

    # Codes are stored hashed — we can no longer show a masked
    # plaintext preview. Only the count is exposed.
    remaining = backup_count(user.backup_codes)
    return success_response(
        data={
            'codes': [],
            'count': remaining,
        }
    )


@bp.route('/api/v2/account/2fa/recovery-codes/regenerate', methods=['POST'])
@require_auth(session_only=True)
def regenerate_recovery_codes():
    """Regenerate recovery codes (invalidates old ones)"""
    data = request.json
    code = data.get('code') if data else None

    if not code:
        return error_response('2FA code required', 400)

    user = db.session.get(User, g.current_user.id)
    if not user or not user.totp_confirmed:
        return error_response('2FA not enabled', 400)
    locked = _code_checks_locked(user.id)
    if locked:
        return locked

    # Verify code, once only
    if not consume_totp(user, code):
        _code_check_failed(user.id)
        return error_response('Invalid verification code', 400)

    # Generate new backup codes
    new_codes = [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(8)]

    user.backup_codes = backup_hash_codes(new_codes)
    ok, _err = safe_commit(logger, "Failed to regenerate backup codes")
    if not ok:
        return _err
    _code_check_passed(user.id)

    return success_response(
        data={'backup_codes': new_codes},
        message='Recovery codes regenerated. Save them now!'
    )
