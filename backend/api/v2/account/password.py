import re
import logging

from flask import request, g
from models import db, User
from werkzeug.security import check_password_hash, generate_password_hash
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from auth.unified import require_auth

from . import bp

logger = logging.getLogger(__name__)


@bp.route('/api/v2/account/password', methods=['POST'])
@require_auth()
def change_password():
    """Change password"""
    data = request.json

    if not data:
        return error_response('No data provided', 400)

    current_password = data.get('current_password')
    new_password = data.get('new_password')
    force_change = data.get('force_change', False)

    # Validation
    if not force_change and not current_password:
        return error_response('Current password is required', 400)

    if not new_password:
        return error_response('New password is required', 400)

    if len(new_password) < 8:
        return error_response('Password must be at least 8 characters', 400)

    # Password complexity check
    if not re.search(r'[A-Z]', new_password):
        return error_response('Password must contain at least one uppercase letter', 400)
    if not re.search(r'[a-z]', new_password):
        return error_response('Password must contain at least one lowercase letter', 400)
    if not re.search(r'[0-9]', new_password):
        return error_response('Password must contain at least one digit', 400)
    if not re.search(r'[!@#$%^&*()_+\-=\[\]{}|;:,.<>?/~`]', new_password):
        return error_response('Password must contain at least one special character', 400)

    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    # Skip current password check only if force_password_change is set
    if force_change and user.force_password_change:
        pass
    elif not current_password or not check_password_hash(user.password_hash, current_password):
        return error_response('Current password is incorrect', 401)

    # Update password
    user.password_hash = generate_password_hash(new_password)
    user.force_password_change = False
    ok, _err = safe_commit(logger, "Failed to update password")
    if not ok:
        return _err

    # Audit log
    AuditService.log_action(
        action='password_change',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Password changed by user: {user.username}',
        success=True
    )

    return success_response(message='Password changed successfully')
