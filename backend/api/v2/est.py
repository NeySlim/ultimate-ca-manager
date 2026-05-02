"""
EST Management Routes v2.0
/api/v2/est/* - EST configuration and statistics
"""

from flask import Blueprint, request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SystemConfig, CA, AuditLog
from services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('est_v2', __name__)


def get_config(key, default=None):
    """Get config value from database"""
    config = SystemConfig.query.filter_by(key=key).first()
    return config.value if config else default


def set_config(key, value):
    """Set config value in database"""
    config = SystemConfig.query.filter_by(key=key).first()
    if config:
        config.value = str(value) if value is not None else None
    else:
        config = SystemConfig(key=key, value=str(value) if value is not None else None)
        db.session.add(config)


@bp.route('/api/v2/est/config', methods=['GET'])
@require_auth(['read:est'])
def get_est_config():
    """Get EST configuration from database"""
    ca_refid = get_config('est_ca_refid', '')
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    return success_response(data={
        'enabled': get_config('est_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'username': get_config('est_username', ''),
        'password_set': bool(get_config('est_password', '')),
        'validity_days': int(get_config('est_validity_days', '365') or 365),
    })


@bp.route('/api/v2/est/config', methods=['PATCH'])
@require_auth(['write:est'])
def update_est_config():
    """Update EST configuration in database"""
    data = request.json or {}

    if 'enabled' in data:
        set_config('est_enabled', 'true' if data['enabled'] else 'false')
    if 'ca_refid' in data:
        set_config('est_ca_refid', data['ca_refid'] or '')
    if 'ca_id' in data:
        # Look up refid from CA id
        ca = CA.query.get(data['ca_id']) if data['ca_id'] else None
        set_config('est_ca_refid', ca.refid if ca else '')
    if 'username' in data:
        set_config('est_username', data['username'])
    if 'password' in data and data['password']:
        from werkzeug.security import generate_password_hash
        set_config('est_password', generate_password_hash(data['password']))
    if 'validity_days' in data:
        set_config('est_validity_days', str(data['validity_days']))

    ok, _err = safe_commit(logger, "Failed to update EST configuration")
    if not ok:
        return _err

    AuditService.log_action(
        action='est_config_update',
        resource_type='est',
        resource_name='EST Configuration',
        details='Updated EST configuration',
        success=True
    )

    return success_response(message='EST configuration saved')


@bp.route('/api/v2/est/stats', methods=['GET'])
@require_auth(['read:est'])
def get_est_stats():
    """Get EST enrollment statistics from audit logs"""
    try:
        total = AuditLog.query.filter(
            AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')
        ).count()
        successful = AuditLog.query.filter(
            (AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')),
            AuditLog.success == True
        ).count()
        failed = AuditLog.query.filter(
            (AuditLog.action.like('est.%') | AuditLog.details.like('%EST enrollment%')),
            AuditLog.success == False
        ).count()

        # Also count certificate.issued with EST details
        est_issued = AuditLog.query.filter(
            AuditLog.action == 'certificate.issued',
            AuditLog.details.like('%EST%')
        ).count()

        return success_response(data={
            'total': total + est_issued,
            'successful': successful + est_issued,
            'failed': failed,
        })
    except Exception as e:
        logger.error(f"Failed to get EST stats: {e}")
        return success_response(data={
            'total': 0,
            'successful': 0,
            'failed': 0,
        })
