"""
Database Admin Routes v2.0
Manage database backend (SQLite ↔ PostgreSQL): status, test, switch, migrate.
"""

from flask import Blueprint, request
import logging

from auth.unified import require_auth
from utils.response import success_response, error_response
from services import database_admin_service as svc
from services.audit_service import AuditService
from config.settings import is_docker, restart_ucm_service

logger = logging.getLogger(__name__)

bp = Blueprint('database_v2', __name__)


@bp.route('/api/v2/database/status', methods=['GET'])
@require_auth(['read:settings'])
def get_status():
    """Return current backend status (type, version, size, table count, health)."""
    try:
        status = svc.get_status()
        return success_response(data=status)
    except Exception as e:
        logger.error(f"Failed to get DB status: {e}")
        return error_response('Failed to get database status', 500)


@bp.route('/api/v2/database/test', methods=['POST'])
@require_auth(['admin:settings'])
def test_connection():
    """Validate a DATABASE_URL by opening a test connection."""
    try:
        data = request.get_json() or {}
        database_url = data.get('database_url', '').strip()
        if not database_url:
            return error_response('database_url is required', 400)

        ok, msg = svc.test_connection(database_url)
        if ok:
            return success_response(data={'success': True, 'message': msg})
        return success_response(data={'success': False, 'message': msg})
    except Exception as e:
        logger.error(f"Test connection failed: {e}")
        return error_response('Test failed', 500)


@bp.route('/api/v2/database/switch', methods=['POST'])
@require_auth(['admin:settings'])
def switch_backend():
    """
    Switch database backend WITHOUT migrating data.
    Pass database_url=null/empty to revert to SQLite default.
    Triggers service restart.
    """
    if is_docker():
        return error_response(
            'Switching DB in Docker is not supported. Set DATABASE_URL env var on the container.',
            400
        )

    try:
        data = request.get_json() or {}
        database_url = (data.get('database_url') or '').strip() or None

        if database_url:
            ok, msg = svc.test_connection(database_url)
            if not ok:
                return error_response(f'Target DB unreachable: {msg}', 400)

        ok, msg = svc.persist_database_url(database_url)
        if not ok:
            return error_response(msg, 500)

        AuditService.log_action(
            action='database.switch',
            resource_type='system',
            details={'database_url': database_url or 'sqlite (default)', 'data_migrated': False}
        )

        ok, restart_msg = restart_ucm_service()
        return success_response(data={
            'persisted': True,
            'restart_initiated': ok,
            'restart_message': restart_msg,
        }, message='Backend switched. Service restarting…')
    except Exception as e:
        logger.exception("switch_backend failed")
        return error_response('Switch failed', 500)


@bp.route('/api/v2/database/migrate', methods=['POST'])
@require_auth(['admin:settings'])
def migrate_data():
    """
    Migrate all data from current backend → target_url.
    Native: also persists DATABASE_URL + restarts service.
    Docker:  only migrates data; admin must update env var + restart container manually.
    On failure: target left as-is, source untouched, no persist.
    """
    try:
        data = request.get_json() or {}
        database_url = (data.get('database_url') or '').strip()
        if not database_url:
            return error_response('database_url is required', 400)

        ok, msg, stats = svc.migrate_data(database_url)
        if not ok:
            AuditService.log_action(
                action='database.migrate.failed',
                resource_type='system',
                details={'database_url': database_url, 'error': msg, 'stats': stats}
            )
            return error_response(msg, 500)

        # Docker: skip persist + restart, return instructions
        if is_docker():
            AuditService.log_action(
                action='database.migrate.success',
                resource_type='system',
                details={'database_url': database_url, 'stats': stats, 'docker': True}
            )
            return success_response(data={
                'migrated': True,
                'stats': stats,
                'restart_initiated': False,
                'docker': True,
                'next_step': (
                    'Data migrated. Now update your container with '
                    '-e DATABASE_URL=<target_url> and restart it to use the new backend.'
                ),
            }, message='Data migrated. Update container env var and restart manually.')

        # Native: persist + restart
        ok, persist_msg = svc.persist_database_url(database_url)
        if not ok:
            return error_response(
                f'Data migrated but could not persist config: {persist_msg}', 500
            )

        AuditService.log_action(
            action='database.migrate.success',
            resource_type='system',
            details={'database_url': database_url, 'stats': stats}
        )

        ok, restart_msg = restart_ucm_service()
        return success_response(data={
            'migrated': True,
            'stats': stats,
            'restart_initiated': ok,
            'restart_message': restart_msg,
        }, message='Data migrated. Service restarting…')
    except Exception as e:
        logger.exception("migrate_data failed")
        return error_response('Migration failed', 500)
