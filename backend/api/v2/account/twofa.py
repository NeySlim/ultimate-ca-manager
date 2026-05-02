import io
import base64
import secrets
import logging

from flask import request, g
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
import pyotp
import qrcode

from . import bp

logger = logging.getLogger(__name__)


# ============================================================================
# 2FA Management
# ============================================================================

@bp.route('/api/v2/account/2fa/enable', methods=['POST'])
@require_auth()
def enable_2fa():
    """Enable 2FA (TOTP) - generates QR code and secret"""
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    # Generate new TOTP secret
    secret = pyotp.random_base32()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.username,
        issuer_name='UCM'
    )

    # Store secret temporarily (will be confirmed with code)
    user.totp_secret = secret  # Store unconfirmed
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
@require_auth()
def confirm_2fa():
    """Confirm 2FA setup with verification code"""
    data = request.json
    code = data.get('code') if data else None

    if not code:
        return error_response('Verification code required', 400)

    user = User.query.get(g.current_user.id)
    if not user or not user.totp_secret:
        return error_response('2FA setup not initiated', 400)

    # Verify code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code):
        return error_response('Invalid verification code', 400)

    # Generate backup codes
    backup_codes = [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(8)]

    # Enable 2FA — backup codes are stored as scrypt hashes; the
    # plaintext list is only ever returned here.
    user.totp_confirmed = True
    user.backup_codes = backup_hash_codes(backup_codes)
    ok, _err = safe_commit(logger, "Failed to enable 2FA")
    if not ok:
        return _err

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
@require_auth()
def disable_2fa():
    """Disable 2FA"""
    data = request.json

    if not data:
        return error_response('Verification required', 400)

    code = data.get('code')
    backup_code = data.get('backup_code')

    if not code and not backup_code:
        return error_response('Code or backup code required', 400)

    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    # Verify with TOTP code
    if code:
        if not user.totp_secret:
            return error_response('2FA not enabled', 400)
        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(code):
            return error_response('Invalid verification code', 400)
    # Or verify with backup code
    elif backup_code:
        if not backup_verify(user.backup_codes, backup_code):
            return error_response('Invalid backup code', 400)

    # Disable 2FA
    user.totp_confirmed = False
    user.totp_secret = None
    user.backup_codes = None
    ok, _err = safe_commit(logger, "Failed to disable 2FA")
    if not ok:
        return _err

    AuditService.log_action(
        action='mfa_disable',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'2FA disabled for user: {user.username}',
        success=True
    )

    return success_response(message='2FA disabled successfully')


@bp.route('/api/v2/account/2fa/recovery-codes', methods=['GET'])
@require_auth()
def get_recovery_codes():
    """Get current recovery codes (masked)"""
    user = User.query.get(g.current_user.id)
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
@require_auth()
def regenerate_recovery_codes():
    """Regenerate recovery codes (invalidates old ones)"""
    data = request.json
    code = data.get('code') if data else None

    if not code:
        return error_response('2FA code required', 400)

    user = User.query.get(g.current_user.id)
    if not user or not user.totp_confirmed:
        return error_response('2FA not enabled', 400)

    # Verify code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code):
        return error_response('Invalid verification code', 400)

    # Generate new backup codes
    new_codes = [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(8)]

    user.backup_codes = backup_hash_codes(new_codes)
    ok, _err = safe_commit(logger, "Failed to regenerate backup codes")
    if not ok:
        return _err

    return success_response(
        data={'backup_codes': new_codes},
        message='Recovery codes regenerated. Save them now!'
    )
