"""
Database transaction helper.

Provides safe_commit() to replace the repeated try/except pattern around
db.session.commit() in API handlers.
"""

from models import db
from utils.response import error_response


def is_deadlock(exc) -> bool:
    """Whether ``exc`` is PostgreSQL's deadlock_detected (40P01)."""
    orig = getattr(exc, 'orig', None)
    return (getattr(orig, 'sqlstate', None) or getattr(orig, 'pgcode', None)) == '40P01'


def deadlock_savepoint():
    """A savepoint for work PostgreSQL may abort with a deadlock, else None: SQLite has none, and
    the RELEASE of a savepoint pysqlite opened outside a transaction would commit it."""
    if db.session.get_bind().dialect.name != 'postgresql':
        return None
    return db.session.begin_nested()


def safe_commit(logger_instance, error_msg="Database operation failed", on_conflict=None):
    """
    Attempt db.session.commit(); roll back and return an error response on failure.

    Returns:
        (True, None)               on success
        (False, Flask response)    on exception (session is rolled back)

    Usage::

        ok, err = safe_commit(logger, "Failed to create certificate")
        if not ok:
            return err
        AuditService.log_action(...)
        return success_response(data=cert.to_dict())

    ``on_conflict``: called after the rollback of an IntegrityError; the response it returns,
    if any, answers instead of the 500 (a constraint a concurrent request won first).
    """
    from sqlalchemy.exc import IntegrityError
    try:
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
        if on_conflict is not None and isinstance(e, IntegrityError):
            answer = on_conflict()
            if answer is not None:
                logger_instance.warning(f"{error_msg}: {e.orig}")
                return False, answer
        logger_instance.error(f"{error_msg}: {e}", exc_info=True)
        return False, error_response(error_msg, 500)


def commit_or_rollback(logger_instance, error_msg="Database operation failed"):
    """
    Service-layer variant of safe_commit().

    Attempts db.session.commit(); on failure rolls back, logs with traceback,
    and returns False. No Flask response (callers in services/auth handle
    the failure however they need to).

    Returns:
        True   on success
        False  on exception (session is rolled back, error logged with stacktrace)

    Usage::

        from utils.db_transaction import commit_or_rollback

        api_key.last_used_at = utc_now()
        if not commit_or_rollback(logger, "Failed to update api_key.last_used_at"):
            return None
    """
    try:
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger_instance.error(f"{error_msg}: {e}", exc_info=True)
        return False
