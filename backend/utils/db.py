"""
Database transaction helpers.
"""

import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)


@contextmanager
def commit_or_rollback(db, audit_fn=None):
    """
    Context manager that commits on success, rolls back on error.

    Usage:
        with commit_or_rollback(db):
            db.session.add(obj)
        # commit happens here

        # With post-commit audit log (must run after commit):
        with commit_or_rollback(db, audit_fn=lambda: AuditService.log_action(...)):
            db.session.delete(obj)

    Args:
        db: SQLAlchemy db instance
        audit_fn: Optional callable invoked AFTER successful commit
    """
    try:
        yield
        db.session.commit()
        if audit_fn:
            audit_fn()
    except Exception:
        db.session.rollback()
        raise
