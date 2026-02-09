"""
WebAuthn API
Manage WebAuthn credentials for passwordless login
Uses WebAuthnService for proper cryptographic verification
"""

from flask import Blueprint, jsonify, request, g
from api.v2.auth import require_auth
from models import db
from models.webauthn import WebAuthnCredential
from services.webauthn_service import WebAuthnService
from services.audit_service import AuditService

bp = Blueprint('webauthn', __name__, url_prefix='/api/v2/webauthn')


@bp.route('/credentials', methods=['GET'])
@require_auth()
def list_credentials():
    """List user's WebAuthn credentials"""
    user = g.current_user
    credentials = WebAuthnService.get_user_credentials(user.id)
    return jsonify({'data': [c.to_dict() for c in credentials]})


@bp.route('/credentials/<int:credential_id>', methods=['DELETE'])
@require_auth()
def delete_credential(credential_id):
    """Delete a WebAuthn credential"""
    user = g.current_user
    success, message = WebAuthnService.delete_credential(credential_id, user.id)
    
    if not success:
        return jsonify({'error': True, 'message': message}), 404
    
    AuditService.log_action(
        action='webauthn_delete',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=f'Deleted WebAuthn credential {credential_id}',
        success=True
    )
    
    return jsonify({'message': message})


@bp.route('/credentials/<int:credential_id>/toggle', methods=['POST'])
@require_auth()
def toggle_credential(credential_id):
    """Enable/disable a WebAuthn credential"""
    user = g.current_user
    data = request.get_json() or {}
    enabled = data.get('enabled', True)
    
    success, message = WebAuthnService.toggle_credential(credential_id, user.id, enabled)
    
    if not success:
        return jsonify({'error': True, 'message': message}), 404
    
    AuditService.log_action(
        action='webauthn_toggle',
        resource_type='webauthn',
        resource_id=str(credential_id),
        resource_name=f'WebAuthn credential {credential_id}',
        details=f'{"Enabled" if enabled else "Disabled"} WebAuthn credential {credential_id}',
        success=True
    )
    
    return jsonify({'message': message})


@bp.route('/register/options', methods=['POST'])
@require_auth()
def registration_options():
    """Get WebAuthn registration options - uses WebAuthnService for proper crypto"""
    user = g.current_user
    hostname = request.host
    
    options = WebAuthnService.generate_registration_options(user, hostname)
    return jsonify({'data': options})


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
        return jsonify({'error': True, 'message': message}), 400
    
    AuditService.log_action(
        action='webauthn_register',
        resource_type='webauthn',
        resource_id=str(credential.id) if credential else None,
        resource_name=credential_name,
        details=f'Registered WebAuthn credential: {credential_name}',
        success=True
    )
    
    return jsonify({
        'message': message,
        'data': credential.to_dict() if credential else None
    })
