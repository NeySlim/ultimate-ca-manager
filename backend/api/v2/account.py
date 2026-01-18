"""
Account Management Routes v2.0
/api/account/* - Profile, API Keys, Sessions

Focus: API Keys management (CRUD)
"""

from flask import Blueprint, request, jsonify, g
from backend.auth.unified import AuthManager, require_auth
from backend.utils.response import success_response, error_response, created_response, no_content_response
from backend.models.api_key import APIKey
from backend.extensions import db
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
