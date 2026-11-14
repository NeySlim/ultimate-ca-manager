"""HA cluster maintenance by hand: around a restore by PostgreSQL's own tools.

These three routes stay served by a node in maintenance (services.cluster_maintenance
.CONTROL_ENDPOINTS): the status, a lift from any node, and setting or extending it.
"""
import logging

from flask import request

from auth.unified import require_auth
from services import cluster_maintenance as cm
from services.audit_service import AuditService
from services.backup.restore_completion import maintenance_refusal, restore_actor
from utils.ha import ha_enabled
from utils.response import error_response, success_response
from . import bp

logger = logging.getLogger(__name__)

HA_ONLY = "Cluster maintenance exists in HA mode only: a single node needs none"


def _audit(action, details):
    try:
        AuditService.log_action(action=action, resource_type='system',
                                resource_name='Cluster maintenance', details=details, success=True)
    except Exception:
        logger.exception('Cluster maintenance: audit entry not written')


@bp.route('/api/v2/system/maintenance', methods=['GET'])
@require_auth(['admin:system'])
def maintenance_status():
    if not ha_enabled():
        return success_response(data={'maintenance': None, 'nodes': [], 'ha': False})
    return success_response(data={**cm.status(), 'ha': True})


@bp.route('/api/v2/system/maintenance', methods=['POST'])
@require_auth(['admin:system'])
def maintenance_begin():
    """Set the manual maintenance (or extend it), once every fresh node acknowledged it."""
    if not ha_enabled():
        return error_response(HA_ONLY, 409)
    payload = request.get_json(silent=True) or {}
    minutes = payload.get('lease_minutes', cm.MANUAL_DEFAULT_MINUTES)
    if isinstance(minutes, bool) or not isinstance(minutes, int) \
            or not 1 <= minutes <= cm.MANUAL_MAX_MINUTES:
        return error_response(
            f'lease_minutes must be a whole number from 1 to {cm.MANUAL_MAX_MINUTES}', 400)
    try:
        with cm.exempt():
            cm.begin_manual(restore_actor(), minutes)
            _audit('cluster_maintenance', f'Cluster maintenance set by hand for {minutes} minute(s)')
    except cm.MaintenanceRefused as refused:
        return maintenance_refusal(refused)
    return success_response(data=cm.status(),
                            message=f'Cluster maintenance set for {minutes} minute(s): every node '
                                    'refuses writes')


@bp.route('/api/v2/system/maintenance', methods=['DELETE'])
@require_auth(['admin:system'])
def maintenance_lift():
    """Lift it from any node; a restore committed by a node that stopped is completed first."""
    if not ha_enabled():
        return error_response(HA_ONLY, 409)
    with cm.exempt():
        row = cm.lift(restore_actor() or 'unknown')
        if row is not None:
            _audit('cluster_maintenance', f"Cluster maintenance lifted ({row['reason']}, {row['phase']})")
    if row is None:
        return success_response(data=cm.status(), message='No cluster maintenance was set')
    return success_response(data=cm.status(), message='Cluster maintenance lifted')
