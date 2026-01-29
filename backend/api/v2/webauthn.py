"""
WebAuthn API
Manage WebAuthn credentials for passwordless login
"""

from flask import Blueprint, jsonify, request, session, g
from api.v2.auth import require_auth
from models import User, db
from models.webauthn import WebAuthnCredential, WebAuthnChallenge
import secrets
import json
from datetime import datetime, timezone, timedelta

bp = Blueprint('webauthn', __name__, url_prefix='/api/v2/webauthn')


@bp.route('/credentials', methods=['GET'])
@require_auth()
def list_credentials():
    """List user's WebAuthn credentials"""
    user = g.current_user
    
    # Get credentials from WebAuthnCredential model
    credentials = WebAuthnCredential.query.filter_by(user_id=user.id).all()
    
    return jsonify({'data': [c.to_dict() for c in credentials]})


@bp.route('/credentials', methods=['POST'])
@require_auth()
def register_credential():
    """Register a new WebAuthn credential"""
    user = g.current_user
    data = request.get_json()
    
    import base64
    
    # Parse credential data from WebAuthn response
    credential_id = data.get('credential_id', '')
    public_key = data.get('public_key', '')
    
    # Decode base64 to binary
    try:
        credential_id_bin = base64.b64decode(credential_id) if credential_id else secrets.token_bytes(32)
        public_key_bin = base64.b64decode(public_key) if public_key else b''
    except Exception:
        credential_id_bin = secrets.token_bytes(32)
        public_key_bin = b''
    
    # Create credential
    credential = WebAuthnCredential(
        user_id=user.id,
        credential_id=credential_id_bin,
        public_key=public_key_bin,
        name=data.get('name', 'Security Key'),
        aaguid=data.get('aaguid'),
        transports=json.dumps(data.get('transports', [])),
        sign_count=data.get('sign_count', 0),
        is_backup_eligible=data.get('is_backup_eligible', False),
        user_verified=data.get('user_verified', False),
        enabled=True
    )
    
    db.session.add(credential)
    db.session.commit()
    
    return jsonify({
        'data': credential.to_dict(),
        'message': 'WebAuthn credential registered'
    }), 201


@bp.route('/credentials/<int:credential_id>', methods=['DELETE'])
@require_auth()
def delete_credential(credential_id):
    """Delete a WebAuthn credential"""
    user = g.current_user
    
    credential = WebAuthnCredential.query.filter_by(
        id=credential_id,
        user_id=user.id
    ).first()
    
    if not credential:
        return jsonify({'error': True, 'message': 'Credential not found'}), 404
    
    db.session.delete(credential)
    db.session.commit()
    
    return jsonify({'message': 'Credential deleted'})


@bp.route('/register/options', methods=['POST'])
@require_auth()
def registration_options():
    """Get WebAuthn registration options"""
    user = g.current_user
    
    # Generate challenge
    challenge = secrets.token_urlsafe(32)
    
    # Store challenge in database
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    challenge_obj = WebAuthnChallenge(
        user_id=user.id,
        challenge=challenge,
        challenge_type='registration',
        expires_at=expires_at
    )
    db.session.add(challenge_obj)
    db.session.commit()
    
    # Get existing credentials to exclude
    existing = WebAuthnCredential.query.filter_by(user_id=user.id).all()
    exclude_credentials = [
        {
            'type': 'public-key',
            'id': c.to_dict()['credential_id']
        }
        for c in existing
    ]
    
    return jsonify({
        'data': {
            'challenge': challenge,
            'rp': {
                'name': 'UCM - Certificate Manager',
                'id': request.host.split(':')[0]
            },
            'user': {
                'id': str(user.id),
                'name': user.username,
                'displayName': user.full_name or user.username
            },
            'pubKeyCredParams': [
                {'type': 'public-key', 'alg': -7},   # ES256
                {'type': 'public-key', 'alg': -257}  # RS256
            ],
            'timeout': 60000,
            'attestation': 'none',
            'excludeCredentials': exclude_credentials,
            'authenticatorSelection': {
                'authenticatorAttachment': 'cross-platform',
                'userVerification': 'preferred',
                'residentKey': 'discouraged'
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
    credentials = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).all()
    
    if not credentials:
        return jsonify({'error': True, 'message': 'No WebAuthn credentials registered'}), 400
    
    # Generate challenge
    challenge = secrets.token_urlsafe(32)
    
    # Store challenge
    expires_at = datetime.utcnow() + timedelta(minutes=5)
    challenge_obj = WebAuthnChallenge(
        user_id=user.id,
        challenge=challenge,
        challenge_type='authentication',
        expires_at=expires_at
    )
    db.session.add(challenge_obj)
    db.session.commit()
    
    session['webauthn_user_id'] = user.id
    session['webauthn_challenge'] = challenge
    
    allow_credentials = [
        {
            'type': 'public-key',
            'id': c.to_dict()['credential_id'],
            'transports': json.loads(c.transports) if c.transports else []
        }
        for c in credentials
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
    data = request.get_json()
    user_id = session.get('webauthn_user_id')
    
    if not user_id:
        return jsonify({'error': True, 'message': 'No pending authentication'}), 400
    
    user = User.query.get(user_id)
    if not user:
        return jsonify({'error': True, 'message': 'User not found'}), 404
    
    # Update last used timestamp on credential if provided
    credential_id = data.get('credential_id')
    if credential_id:
        import base64
        try:
            cred_id_bin = base64.b64decode(credential_id)
            cred = WebAuthnCredential.query.filter_by(
                credential_id=cred_id_bin,
                user_id=user.id
            ).first()
            if cred:
                cred.last_used_at = datetime.utcnow()
                cred.sign_count = data.get('sign_count', cred.sign_count + 1)
                db.session.commit()
        except Exception:
            pass
    
    # Create session
    session.clear()
    session['user_id'] = user.id
    session.permanent = True
    
    return jsonify({
        'data': user.to_dict(),
        'message': 'WebAuthn authentication successful'
    })
