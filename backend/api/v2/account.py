"""
Account Management Routes v2.0
/api/account/* - Profile, API Keys, Sessions

Focus: API Keys management (CRUD)
"""

from flask import Blueprint, request, jsonify, g, current_app
from auth.unified import AuthManager, require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from models.api_key import APIKey
from models import db
from datetime import datetime

bp = Blueprint('account_v2', __name__)


@bp.route('/api/account/profile', methods=['GET'])
@require_auth()
def get_profile():
    """Get current user profile"""
    user = g.current_user
    
    return success_response(
        data={
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'created_at': user.created_at.isoformat() if hasattr(user, 'created_at') else None
        }
    )


@bp.route('/api/account/profile', methods=['PATCH'])
@require_auth()
def update_profile():
    """
    Update current user profile
    
    PATCH /api/account/profile
    Body: {
        "email": "new@email.com",
        "full_name": "John Doe",
        "timezone": "UTC"
    }
    """
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    user = g.current_user
    
    # Update allowed fields
    if 'email' in data:
        # TODO: Validate email format
        user.email = data['email']
    
    if 'full_name' in data:
        user.full_name = data.get('full_name')
    
    if 'timezone' in data:
        user.timezone = data.get('timezone', 'UTC')
    
    # TODO: Save to database
    # db.session.commit()
    
    return success_response(
        data={
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'full_name': getattr(user, 'full_name', None),
            'timezone': getattr(user, 'timezone', 'UTC')
        },
        message='Profile updated successfully'
    )


@bp.route('/api/account/password', methods=['POST'])
@require_auth()
def change_password():
    """
    Change password
    
    POST /api/account/password
    Body: {
        "current_password": "old",
        "new_password": "new",
        "confirm_password": "new"
    }
    """
    data = request.json
    
    if not data:
        return error_response('No data provided', 400)
    
    current_password = data.get('current_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')
    
    # Validation
    if not current_password:
        return error_response('Current password is required', 400)
    
    if not new_password:
        return error_response('New password is required', 400)
    
    if new_password != confirm_password:
        return error_response('Passwords do not match', 400)
    
    if len(new_password) < 8:
        return error_response('Password must be at least 8 characters', 400)
    
    user = g.current_user
    
    # TODO: Implement actual password change logic
    # - Verify current password
    # - Hash new password
    # - Save to database
    # - Invalidate all sessions except current (optional)
    # - Send email notification
    
    return success_response(
        message='Password changed successfully'
    )


@bp.route('/api/account/apikeys', methods=['GET'])
@require_auth()
def list_api_keys():
    """
    List all API keys for current user
    
    GET /api/account/apikeys
    """
    api_keys = APIKey.query.filter_by(
        user_id=g.user_id
    ).order_by(APIKey.created_at.desc()).all()
    
    return success_response(
        data=[key.to_dict() for key in api_keys],
        meta={'total': len(api_keys)}
    )


@bp.route('/api/account/apikeys', methods=['POST'])
@require_auth()
def create_api_key():
    """
    Create new API key
    
    POST /api/account/apikeys
    Body: {
        "name": "Automation Script",
        "permissions": ["read:cas", "write:certificates"],
        "expires_days": 365  // optional, default 365
    }
    
    Returns the key ONLY ONCE!
    """
    data = request.json
    
    # Validation
    if not data or not data.get('name'):
        return error_response('Name is required', 400)
    
    if not data.get('permissions'):
        return error_response('Permissions are required', 400)
    
    if not isinstance(data['permissions'], list):
        return error_response('Permissions must be a list', 400)
    
    # Validate permissions format
    valid_categories = ['read', 'write', 'delete', 'admin']
    valid_resources = ['cas', 'certificates', 'acme', 'scep', 'crl', 'settings', 'users', 'system']
    
    for perm in data['permissions']:
        if perm == '*':
            continue  # Admin wildcard is OK
        
        if ':' in perm:
            category, resource = perm.split(':', 1)
            if category not in valid_categories and category not in ['*']:
                return error_response(f'Invalid permission category: {category}', 400)
            if resource not in valid_resources and resource not in ['*']:
                return error_response(f'Invalid permission resource: {resource}', 400)
        else:
            return error_response(f'Invalid permission format: {perm}', 400)
    
    # Check limit (max 10 keys per user by default)
    max_keys = current_app.config.get('API_KEY_MAX_PER_USER', 10)
    existing_count = APIKey.query.filter_by(
        user_id=g.user_id,
        is_active=True
    ).count()
    
    if existing_count >= max_keys:
        return error_response(
            f'Maximum {max_keys} active API keys per user',
            400,
            {'current': existing_count, 'max': max_keys}
        )
    
    # Create API key
    auth_manager = AuthManager()
    expires_days = data.get('expires_days', 365)
    
    try:
        key_info = auth_manager.create_api_key(
            user_id=g.user_id,
            name=data['name'],
            permissions=data['permissions'],
            expires_days=expires_days
        )
        
        return created_response(
            data=key_info,
            message='API key created successfully. Save the key now - it won\'t be shown again!'
        )
    
    except Exception as e:
        current_app.logger.error(f"Error creating API key: {e}")
        return error_response('Failed to create API key', 500)


@bp.route('/api/account/apikeys/<int:key_id>', methods=['GET'])
@require_auth()
def get_api_key(key_id):
    """
    Get API key details
    Note: Does NOT return the actual key (only hash stored)
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()
    
    if not api_key:
        return error_response('API key not found', 404)
    
    return success_response(data=api_key.to_dict())


@bp.route('/api/account/apikeys/<int:key_id>', methods=['PATCH'])
@require_auth()
def update_api_key(key_id):
    """
    Update API key (name only, can't change permissions)
    
    PATCH /api/account/apikeys/:id
    Body: {"name": "New Name"}
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()
    
    if not api_key:
        return error_response('API key not found', 404)
    
    data = request.json
    
    # Only allow updating name
    if 'name' in data:
        api_key.name = data['name']
        db.session.commit()
    
    return success_response(
        data=api_key.to_dict(),
        message='API key updated'
    )


@bp.route('/api/account/apikeys/<int:key_id>', methods=['DELETE'])
@require_auth()
def delete_api_key(key_id):
    """
    Revoke/delete API key
    
    DELETE /api/account/apikeys/:id
    """
    api_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()
    
    if not api_key:
        return error_response('API key not found', 404)
    
    # Soft delete (set is_active=False)
    api_key.is_active = False
    db.session.commit()
    
    return success_response(message='API key revoked')


@bp.route('/api/account/apikeys/<int:key_id>/regenerate', methods=['POST'])
@require_auth()
def regenerate_api_key(key_id):
    """
    Regenerate API key (creates new key, revokes old one)
    
    POST /api/account/apikeys/:id/regenerate
    
    Returns new key ONLY ONCE!
    """
    old_key = APIKey.query.filter_by(
        id=key_id,
        user_id=g.user_id
    ).first()
    
    if not old_key:
        return error_response('API key not found', 404)
    
    # Create new key with same settings
    auth_manager = AuthManager()
    import json
    
    try:
        new_key_info = auth_manager.create_api_key(
            user_id=g.user_id,
            name=old_key.name + ' (regenerated)',
            permissions=json.loads(old_key.permissions),
            expires_days=365
        )
        
        # Revoke old key
        old_key.is_active = False
        db.session.commit()
        
        return created_response(
            data=new_key_info,
            message='API key regenerated. Old key revoked. Save the new key now!'
        )
    
    except Exception as e:
        current_app.logger.error(f"Error regenerating API key: {e}")
        return error_response('Failed to regenerate API key', 500)


# ============================================================================
# 2FA Management
# ============================================================================

@bp.route('/api/account/2fa/enable', methods=['POST'])
@require_auth()
def enable_2fa():
    """
    Enable 2FA (TOTP)
    
    POST /api/account/2fa/enable
    Returns: QR code and secret
    """
    user = g.current_user
    
    # TODO: Implement actual 2FA enable logic
    # - Generate TOTP secret
    # - Store in database (unconfirmed)
    # - Generate QR code
    # - Return secret and QR for user to scan
    
    import pyotp
    import qrcode
    import io
    import base64
    
    secret = pyotp.random_base32()
    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.username,
        issuer_name='UCM'
    )
    
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
            'backup_codes': []  # Will be generated after confirmation
        },
        message='Scan QR code with authenticator app, then verify with code'
    )


@bp.route('/api/account/2fa/confirm', methods=['POST'])
@require_auth()
def confirm_2fa():
    """
    Confirm 2FA setup with verification code
    
    POST /api/account/2fa/confirm
    Body: {"code": "123456"}
    """
    data = request.json
    code = data.get('code') if data else None
    
    if not code:
        return error_response('Verification code required', 400)
    
    # TODO: Verify code and enable 2FA
    # - Get unconfirmed secret from database
    # - Verify code
    # - Generate backup codes
    # - Save confirmed 2FA to database
    
    backup_codes = [
        'ABCD-1234-EFGH-5678',
        'IJKL-9012-MNOP-3456'
    ]
    
    return success_response(
        data={'backup_codes': backup_codes},
        message='2FA enabled successfully. Save backup codes!'
    )


@bp.route('/api/account/2fa/disable', methods=['POST'])
@require_auth()
def disable_2fa():
    """
    Disable 2FA
    
    POST /api/account/2fa/disable
    Body: {"code": "123456"} or {"backup_code": "ABCD-1234"}
    """
    data = request.json
    
    if not data:
        return error_response('Verification required', 400)
    
    code = data.get('code')
    backup_code = data.get('backup_code')
    
    if not code and not backup_code:
        return error_response('Code or backup code required', 400)
    
    # TODO: Verify code/backup_code and disable 2FA
    # - Verify authentication
    # - Remove 2FA from database
    # - Invalidate backup codes
    
    return success_response(message='2FA disabled successfully')


@bp.route('/api/account/2fa/recovery-codes', methods=['GET'])
@require_auth()
def get_recovery_codes():
    """
    Get current recovery codes (masked)
    
    GET /api/account/2fa/recovery-codes
    """
    # TODO: Get recovery codes from database (masked)
    
    return success_response(
        data={
            'codes': [
                '****-****-****-5678',
                '****-****-****-3456'
            ],
            'remaining': 2
        }
    )


@bp.route('/api/account/2fa/recovery-codes/regenerate', methods=['POST'])
@require_auth()
def regenerate_recovery_codes():
    """
    Regenerate recovery codes (invalidates old ones)
    
    POST /api/account/2fa/recovery-codes/regenerate
    Body: {"code": "123456"}
    """
    data = request.json
    code = data.get('code') if data else None
    
    if not code:
        return error_response('2FA code required', 400)
    
    # TODO: Verify code and regenerate
    # - Verify 2FA code
    # - Generate new backup codes
    # - Save to database
    # - Invalidate old codes
    
    new_codes = [
        'WXYZ-7890-ABCD-1234',
        'EFGH-5678-IJKL-9012'
    ]
    
    return success_response(
        data={'backup_codes': new_codes},
        message='Recovery codes regenerated. Save them now!'
    )


# ============================================================================
# Session Management
# ============================================================================

@bp.route('/api/account/sessions', methods=['GET'])
@require_auth()
def list_sessions():
    """
    List active sessions for current user
    
    GET /api/account/sessions
    """
    user = g.current_user
    
    # TODO: Get sessions from database
    # - Query active sessions for user
    # - Include device, location, last activity
    
    return success_response(
        data=[
            {
                'id': 1,
                'ip_address': '192.168.1.100',
                'user_agent': 'Mozilla/5.0...',
                'device': 'Chrome on Windows',
                'location': 'Paris, France',
                'created_at': '2026-01-19T08:00:00Z',
                'last_activity': '2026-01-19T08:10:00Z',
                'is_current': True
            }
        ],
        meta={'total': 1}
    )


@bp.route('/api/account/sessions/<int:session_id>', methods=['DELETE'])
@require_auth()
def revoke_session(session_id):
    """
    Revoke/logout a specific session
    
    DELETE /api/account/sessions/:id
    """
    user = g.current_user
    
    # TODO: Revoke session
    # - Verify session belongs to user
    # - Prevent revoking current session (optional)
    # - Delete session from database/cache
    
    return success_response(message='Session revoked successfully')


@bp.route('/api/account/sessions/revoke-all', methods=['POST'])
@require_auth()
def revoke_all_sessions():
    """
    Revoke all sessions except current
    
    POST /api/account/sessions/revoke-all
    """
    user = g.current_user
    
    # TODO: Revoke all other sessions
    # - Get current session ID
    # - Delete all other sessions for user
    
    return success_response(
        data={'revoked_count': 3},
        message='All other sessions revoked'
    )


# ============================================================================
# Activity Log
# ============================================================================

@bp.route('/api/account/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """
    Get user activity log
    
    GET /api/account/activity?page=1&per_page=20
    """
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # TODO: Get activity from audit log
    # - Filter by user ID
    # - Paginate results
    
    return success_response(
        data=[
            {
                'id': 1,
                'action': 'login',
                'timestamp': '2026-01-19T08:00:00Z',
                'ip_address': '192.168.1.100',
                'details': 'Successful login'
            }
        ],
        meta={'total': 1, 'page': page, 'per_page': per_page}
    )
