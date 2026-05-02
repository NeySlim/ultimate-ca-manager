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

    # NOTE: whether to skip current_password verification is decided ENTIRELY
    # server-side from User.force_password_change. The client must NOT be able
    # to influence this — a stolen session on a non-force-change user could
    # otherwise rotate the password without knowing the current one.
    user = User.query.get(g.current_user.id)
    if not user:
        return error_response('User not found', 404)

    skip_current_check = bool(user.force_password_change)

    # Validation
    if not skip_current_check and not current_password:
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

    # Skip current-password verification only when the SERVER says so
    if not skip_current_check:
        if not current_password or not check_password_hash(user.password_hash, current_password):
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
