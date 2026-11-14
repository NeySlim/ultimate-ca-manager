"""
Database Admin Routes v2.0
Manage database backend (SQLite ↔ PostgreSQL): status, test, switch, migrate.

Both mutating routes hold the migration lock for their whole length, from the
first pre-flight check to the moment the restart is requested, and both
activate the new backend only once every check has passed. The restart itself
is asynchronous, so the lock cannot cover it: a marker written under the lock
refuses the next operation until the service has actually come back on the
backend the configuration now names.

Under Docker, where the restart is the operator's to perform, they return the
same proof the native path acted on, so that the manual step is taken on
evidence rather than on trust.
"""

from flask import Blueprint, request
import logging

from auth.unified import require_auth
from utils.ha import reject_in_ha
from utils.response import success_response, error_response
from services import database_admin_service as svc
from services.database_admin.lock import (
    MigrationBusyError,
    database_migration_lock,
    mark_switch_pending,
    pending_switch_refusal,
)
from services.audit_service import AuditService
from config.settings import Config, is_docker, restart_ucm_service

logger = logging.getLogger(__name__)

bp = Blueprint('database_v2', __name__)

# How a refusal reported by the service layer becomes an HTTP status. A
# refusal raised before anything was written is the caller's conflict to
# resolve (a non-empty target, an unreachable server); anything that failed
# once the work was under way is ours to report as a failure. Two of the
# pre-flight checks — the schema check and the copy plan — run after the
# schema has been created on the target, so the category alone is not enough
# and `target_written` decides.
_REFUSAL_STATUS = {
    'preflight': 409,
    'snapshot': 409,
    'copy': 500,
    'verification': 500,
}


def _refusal_status(stats: dict) -> int:
    """The status for a refusal, given how far the migration got."""
    if stats.get('target_written'):
        return 500
    return _REFUSAL_STATUS.get(stats.get('refusal'), 500)


def _refuse_if_switch_pending():
    """Refuse while a switch has been requested and not yet applied.

    The lock is released when the request returns, but the restart it asked
    for happens afterwards: a watcher unit picks up a signal file. A second
    migration in that window would rewrite the configuration again and the
    service would come up on whichever one wrote last. The marker is cleared
    when the service starts, so restarting is what unblocks this.
    """
    refusal = pending_switch_refusal()
    return error_response(refusal, 409) if refusal else None


def _safe_uri(database_url: str) -> str:
    """Return a DB URI safe to persist or return.

    Audit details are readable by every role holding read:audit and are
    forwarded to syslog, so the DB password must never reach them: an admin
    configuring PostgreSQL would otherwise hand the credential to operators.
    """
    return svc._redact_uri(database_url or 'sqlite (default)')


def _proof(stats: dict) -> dict:
    """What was checked, in the form the operator is shown.

    The same dictionary is returned whether the service restarts itself or
    the operator restarts a container by hand: the manual step deserves the
    same evidence as the automatic one.
    """
    validation = stats.get('validation') or {}
    return {
        'snapshot': stats.get('snapshot'),
        'source_view': stats.get('source_view'),
        'tables': stats.get('tables'),
        'rows': stats.get('rows_migrated', stats.get('rows_copied')),
        'dropped_columns': stats.get('dropped_columns'),
        # Rows written to the source after the snapshot: on the old backend,
        # not on the new one. Nothing else in the pipeline can see them.
        'source_drift': stats.get('source_drift'),
        # Named at the top level rather than left three levels down in a
        # per-check dictionary: "verified" has to say what it did not verify.
        'not_verified': validation.get('not_verified'),
        'validation': validation or None,
    }


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
        msg = svc._redact_uri(msg)
        return success_response(data={'success': ok, 'message': msg})
    except Exception as e:
        logger.error(f"Test connection failed: {e}")
        return error_response('Test failed', 500)


@bp.route('/api/v2/database/switch', methods=['POST'])
@require_auth(['admin:settings'])
@reject_in_ha()
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
        with database_migration_lock(purpose='the backend switch'):
            return _switch_backend()
    except MigrationBusyError as busy:
        return error_response(str(busy), 409)
    except Exception:
        logger.exception("switch_backend failed")
        return error_response('Switch failed', 500)


def _switch_backend():
    """The switch itself, with the migration lock already held."""
    refused = _refuse_if_switch_pending()
    if refused is not None:
        return refused

    data = request.get_json() or {}
    database_url = (data.get('database_url') or '').strip() or None

    if database_url:
        ok, msg = svc.test_connection(database_url)
        if not ok:
            return error_response(
                f'Target DB unreachable: {svc._redact_uri(msg)}', 400)

        # Bootstrap auth/RBAC/SSO/MFA tables to the new (empty) target so
        # admins, custom roles and SSO config survive the switch — without
        # this, the new DB has no users and the operator is locked out.
        ok_boot, boot_msg, boot_stats = svc.bootstrap_auth_to_target(database_url)
        if not ok_boot:
            reset = (
                ' The target now carries a schema; reset it before retrying.'
                if boot_stats.get('target_written') else ''
            )
            return error_response(
                'Pre-flight bootstrap failed, so the backend was not '
                f'switched. {svc._redact_uri(boot_msg)}{reset}',
                _refusal_status(boot_stats),
            )
    else:
        # The file DATABASE_PATH names may be left by an older release: the start must accept it
        refusal = svc.start_refusal(f'sqlite:///{Config.DATABASE_PATH}')
        if refusal:
            return error_response(
                f'The backend was not switched back to SQLite. {refusal}', 409)
        boot_msg = 'Reverting to SQLite default, no bootstrap needed'
        boot_stats = {}

    ok, msg, env_backup = svc.persist_database_url_with_backup(database_url)
    if not ok:
        return error_response(svc._redact_uri(msg), 500)

    # Audit BEFORE restart so the log entry is guaranteed to flush.
    AuditService.log_action(
        action='database.switch',
        resource_type='system',
        details={
            'database_url': _safe_uri(database_url),
            'data_migrated': False,
            'bootstrap': boot_stats,
        },
    )

    ok, restart_msg = restart_ucm_service()
    if not ok:
        return _undo_configuration(
            env_backup, restart_msg,
            'The backend was not switched: the configuration was put back.')

    mark_switch_pending(_safe_uri(database_url))

    return success_response(data={
        'persisted': True,
        'bootstrap': boot_stats,
        'bootstrap_message': boot_msg,
        'validation': boot_stats.get('validation'),
        'restart_initiated': ok,
        'restart_message': restart_msg,
    }, message='Backend switched. Service restarting…')


def _undo_configuration(env_backup, reason: str, summary: str):
    """Put ``ucm.env`` back when the restart could not even be requested.

    A configuration file naming a backend the service was never restarted
    onto is the worst of both worlds: the running instance still uses the old
    database, and the next restart — a package upgrade, a reboot, anything —
    silently moves it to the new one, hours later, with nobody watching.
    """
    restored, restore_msg = svc.restore_previous_database_url(env_backup)
    if restored:
        logger.error("Restart could not be requested (%s); ucm.env restored",
                     reason)
        return error_response(f'{summary} {svc._redact_uri(reason)}', 500)

    logger.critical(
        "Restart could not be requested (%s) and ucm.env could not be "
        "restored (%s)", reason, restore_msg)
    return error_response(
        'The configuration now names the new backend but the service could '
        f'not be restarted ({svc._redact_uri(reason)}), and the previous '
        f'configuration could not be put back ({svc._redact_uri(restore_msg)}). '
        'Check the configuration file before the next restart.', 500)


@bp.route('/api/v2/database/migrate', methods=['POST'])
@require_auth(['admin:settings'])
@reject_in_ha()
def migrate_data():
    """
    Migrate all data from current backend → target_url.
    Native: also persists DATABASE_URL + restarts service.
    Docker:  only migrates data; admin must update env var + restart container manually.
    On failure: target left as-is, source untouched, no persist.
    """
    try:
        with database_migration_lock(purpose='the migration'):
            return _migrate_data()
    except MigrationBusyError as busy:
        return error_response(str(busy), 409)
    except Exception:
        logger.exception("migrate_data failed")
        return error_response('Migration failed', 500)


def _migrate_data():
    """The migration itself, with the migration lock already held."""
    refused = _refuse_if_switch_pending()
    if refused is not None:
        return refused

    data = request.get_json() or {}
    database_url = (data.get('database_url') or '').strip()
    if not database_url:
        return error_response('database_url is required', 400)

    ok, msg, stats = svc.migrate_data(database_url)
    if not ok:
        AuditService.log_action(
            action='database.migrate.failed',
            resource_type='system',
            details={
                'database_url': _safe_uri(database_url),
                'error': svc._redact_uri(msg),
                'stats': stats,
            }
        )
        return error_response(svc._redact_uri(msg), _refusal_status(stats))

    # Docker: skip persist + restart, return the proof the operator acts on.
    if is_docker():
        AuditService.log_action(
            action='database.migrate.success',
            resource_type='system',
            details={
                'database_url': _safe_uri(database_url),
                'stats': stats,
                'docker': True,
            }
        )
        return success_response(data={
            'migrated': True,
            'stats': stats,
            'proof': _proof(stats),
            'restart_initiated': False,
            'docker': True,
            'next_step': (
                'Data migrated and verified. Now update your container with '
                '-e DATABASE_URL=<target_url> and restart it to use the new backend.'
            ),
        }, message='Data migrated and verified. Update container env var and restart manually.')

    # Native: persist + restart, both after every check has passed.
    ok, persist_msg, env_backup = svc.persist_database_url_with_backup(database_url)
    if not ok:
        return error_response(
            'Data migrated but could not persist config: '
            f'{svc._redact_uri(persist_msg)}', 500
        )

    AuditService.log_action(
        action='database.migrate.success',
        resource_type='system',
        details={'database_url': _safe_uri(database_url), 'stats': stats}
    )

    ok, restart_msg = restart_ucm_service()
    if not ok:
        return _undo_configuration(
            env_backup, restart_msg,
            'The data was migrated and verified, but the backend was not '
            'activated: the configuration was put back. The target now holds '
            'the data and is no longer empty, so reset it before retrying.')

    mark_switch_pending(_safe_uri(database_url))

    return success_response(data={
        'migrated': True,
        'stats': stats,
        'proof': _proof(stats),
        'restart_initiated': ok,
        'restart_message': restart_msg,
    }, message='Data migrated and verified. Service restarting…')
