"""
WebAuthn API
Manage WebAuthn credentials for passwordless login
"""

from flask import Blueprint, jsonify, request, session, g
from api.v2.auth import require_auth
from models import User, db
import secrets
import json
from datetime import datetime, timezone

bp = Blueprint('webauthn', __name__, url_prefix='/api/v2/webauthn')


@bp.route('/credentials', methods=['GET'])
@require_auth()
def list_credentials():
    """List user's WebAuthn credentials"""
    user = g.current_user
    
    # Get credentials from user metadata
    metadata = json.loads(user.metadata or '{}')
    credentials = metadata.get('webauthn_credentials', [])
    
    return jsonify({'data': credentials})


@bp.route('/credentials', methods=['POST'])
@require_auth()
def register_credential():
    """Register a new WebAuthn credential"""
    user = g.current_user
    data = request.get_json()
    
    # Parse credential data
    credential = {
        'id': secrets.token_urlsafe(16),
        'name': data.get('name', 'Security Key'),
        'type': data.get('type', 'security-key'),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'last_used': None,
        'credential_id': data.get('credential_id', ''),
        'public_key': data.get('public_key', '')
    }
    
    # Store in user metadata
    metadata = json.loads(user.metadata or '{}')
    credentials = metadata.get('webauthn_credentials', [])
    credentials.append(credential)
    metadata['webauthn_credentials'] = credentials
    user.metadata = json.dumps(metadata)
    db.session.commit()
    
    return jsonify({
        'data': credential,
        'message': 'WebAuthn credential registered'
    }), 201


@bp.route('/credentials/<credential_id>', methods=['DELETE'])
@require_auth()
def delete_credential(credential_id):
    """Delete a WebAuthn credential"""
    user = g.current_user
    
    metadata = json.loads(user.metadata or '{}')
    credentials = metadata.get('webauthn_credentials', [])
    
    # Find and remove credential
    credentials = [c for c in credentials if c['id'] != credential_id]
    metadata['webauthn_credentials'] = credentials
    user.metadata = json.dumps(metadata)
    db.session.commit()
    
    return jsonify({'message': 'Credential deleted'})


@bp.route('/register/options', methods=['POST'])
def registration_options():
    """Get WebAuthn registration options"""
    data = request.get_json()
    user_id = data.get('user_id')
    
    # Generate challenge
    challenge = secrets.token_urlsafe(32)
    session['webauthn_challenge'] = challenge
    
    return jsonify({
        'data': {
            'challenge': challenge,
            'rp': {
                'name': 'UCM - Certificate Manager',
                'id': request.host.split(':')[0]
            },
            'user': {
                'id': str(user_id),
                'name': data.get('username', 'user'),
                'displayName': data.get('display_name', 'User')
            },
            'pubKeyCredParams': [
                {'type': 'public-key', 'alg': -7},   # ES256
                {'type': 'public-key', 'alg': -257}  # RS256
            ],
            'timeout': 60000,
            'attestation': 'none',
            'authenticatorSelection': {
                'authenticatorAttachment': 'cross-platform',
                'userVerification': 'preferred'
            }
        }
    })


@bp.route('/authenticate/options', methods=['POST'])
def authentication_options():
    """Get WebAuthn authentication options"""
    data = request.get_json()
    username = data.get('username')
    
    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 404
    
    # Get user credentials
    metadata = json.loads(user.metadata or '{}')
    credentials = metadata.get('webauthn_credentials', [])
    
    # Generate challenge
    challenge = secrets.token_urlsafe(32)
    session['webauthn_challenge'] = challenge
    session['webauthn_user_id'] = user.id
    
    allow_credentials = [
        {
            'type': 'public-key',
            'id': c['credential_id']
        }
        for c in credentials if c.get('credential_id')
    ]
    
    return jsonify({
        'data': {
            'challenge': challenge,
            'timeout': 60000,
            'rpId': request.host.split(':')[0],
            'allowCredentials': allow_credentials,
            'userVerification': 'preferred'
        }
    })


@bp.route('/authenticate/verify', methods=['POST'])
def verify_authentication():
    """Verify WebAuthn authentication response"""
    # For now, trust the credential verification from frontend
    # In production, implement full server-side verification
    
    data = request.get_json()
    user_id = session.get('webauthn_user_id')
    
    if not user_id:
        return jsonify({'error': True, 'message': 'No pending authentication'}), 400
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 404
    
    # Create session
    session.clear()
    session['user_id'] = user.id
    session.permanent = True
    
    return jsonify({
        'data': user.to_dict(),
        'message': 'WebAuthn authentication successful'
    })
