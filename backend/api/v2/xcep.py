"""
MS-XCEP Management Routes v2.0
/api/v2/xcep/* - XCEP (Certificate Enrollment Policy) configuration
"""

from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SystemConfig, CA
from services.audit_service import AuditService
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('xcep_v2', __name__)


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


@bp.route('/api/v2/xcep/config', methods=['GET'])
@require_auth(['read:xcep'])
def get_xcep_config():
    """Get XCEP configuration from database"""
    ca_refid = get_config('xcep_ca_refid', '')
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    return success_response(data={
        'enabled': get_config('xcep_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'username': get_config('xcep_username', ''),
        'password_set': bool(get_config('xcep_password', '')),
    })


@bp.route('/api/v2/xcep/config', methods=['PATCH'])
@require_auth(['write:xcep'])
def update_xcep_config():
    """Update XCEP configuration in database"""
    data = request.json or {}

    if 'enabled' in data:
        set_config('xcep_enabled', 'true' if data['enabled'] else 'false')
    if 'ca_refid' in data:
        if data['ca_refid']:
            if not CA.query.filter_by(refid=data['ca_refid']).first():
                return error_response('CA not found', 404)
        set_config('xcep_ca_refid', data['ca_refid'] or '')
    if 'ca_id' in data:
        if data['ca_id']:
            ca = db.session.get(CA, data['ca_id'])
            if not ca:
                return error_response('CA not found', 404)
            set_config('xcep_ca_refid', ca.refid)
        else:
            set_config('xcep_ca_refid', '')
    if 'username' in data:
        set_config('xcep_username', data['username'])
    if 'password' in data and data['password']:
        from werkzeug.security import generate_password_hash
        set_config('xcep_password', generate_password_hash(data['password']))

    ok, _err = safe_commit(logger, "Failed to update XCEP configuration")
    if not ok:
        return _err

    AuditService.log_action(
        action='xcep_config_update',
        resource_type='xcep',
        resource_name='XCEP Configuration',
        details='Updated XCEP configuration',
        success=True
    )

    return success_response(message='XCEP configuration saved')
