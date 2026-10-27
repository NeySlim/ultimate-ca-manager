"""
Users API Key Management Routes (Admin)
"""
import logging

from models import db, User
from models.api_key import APIKey
from auth.unified import refuse_api_key_on_own_account, require_auth
from flask import g
from services.api_key_revocation import revoke_or_delete
from utils.response import success_response, error_response

from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/users/<int:user_id>/apikeys', methods=['GET'])
@require_auth(['write:users'])
def list_user_api_keys(user_id):
    """
    List another user's API keys. The secret is never returned.

    GET /api/v2/users/{user_id}/apikeys
    """
    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)
    keys = APIKey.query.filter_by(user_id=user.id).order_by(APIKey.created_at.desc()).all()
    return success_response(data=[key.to_dict() for key in keys], meta={'total': len(keys)})


@bp.route('/api/v2/users/<int:user_id>/apikeys/<int:key_id>', methods=['DELETE'])
@require_auth(['write:users'])
def delete_user_api_key(user_id, key_id):
    """
    Revoke another user's API key; a revoked or expired one is deleted.

    DELETE /api/v2/users/{user_id}/apikeys/{key_id}
    """
    refused = refuse_api_key_on_own_account(user_id)
    if refused:
        return refused
    user = db.session.get(User, user_id)
    if not user:
        return error_response('User not found', 404)
    api_key = APIKey.query.filter_by(id=key_id, user_id=user.id).first()
    if not api_key:
        return error_response('API key not found', 404)

    owner, actor = user.username, g.current_user.username
    verb, err = revoke_or_delete(
        api_key, 'apikey_admin',
        lambda verb, name: f'{verb} API key "{name}" (id {key_id}) of {owner} by {actor}')
    if err:
        return err
    return success_response(message=f'API key {verb}')
