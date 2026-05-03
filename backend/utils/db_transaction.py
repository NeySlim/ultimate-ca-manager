"""
Database transaction helper.

Provides safe_commit() to replace the repeated try/except pattern around
db.session.commit() in API handlers.
"""

from models import db
from utils.response import error_response


def safe_commit(logger_instance, error_msg="Database operation failed"):
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
    """
    try:
        db.session.commit()
        return True, None
    except Exception as e:
        db.session.rollback()
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
