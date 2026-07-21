"""
TSA Management Routes v2.0
/api/v2/tsa/* - TSA configuration and statistics
"""

from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import db, SystemConfig, CA, AuditLog
from services.audit_service import AuditService
import logging
import re

logger = logging.getLogger(__name__)

bp = Blueprint('tsa_v2', __name__)

_POLICY_OID_RE = re.compile(r'^[0-2](?:\.(?:0|[1-9]\d*)){1,}$')
_MAX_POLICY_OID_LENGTH = 255


def normalize_policy_oid(value):
    """Return a canonical policy OID string, or None when malformed."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if len(candidate) > _MAX_POLICY_OID_LENGTH or not _POLICY_OID_RE.fullmatch(candidate):
        return None
    first, second = (int(arc) for arc in candidate.split('.', 2)[:2])
    if first < 2 and second > 39:
        return None
    return candidate


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


@bp.route('/api/v2/tsa/config', methods=['GET'])
@require_auth(['read:settings'])
def get_tsa_config():
    """Get TSA configuration from database"""
    ca_refid = get_config('tsa_ca_refid', '')
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    return success_response(data={
        'enabled': get_config('tsa_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'policy_oid': get_config('tsa_policy_oid', '1.2.3.4.1'),
    })


@bp.route('/api/v2/tsa/config', methods=['PATCH'])
@require_auth(['write:settings'])
def update_tsa_config():
    """Update TSA configuration in database"""
    data = request.json or {}

    policy_oid = None
    if 'policy_oid' in data:
        policy_oid = normalize_policy_oid(data['policy_oid'])
        if policy_oid is None:
            return error_response('policy_oid must be a valid OID', 400)

    if 'enabled' in data:
        set_config('tsa_enabled', 'true' if data['enabled'] else 'false')
    if 'ca_refid' in data:
        set_config('tsa_ca_refid', data['ca_refid'] or '')
    if 'ca_id' in data:
        ca = db.session.get(CA, data['ca_id']) if data['ca_id'] else None
        set_config('tsa_ca_refid', ca.refid if ca else '')
    if policy_oid is not None:
        set_config('tsa_policy_oid', policy_oid)

    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update TSA config: {e}")
        return error_response('Failed to update TSA configuration', 500)

    AuditService.log_action(
        action='tsa_config_update',
        resource_type='tsa',
        resource_name='TSA Configuration',
        details='Updated TSA configuration',
        success=True
    )

    return success_response(message='TSA configuration saved')


@bp.route('/api/v2/tsa/stats', methods=['GET'])
@require_auth(['read:settings'])
def get_tsa_stats():
    """Get TSA statistics from audit logs"""
    try:
        total = AuditLog.query.filter(
            AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')
        ).count()
        successful = AuditLog.query.filter(
            (AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')),
            AuditLog.success == True
        ).count()
        failed = AuditLog.query.filter(
            (AuditLog.action.like('tsa.%') | AuditLog.details.like('%TSA%timestamp%')),
            AuditLog.success == False
        ).count()

        return success_response(data={
            'total': total,
            'successful': successful,
            'failed': failed,
        })
    except Exception as e:
        logger.error(f"Failed to get TSA stats: {e}")
        return success_response(data={
            'total': 0,
            'successful': 0,
            'failed': 0,
        })
