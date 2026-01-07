"""
WebAuthn API
FIDO2/U2F passwordless authentication endpoints
"""
from flask import Blueprint, request, jsonify, session
from flask_jwt_extended import jwt_required, get_jwt_identity, create_access_token, create_refresh_token
from datetime import datetime
from models import db, User, AuditLog
from models.webauthn import WebAuthnCredential
from services.webauthn_service import WebAuthnService
import logging

logger = logging.getLogger(__name__)

webauthn_bp = Blueprint('webauthn', __name__)


def log_audit(action, username, details=None):
    """Helper to log WebAuthn actions"""
    log = AuditLog(
        username=username,
        action=action,
        resource_type='webauthn_credential',
        details=details,
        ip_address=request.remote_addr
    )
    db.session.add(log)
    db.session.commit()


# ==================== Registration ====================

@webauthn_bp.route('/register/options', methods=['POST'])
@jwt_required()
def registration_options():
    """
    Generate WebAuthn registration options
    ---
    POST /api/v1/webauthn/register/options
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        hostname = request.host
        options = WebAuthnService.generate_registration_options(user, hostname)
        
        return jsonify(options), 200
        
    except Exception as e:
        logger.error(f"Error generating registration options: {str(e)}")
        return jsonify({'error': str(e)}), 500


@webauthn_bp.route('/register/verify', methods=['POST'])
@jwt_required()
def registration_verify():
    """
    Verify WebAuthn registration response
    ---
    POST /api/v1/webauthn/register/verify
    Body: {credential response from navigator.credentials.create()}
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'error': 'User not found'}), 404
        
        data = request.get_json()
        credential_data = data.get('credential')
        credential_name = data.get('name', 'Security Key')
        
        if not credential_data:
            return jsonify({'error': 'Credential data required'}), 400
        
        hostname = request.host
        success, message, credential = WebAuthnService.verify_registration(
            user_id,
            credential_data,
            hostname,
            credential_name
        )
        
        if success:
            log_audit('register_webauthn', user.username, f"Registered credential: {credential_name}")
            
            return jsonify({
                'success': True,
                'message': message,
                'credential': credential.to_dict()
            }), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error verifying registration: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== Authentication ====================

@webauthn_bp.route('/authenticate/options', methods=['POST'])
def authentication_options():
    """
    Generate WebAuthn authentication options
    ---
    POST /api/v1/webauthn/authenticate/options
    Body: {"username": "admin"}
    """
    try:
        data = request.get_json()
        username = data.get('username')
        
        if not username:
            return jsonify({'error': 'Username required'}), 400
        
        hostname = request.host
        options, user_id = WebAuthnService.generate_authentication_options(username, hostname)
        
        if not options:
            return jsonify({'error': 'No credentials found for user'}), 404
        
        # Store user_id in session for verification
        session['webauthn_user_id'] = user_id
        
        return jsonify(options), 200
        
    except Exception as e:
        logger.error(f"Error generating authentication options: {str(e)}")
        return jsonify({'error': str(e)}), 500


@webauthn_bp.route('/authenticate/verify', methods=['POST'])
def authentication_verify():
    """
    Verify WebAuthn authentication response and create session
    ---
    POST /api/v1/webauthn/authenticate/verify
    Body: {credential response from navigator.credentials.get()}
    """
    try:
        user_id = session.get('webauthn_user_id')
        
        if not user_id:
            return jsonify({'error': 'No active authentication request'}), 400
        
        data = request.get_json()
        credential_data = data.get('credential')
        
        if not credential_data:
            return jsonify({'error': 'Credential data required'}), 400
        
        hostname = request.host
        success, message, user = WebAuthnService.verify_authentication(
            user_id,
            credential_data,
            hostname
        )
        
        if success and user:
            # Create session
            session['user_id'] = user.id
            session['username'] = user.username
            session['role'] = user.role
            session['auth_method'] = 'webauthn'
            
            # Update last login
            user.last_login = datetime.utcnow()
            db.session.commit()
            
            # Create JWT tokens
            access_token = create_access_token(identity=str(user.id))
            refresh_token = create_refresh_token(identity=str(user.id))
            
            session['access_token'] = access_token
            
            log_audit('login_webauthn', user.username, "Authenticated with WebAuthn")
            
            return jsonify({
                'success': True,
                'message': 'Authentication successful',
                'access_token': access_token,
                'refresh_token': refresh_token,
                'user': user.to_dict()
            }), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error verifying authentication: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== Credential Management ====================

@webauthn_bp.route('/credentials', methods=['GET'])
@jwt_required()
def get_credentials():
    """
    Get user's WebAuthn credentials
    ---
    GET /api/v1/webauthn/credentials
    """
    user_id = get_jwt_identity()
    credentials = WebAuthnService.get_user_credentials(user_id)
    
    return jsonify({
        'credentials': [cred.to_dict() for cred in credentials]
    }), 200


@webauthn_bp.route('/credentials/<int:credential_id>', methods=['DELETE'])
@jwt_required()
def delete_credential(credential_id):
    """
    Delete a WebAuthn credential
    ---
    DELETE /api/v1/webauthn/credentials/<id>
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        success, message = WebAuthnService.delete_credential(credential_id, user_id)
        
        if success:
            log_audit('delete_webauthn', user.username, f"Deleted credential ID: {credential_id}")
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error deleting credential: {str(e)}")
        return jsonify({'error': str(e)}), 500


@webauthn_bp.route('/credentials/<int:credential_id>/toggle', methods=['POST'])
@jwt_required()
def toggle_credential(credential_id):
    """
    Enable/disable a WebAuthn credential
    ---
    POST /api/v1/webauthn/credentials/<id>/toggle
    Body: {"enabled": true/false}
    """
    try:
        user_id = get_jwt_identity()
        user = User.query.get(user_id)
        
        data = request.get_json()
        enabled = data.get('enabled', True)
        
        success, message = WebAuthnService.toggle_credential(credential_id, user_id, enabled)
        
        if success:
            action = 'enabled' if enabled else 'disabled'
            log_audit(f'{action}_webauthn', user.username, f"{action.title()} credential ID: {credential_id}")
            return jsonify({'success': True, 'message': message}), 200
        else:
            return jsonify({'success': False, 'error': message}), 400
            
    except Exception as e:
        logger.error(f"Error toggling credential: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ==================== Settings ====================

@webauthn_bp.route('/available', methods=['GET'])
def check_availability():
    """
    Check if WebAuthn is available (browser support)
    This is a client-side check but we provide the endpoint
    ---
    GET /api/v1/webauthn/available
    """
    return jsonify({
        'available': True,
        'message': 'WebAuthn API endpoints are available. Client must check browser support.'
    }), 200
