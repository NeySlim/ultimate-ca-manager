"""
MS-XCEP Management Routes v2.0
/api/v2/xcep/* - XCEP (Certificate Enrollment Policy) configuration
"""

from utils.signing_ca import xcep_ca_problem
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SystemConfig, CA
from services.audit_service import AuditService
from services import windows_profiles
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


def _actor():
    from flask import g
    return getattr(getattr(g, 'current_user', None), 'username', None)


@bp.route('/api/v2/xcep/config', methods=['GET'])
@require_auth(['read:xcep'])
def get_xcep_config():
    """XCEP configuration: the switch, and the default profile's policy CA and account"""
    profile = windows_profiles.default_profile()
    ca_refid = (profile.policy_ca_refid if profile is not None else None) or ''
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
        'username': (profile.xcep_username if profile is not None else None) or '',
        'password_set': bool(profile is not None and profile.xcep_password),
    })


@bp.route('/api/v2/xcep/config', methods=['PATCH'])
@require_auth(['write:xcep'])
def update_xcep_config():
    """Update the XCEP switch and the default profile's policy CA and account"""
    data = request.json or {}

    if 'enabled' in data:
        set_config('xcep_enabled', 'true' if data['enabled'] else 'false')
    if not {'ca_refid', 'ca_id', 'username', 'password'} & set(data):
        profile = None
    else:
        profile = windows_profiles.default_for_write(_actor())
    current = (profile.policy_ca_refid if profile is not None else None) or ''
    if 'ca_refid' in data:
        if data['ca_refid']:
            ca = CA.query.filter_by(refid=str(data['ca_refid'])).first()
            if not ca:
                db.session.rollback()
                return error_response('CA not found', 404)
            if ca.refid != current and xcep_ca_problem(ca):
                db.session.rollback()
                return error_response(xcep_ca_problem(ca), 400)
        profile.policy_ca_refid = str(data['ca_refid']) if data['ca_refid'] else None
    if 'ca_id' in data:
        if data['ca_id']:
            ca = db.session.get(CA, data['ca_id'])
            if not ca:
                db.session.rollback()
                return error_response('CA not found', 404)
            if ca.refid != current and xcep_ca_problem(ca):
                db.session.rollback()
                return error_response(xcep_ca_problem(ca), 400)
            profile.policy_ca_refid = ca.refid
        else:
            profile.policy_ca_refid = None
    if 'username' in data:
        profile.xcep_username = data['username'] or None
    if 'password' in data and data['password']:
        from utils.password_hash import hash_password
        profile.xcep_password = hash_password(data['password'])

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
