"""
WebAuthn API
Manage WebAuthn credentials for passwordless login
Uses WebAuthnService for proper cryptographic verification
"""

import logging

from flask import Blueprint, request, g, session
from auth.unified import require_auth
from auth.twofa_enforcement import (
    ENROLL_SESSION_KEY, last_factor_refusal, lock_for_factor_change,
)
from models import db
from models.webauthn import WebAuthnCredential
from services.webauthn_service import WebAuthnService
from services.audit_service import AuditService
from utils.response import success_response, error_response
from auth.session_start import (
    closed_sessions_note, end_sessions_on_commit, keep_own_session, other_sessions_closed,
)

logger = logging.getLogger(__name__)

bp = Blueprint('webauthn', __name__, url_prefix='/api/v2/webauthn')


_LAST_FACTOR_MESSAGE = ('Your account requires a second factor: keep TOTP or another '
                        'security key, or turn off the security key as second factor first')


def _strips_last_factor(user, credential_id):
    """Own enabled key whose removal would leave required 2FA without a factor.

    Read under the user row lock, held until the removal commits. Someone else's
    key is left to the service, which refuses it.
    """
    credential = db.session.get(WebAuthnCredential, credential_id)
    if not credential or credential.user_id != user.id or not credential.enabled:
        return False
    _owner, refused = lock_for_factor_change(credential.user_id, dropping_key=credential.id)
    return refused


@bp.route('/credentials', methods=['GET'])
@require_auth()
def list_credentials():
    """List user's WebAuthn credentials"""
    user = g.current_user
    credentials = WebAuthnService.get_user_credentials(user.id)
    return success_response(data=[c.to_dict() for c in credentials])


@bp.route('/credentials/<int:credential_id>', methods=['DELETE'])
@require_auth(session_only=True)
def delete_credential(credential_id):
    """Delete a WebAuthn credential"""
    user = g.current_user
    if _strips_last_factor(user, credential_id):
        return last_factor_refusal(_LAST_FACTOR_MESSAGE)
    # A factor change closes the account's other sessions, as a password change
    owner = end_sessions_on_commit(user.id)
    if owner is None:
        db.session.rollback()
        return error_response('User not found', 404)
    success, message = WebAuthnService.delete_credential(credential_id, user.id)
    if not success:
        db.session.rollback()
        return error_response(message, 404)
    closed = other_sessions_closed(owner)

    AuditService.log_action(
        action='webauthn_delete',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=f'Deleted WebAuthn credential {credential_id} ({closed_sessions_note(closed)})',
        success=True
    )
    keep_own_session(owner)

    return success_response(message=message, meta={'other_sessions_closed': closed})


@bp.route('/credentials/<int:credential_id>/toggle', methods=['POST'])
@require_auth(session_only=True)
def toggle_credential(credential_id):
    """Enable/disable a WebAuthn credential"""
    user = g.current_user
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    if not enabled and _strips_last_factor(user, credential_id):
        return last_factor_refusal(_LAST_FACTOR_MESSAGE)
    # A key left as it was changes no factor: no session closes
    current = db.session.get(WebAuthnCredential, credential_id)
    if current and current.user_id == user.id and current.enabled == bool(enabled):
        db.session.rollback()
        return success_response(message=f'Credential already {"enabled" if enabled else "disabled"}',
                                meta={'other_sessions_closed': 0})
    owner = end_sessions_on_commit(user.id)
    if owner is None:
        db.session.rollback()
        return error_response('User not found', 404)
    success, message = WebAuthnService.toggle_credential(credential_id, user.id, enabled)
    if not success:
        db.session.rollback()
        return error_response(message, 404)
    closed = other_sessions_closed(owner)

    AuditService.log_action(
        action='webauthn_toggle',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=(f'{"Enabled" if enabled else "Disabled"} WebAuthn credential {credential_id} '
                 f'({closed_sessions_note(closed)})'),
        success=True
    )
    keep_own_session(owner)

    return success_response(message=message, meta={'other_sessions_closed': closed})


@bp.route('/register/options', methods=['POST'])
@require_auth(session_only=True)
def registration_options():
    """Get WebAuthn registration options - uses WebAuthnService for proper crypto"""
    user = g.current_user
    hostname = request.host
    
    options = WebAuthnService.generate_registration_options(user, hostname)
    return success_response(data=options)


@bp.route('/register/verify', methods=['POST'])
@require_auth(session_only=True)
def verify_registration():
    """Verify WebAuthn registration and create credential"""
    user = g.current_user
    data = request.get_json()
    
    credential_data = data.get('credential', {})
    credential_name = data.get('name', 'Security Key')
    hostname = request.host

    owner = end_sessions_on_commit(user.id)
    if owner is None:
        db.session.rollback()
        return error_response('User not found', 404)
    # A key registered under forced enrolment (#141) stays the user's second factor if
    # enforcement is lifted later: the flag rides the key's own commit, the gate goes after it.
    enrolling = session.get(ENROLL_SESSION_KEY) is not None
    success, message, credential = WebAuthnService.verify_registration(
        user.id, credential_data, hostname, credential_name,
        second_factor_of=owner if enrolling else None
    )
    if not success:
        db.session.rollback()
        return error_response(message, 400)
    if enrolling:
        session.pop(ENROLL_SESSION_KEY, None)
        session.modified = True
    closed = other_sessions_closed(owner)

    AuditService.log_action(
        action='webauthn_register',
        resource_type='webauthn',
        resource_id=str(credential.id) if credential else None,
        resource_name=credential_name,
        details=f'Registered WebAuthn credential: {credential_name} ({closed_sessions_note(closed)})',
        success=True
    )
    keep_own_session(owner)

    return success_response(data=credential.to_dict() if credential else None, message=message,
                            meta={'other_sessions_closed': closed})
