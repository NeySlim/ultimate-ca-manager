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
from services.audit_service import AuditService
from datetime import datetime

bp = Blueprint('account_v2', __name__)


@bp.route('/api/v2/account/profile', methods=['GET'])
@require_auth()
def get_profile():
    """Get current user profile with full details"""
    from models import User
    
    # Get fresh user data from DB
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)
    
    return success_response(
        data={
            'id': user.id,
            'username': user.username,
            'email': getattr(user, 'email', None),
            'full_name': getattr(user, 'full_name', None),
            'role': user.role,
            'active': getattr(user, 'active', True),
            'created_at': user.created_at.isoformat() if hasattr(user, 'created_at') and user.created_at else None,
            'last_login': user.last_login.isoformat() if hasattr(user, 'last_login') and user.last_login else None,
            'login_count': getattr(user, 'login_count', 0),
            'two_factor_enabled': getattr(user, 'two_factor_enabled', False),
            'password_changed_at': user.password_changed_at.isoformat() if hasattr(user, 'password_changed_at') and user.password_changed_at else None,
        }
    )


@bp.route('/api/v2/account/profile', methods=['PATCH'])
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


@bp.route('/api/v2/account/password', methods=['POST'])
@require_auth()
def change_password():
    """Change password"""
    from models import User, db
    from werkzeug.security import check_password_hash, generate_password_hash
    
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
    
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)
    
    # Verify current password
    if not check_password_hash(user.password_hash, current_password):
        return error_response('Current password is incorrect', 401)
    
    # Update password
    user.password_hash = generate_password_hash(new_password)
    db.session.commit()
    
    # Audit log
    AuditService.log_action(
        action='password_change',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Password changed by user: {user.username}',
        success=True
    )
    
    return success_response(
        message='Password changed successfully'
    )


@bp.route('/api/v2/account/apikeys', methods=['GET'])
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


@bp.route('/api/v2/account/apikeys', methods=['POST'])
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
        
        AuditService.log_action(
            action='apikey_create',
            resource_type='api_key',
            resource_name=data['name'],
            details=f'Created API key: {data["name"]}',
            success=True
        )
        
        return created_response(
            data=key_info,
            message='API key created successfully. Save the key now - it won\'t be shown again!'
        )
    
    except Exception as e:
        current_app.logger.error(f"Error creating API key: {e}")
        return error_response('Failed to create API key', 500)


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['GET'])
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


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['PATCH'])
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


@bp.route('/api/v2/account/apikeys/<int:key_id>', methods=['DELETE'])
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
    key_name = api_key.name
    db.session.commit()
    
    AuditService.log_action(
        action='apikey_delete',
        resource_type='api_key',
        resource_id=str(key_id),
        resource_name=key_name,
        details=f'Revoked API key: {key_name}',
        success=True
    )
    
    return success_response(message='API key revoked')


@bp.route('/api/v2/account/apikeys/<int:key_id>/regenerate', methods=['POST'])
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
        
        AuditService.log_action(
            action='apikey_regenerate',
            resource_type='api_key',
            resource_id=str(key_id),
            resource_name=old_key.name,
            details=f'Regenerated API key: {old_key.name}',
            success=True
        )
        
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

@bp.route('/api/v2/account/2fa/enable', methods=['POST'])
@require_auth()
def enable_2fa():
    """Enable 2FA (TOTP) - generates QR code and secret"""
    from models import User, db
    import pyotp
    import qrcode
    import io
    import base64
    
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
    db.session.commit()
    
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
    from models import User, db
    import pyotp
    import secrets
    
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
    
    # Enable 2FA
    user.two_factor_enabled = True
    user.backup_codes = ','.join(backup_codes)
    db.session.commit()
    
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
    from models import User, db
    import pyotp
    
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
        stored_codes = (user.backup_codes or '').split(',')
        if backup_code not in stored_codes:
            return error_response('Invalid backup code', 400)
    
    # Disable 2FA
    user.two_factor_enabled = False
    user.totp_secret = None
    user.backup_codes = None
    db.session.commit()
    
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
    from models import User
    
    user = User.query.get(g.current_user.id)
    if not user or not user.two_factor_enabled:
        return error_response('2FA not enabled', 400)
    
    stored_codes = (user.backup_codes or '').split(',')
    masked_codes = [f'{c[:4]}...{c[-4:]}' if len(c) > 8 else '****' for c in stored_codes if c]
    
    return success_response(
        data={
            'codes': masked_codes,
            'count': len([c for c in stored_codes if c])
        }
    )


@bp.route('/api/v2/account/2fa/recovery-codes/regenerate', methods=['POST'])
@require_auth()
def regenerate_recovery_codes():
    """Regenerate recovery codes (invalidates old ones)"""
    from models import User, db
    import pyotp
    import secrets
    
    data = request.json
    code = data.get('code') if data else None
    
    if not code:
        return error_response('2FA code required', 400)
    
    user = User.query.get(g.current_user.id)
    if not user or not user.two_factor_enabled:
        return error_response('2FA not enabled', 400)
    
    # Verify code
    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(code):
        return error_response('Invalid verification code', 400)
    
    # Generate new backup codes
    new_codes = [f'{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}' for _ in range(8)]
    
    user.backup_codes = ','.join(new_codes)
    db.session.commit()
    
    return success_response(
        data={'backup_codes': new_codes},
        message='Recovery codes regenerated. Save them now!'
    )


# ============================================================================
# Session Management
# ============================================================================

@bp.route('/api/v2/account/sessions', methods=['GET'])
@require_auth()
def list_sessions():
    """List active sessions for current user"""
    from models import UserSession
    
    sessions = UserSession.query.filter_by(user_id=g.current_user.id).all()
    
    # Get current session ID from cookie/token
    current_session_id = request.cookies.get('session_id')
    
    return success_response(
        data=[{
            'id': s.id,
            'ip_address': s.ip_address,
            'user_agent': s.user_agent,
            'created_at': s.created_at.isoformat() if s.created_at else None,
            'last_activity': s.last_activity.isoformat() if s.last_activity else None,
            'is_current': str(s.id) == current_session_id
        } for s in sessions],
        meta={'total': len(sessions)}
    )


@bp.route('/api/v2/account/sessions/<int:session_id>', methods=['DELETE'])
@require_auth()
def revoke_session(session_id):
    """Revoke a specific session"""
    from models import UserSession, db
    
    session = UserSession.query.filter_by(id=session_id, user_id=g.current_user.id).first()
    if not session:
        return error_response('Session not found', 404)
    
    db.session.delete(session)
    db.session.commit()
    
    AuditService.log_action(
        action='session_revoke',
        resource_type='session',
        resource_id=str(session_id),
        resource_name=f'Session {session_id}',
        details=f'Revoked session {session_id}',
        success=True
    )
    
    return success_response(message='Session revoked successfully')


@bp.route('/api/v2/account/sessions/revoke-all', methods=['POST'])
@require_auth()
def revoke_all_sessions():
    """Revoke all sessions except current"""
    from models import UserSession, db
    
    current_session_id = request.cookies.get('session_id')
    
    # Delete all sessions except current
    UserSession.query.filter(
        UserSession.user_id == g.current_user.id,
        UserSession.id != current_session_id
    ).delete(synchronize_session=False)
    
    db.session.commit()
    
    return success_response(message='All other sessions revoked')


# ============================================================================
# Activity Log
# ============================================================================

@bp.route('/api/v2/account/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """Get user activity log"""
    from models import AuditLog
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    # Filter by username (AuditLog doesn't have user_id, uses username)
    query = AuditLog.query.filter_by(username=g.current_user.username)
    query = query.order_by(AuditLog.timestamp.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return success_response(
        data=[log.to_dict() for log in pagination.items],
        meta={'total': pagination.total, 'page': page, 'per_page': per_page}
    )
