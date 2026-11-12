"""
MS-WSTEP Management Routes v2.0
/api/v2/wstep/* - WSTEP (certificate enrollment) configuration
"""

from utils.signing_ca import signing_ca_problem
from flask import Blueprint, request
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, SystemConfig, CA
from services.audit_service import AuditService
from services import windows_profiles
import logging

logger = logging.getLogger(__name__)

bp = Blueprint('wstep_v2', __name__)


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


@bp.route('/api/v2/wstep/config', methods=['GET'])
@require_auth(['read:wstep'])
def get_wstep_config():
    """WSTEP configuration: the switch, and the default profile's issuing CA, account and validity"""
    profile = windows_profiles.default_profile()
    ca_refid = (profile.issuing_ca_refid if profile is not None else None) or ''
    ca_id = None
    ca_name = None
    if ca_refid:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if ca:
            ca_id = ca.id
            ca_name = ca.descr

    return success_response(data={
        'enabled': get_config('wstep_enabled', 'false') == 'true',
        'ca_refid': ca_refid,
        'ca_id': ca_id,
        'ca_name': ca_name,
        'username': (profile.wstep_username if profile is not None else None) or '',
        'password_set': bool(profile is not None and profile.wstep_password),
        'validity_days': (profile.validity_days if profile is not None else None) or 365,
    })


@bp.route('/api/v2/wstep/config', methods=['PATCH'])
@require_auth(['write:wstep'])
def update_wstep_config():
    """Update the WSTEP switch and the default profile's issuing CA, account and validity"""
    data = request.json or {}

    # gunicorn_config.py reads wstep_enabled once at worker startup to
    # decide whether the whole server needs the TLS-1.2-only cap some
    # Windows WSTEP/CEP clients require (see its ssl_context() docstring)
    # -- a toggle here needs a restart to actually take effect, same as
    # the HTTPS certificate change below.
    enabled_changed = 'enabled' in data and (
        (get_config('wstep_enabled', 'false') == 'true') != bool(data['enabled'])
    )

    if 'enabled' in data:
        set_config('wstep_enabled', 'true' if data['enabled'] else 'false')
    profile = (windows_profiles.default_for_write(_actor())
               if {'ca_refid', 'ca_id', 'username', 'password', 'validity_days'} & set(data) else None)
    current = (profile.issuing_ca_refid if profile is not None else None) or ''
    if 'ca_refid' in data:
        if data['ca_refid']:
            ca = CA.query.filter_by(refid=str(data['ca_refid'])).first()
            if not ca:
                db.session.rollback()
                return error_response('CA not found', 404)
            # WSTEP issues: the CA must be able to sign when it is chosen
            if ca.refid != current and signing_ca_problem(ca):
                db.session.rollback()
                return error_response(signing_ca_problem(ca), 400)
        profile.issuing_ca_refid = str(data['ca_refid']) if data['ca_refid'] else None
    if 'ca_id' in data:
        if data['ca_id']:
            ca = db.session.get(CA, data['ca_id'])
            if not ca:
                db.session.rollback()
                return error_response('CA not found', 404)
            if ca.refid != current and signing_ca_problem(ca):
                db.session.rollback()
                return error_response(signing_ca_problem(ca), 400)
            profile.issuing_ca_refid = ca.refid
        else:
            profile.issuing_ca_refid = None
    if 'username' in data:
        profile.wstep_username = data['username'] or None
    if 'password' in data and data['password']:
        from utils.password_hash import hash_password
        profile.wstep_password = hash_password(data['password'])
    if 'validity_days' in data:
        # Bound to PKI-internal cap (10 years), same as EST.
        from utils.validity import (MAX_VALIDITY_DAYS, MIN_VALIDITY_DAYS,
                                    coerce_validity_days, validity_days_in_range)
        vd = coerce_validity_days(data['validity_days'])
        if vd is None:
            db.session.rollback()
            return error_response('validity_days must be an integer', 400)
        if not validity_days_in_range(vd):
            db.session.rollback()
            return error_response(
                f'validity_days must be between {MIN_VALIDITY_DAYS} and {MAX_VALIDITY_DAYS}',
                400)
        profile.validity_days = vd

    # HA: the restart is queued with the setting, or neither is saved
    from utils.ha import ha_enabled
    rolling = enabled_changed and ha_enabled()
    if rolling:
        from services.cluster_commands import RESTART, emit
        emit(RESTART)

    ok, _err = safe_commit(logger, "Failed to update WSTEP configuration")
    if not ok:
        return _err

    AuditService.log_action(
        action='wstep_config_update',
        resource_type='wstep',
        resource_name='WSTEP Configuration',
        details='Updated WSTEP configuration',
        success=True
    )

    if rolling:
        return success_response(message='WSTEP configuration saved. Rolling restart requested: '
                                         'the nodes restart one at a time.')
    if enabled_changed:
        from config.settings import is_docker
        if is_docker():
            return success_response(
                message='WSTEP configuration saved. Restart the container to apply the TLS behavior change.',
                data={'requires_container_restart': True},
            )

        from utils.service_manager import restart_service
        success, msg = restart_service()
        if not success:
            logger.warning("WSTEP config saved but service restart failed: %s", msg)
            return success_response(
                message='WSTEP configuration saved, but the automatic restart failed -- '
                        'restart UCM manually for the TLS behavior change to take effect.',
                data={'restart_failed': True},
            )
        return success_response(message='WSTEP configuration saved. Service restarting...')

    return success_response(message='WSTEP configuration saved')
