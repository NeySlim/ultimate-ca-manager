"""What has to happen once a restore has been applied, for either route.

There are two ways to ask for a restore and they had drifted apart on every
step after the archive was read: one recorded the restore in a way that could
turn a success into a failure, one asked the service to restart and the other
told the operator to do it themselves, and only one of them handed back what
the archive had said about itself.

The steps live here so that the page an operator happened to use stops
deciding what their restore does.
"""
import logging

from services.audit_service import AuditService

logger = logging.getLogger(__name__)


def record_restore(**fields) -> None:
    """Write an audit entry without letting it undo the answer.

    `AuditService.log_action` catches its own failures, but its handler calls
    `db.session.rollback()`, which can raise in turn on a connection a
    replacing restore has just invalidated. Called bare inside a route whose
    outer handler answers 500, that turned a restore that had completed into
    "Restore failed". One route had always guarded it and the other had not.
    """
    try:
        AuditService.log_action(**fields)
    except Exception:
        logger.exception("Operation completed but audit logging failed")


def record_failure(action: str, resource_name: str, reason: str) -> None:
    """Audit a backup or restore that was refused or failed, with `success=False`.

    One rule for both routes: every attempt the route itself refuses or sees fail leaves
    exactly one line, whose reason is a fixed phrase, never exception text, password or path.
    A request stopped before the route (body over the upload limit, HA guard, wrong media type) leaves none.
    """
    record_restore(action=action, resource_type='system',
                   resource_name=resource_name, details=reason, success=False)


# Stable prefix of a restore refused before the archive was read (the bell keys on it).
REQUEST_REFUSED = 'Restore request refused: '


def record_request_refusal(resource_name: str, reason: str) -> None:
    record_failure('system_restore', resource_name, REQUEST_REFUSED + reason)


def request_restart() -> tuple:
    """Ask the service to restart, the one way this project restarts.

    A restore replaces the certificate authorities, their keys and the
    identities; the running workers hold the previous ones in memory.

    Returns (requested, message). `restart_service` returns a pair, and
    reading it as a single truth value made `restart_requested` true even
    when the restart had not been asked for: the operator was told to sign in
    again and nothing was coming.
    """
    try:
        from utils.service_manager import restart_service
        requested, detail = restart_service()
        return bool(requested), (detail or "restart requested")
    except Exception as exc:
        logger.warning("Restore: could not request a restart: %s", exc)
        return False, "restart the service manually"


def restore_message(results) -> str:
    """The sentence both routes answer with, warnings included."""
    from services.backup.restore_report import with_restore_warnings

    requested = (results or {}).get('restart_requested')
    detail = (results or {}).get('restart_detail') or 'restart the service manually'
    opening = ("Backup restored successfully. Sign in again"
               if requested else
               f"Backup restored successfully. Restart the service to "
               f"finish: {detail}")
    return with_restore_warnings(opening, results)
