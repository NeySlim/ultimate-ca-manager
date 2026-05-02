import logging

from flask import request, g
from models import db, UserSession, AuditLog
from services.audit_service import AuditService
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from utils.datetime_utils import utc_isoformat
from auth.unified import require_auth

from . import bp

logger = logging.getLogger(__name__)


# ============================================================================
# Session Management
# ============================================================================

@bp.route('/api/v2/account/sessions', methods=['GET'])
@require_auth()
def list_sessions():
    """List active sessions for current user"""
    sessions = UserSession.query.filter_by(user_id=g.current_user.id).all()

    # Get current session ID from cookie/token
    current_session_id = request.cookies.get('session_id')

    return success_response(
        data=[{
            'id': s.id,
            'ip_address': s.ip_address,
            'user_agent': s.user_agent,
            'created_at': utc_isoformat(s.created_at),
            'last_activity': utc_isoformat(s.last_activity),
            'is_current': str(s.id) == current_session_id
        } for s in sessions],
        meta={'total': len(sessions)}
    )


@bp.route('/api/v2/account/sessions/<int:session_id>', methods=['DELETE'])
@require_auth()
def revoke_session(session_id):
    """Revoke a specific session"""
    session = UserSession.query.filter_by(id=session_id, user_id=g.current_user.id).first()
    if not session:
        return error_response('Session not found', 404)

    db.session.delete(session)
    ok, _err = safe_commit(logger, "Failed to revoke session")
    if not ok:
        return _err

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
    current_session_id = request.cookies.get('session_id')

    # Delete all sessions except current
    UserSession.query.filter(
        UserSession.user_id == g.current_user.id,
        UserSession.id != current_session_id
    ).delete(synchronize_session=False)

    ok, _err = safe_commit(logger, "Failed to revoke other sessions")
    if not ok:
        return _err

    return success_response(message='All other sessions revoked')


# ============================================================================
# Activity Log
# ============================================================================

@bp.route('/api/v2/account/activity', methods=['GET'])
@require_auth()
def get_activity_log():
    """Get user activity log"""
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
