"""
WebAuthn API
Manage WebAuthn credentials for passwordless login
Uses WebAuthnService for proper cryptographic verification
"""

from flask import Blueprint, request, g, session
from auth.unified import require_auth
from auth.twofa_enforcement import ENROLL_SESSION_KEY, would_leave_no_second_factor
from models import db
from models.webauthn import WebAuthnCredential
from services.webauthn_service import WebAuthnService
from services.audit_service import AuditService
from utils.response import success_response, error_response

bp = Blueprint('webauthn', __name__, url_prefix='/api/v2/webauthn')


_LAST_FACTOR_MESSAGE = ('2FA is enforced for your account: keep TOTP or another '
                        'security key before removing this one')


def _strips_last_factor(user, credential_id):
    """Own enabled key whose removal would leave enforced 2FA without a factor.

    An administrator acting on someone else's key is not blocked (recovery of a lost key).
    """
    credential = db.session.get(WebAuthnCredential, credential_id)
    if not credential or credential.user_id != user.id or not credential.enabled:
        return False
    return would_leave_no_second_factor(credential.user, dropping_key=credential.id)


@bp.route('/credentials', methods=['GET'])
@require_auth()
def list_credentials():
    """List user's WebAuthn credentials"""
    user = g.current_user
    credentials = WebAuthnService.get_user_credentials(user.id)
    return success_response(data=[c.to_dict() for c in credentials])


@bp.route('/credentials/<int:credential_id>', methods=['DELETE'])
@require_auth()
def delete_credential(credential_id):
    """Delete a WebAuthn credential"""
    user = g.current_user
    if _strips_last_factor(user, credential_id):
        return error_response(_LAST_FACTOR_MESSAGE, 403)
    success, message = WebAuthnService.delete_credential(credential_id, user.id)
    
    if not success:
        return error_response(message, 404)
    
    AuditService.log_action(
        action='webauthn_delete',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=f'Deleted WebAuthn credential {credential_id}',
        success=True
    )
    
    return success_response(message=message)


@bp.route('/credentials/<int:credential_id>/toggle', methods=['POST'])
@require_auth()
def toggle_credential(credential_id):
    """Enable/disable a WebAuthn credential"""
    user = g.current_user
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    if not enabled and _strips_last_factor(user, credential_id):
        return error_response(_LAST_FACTOR_MESSAGE, 403)
    
    success, message = WebAuthnService.toggle_credential(credential_id, user.id, enabled)
    
    if not success:
        return error_response(message, 404)
    
    AuditService.log_action(
        action='webauthn_toggle',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=f'{"Enabled" if enabled else "Disabled"} WebAuthn credential {credential_id}',
        success=True
    )
    
    return success_response(message=message)


@bp.route('/register/options', methods=['POST'])
@require_auth()
def registration_options():
    """Get WebAuthn registration options - uses WebAuthnService for proper crypto"""
    user = g.current_user
    hostname = request.host
    
    options = WebAuthnService.generate_registration_options(user, hostname)
    return success_response(data=options)


@bp.route('/register/verify', methods=['POST'])
@require_auth()
def verify_registration():
    """Verify WebAuthn registration and create credential"""
    user = g.current_user
    data = request.get_json()
    
    credential_data = data.get('credential', {})
    credential_name = data.get('name', 'Security Key')
    hostname = request.host
    
    success, message, credential = WebAuthnService.verify_registration(
        user.id, credential_data, hostname, credential_name
    )
    
    if not success:
        return error_response(message, 400)

    # A registered key satisfies a forced-enrolment session (#141): lift the gate.
    if session.pop(ENROLL_SESSION_KEY, None) is not None:
        session.modified = True
    
    AuditService.log_action(
        action='webauthn_register',
        resource_type='webauthn',
        resource_id=str(credential.id) if credential else None,
        resource_name=credential_name,
        details=f'Registered WebAuthn credential: {credential_name}',
        success=True
    )
    
    return success_response(data=credential.to_dict() if credential else None, message=message)
