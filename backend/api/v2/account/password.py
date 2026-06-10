import json
import logging

from flask import request, g
from models import db, User
from werkzeug.security import check_password_hash, generate_password_hash
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from auth.unified import require_auth
from security.password_policy import validate_password, is_admin_bypass_enabled

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

    # Admin bypass: admin can skip policy validation if enabled
    is_admin = user.role == 'admin'
    if not (is_admin and is_admin_bypass_enabled()):
        is_valid, errors = validate_password(new_password)
        if not is_valid:
            first = errors[0]
            return error_response(first.get('message', 'Invalid password'), 400,
                                  details={'i18n_key': first.get('key'), 'i18n_values': first.get('values', {})})

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

    # SECURITY: Invalidate all active sessions after password change
    # This forces re-authentication across all devices/browsers
    from models.user import UserSession
    sessions_deleted = UserSession.query.filter_by(user_id=user.id).delete()
    if sessions_deleted > 0:
        ok, _err = safe_commit(logger, "Failed to invalidate user sessions after password change")
        if not ok:
            logger.warning(f"Failed to delete {sessions_deleted} sessions for user {user.username}")
        else:
            logger.info(f"Invalidated {sessions_deleted} sessions for user {user.username} after password change")

    # Audit log
    AuditService.log_action(
        action='password_change',
        resource_type='user',
        resource_id=str(user.id),
        resource_name=user.username,
        details=f'Password changed by user: {user.username} ({sessions_deleted} sessions invalidated)',
        success=True
    )

    return success_response(message='Password changed successfully')
