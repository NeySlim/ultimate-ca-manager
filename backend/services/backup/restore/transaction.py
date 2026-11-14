"""One transaction for a whole restore.

The restorers were written to commit as they went, which is why a failure in
a late section left everything before it applied. Rather than rewrite all of
them at once, their commits become flushes for the duration of the restore:
the work reaches the session, stays invisible to everyone else, and is either
committed once at the end or rolled back whole.

A rollback asked for by a restorer is neutralised for the same reason: it
would silently undo the sections that came before it. Errors propagate.
"""
import logging
from contextlib import contextmanager

from models import db

logger = logging.getLogger(__name__)


@contextmanager
def single_transaction():
    """Run a block where every commit is a flush, and commit once at the end."""
    # This scope's Session, not the scoped proxy: another thread's commits stay commits
    session = db.session()
    real_commit = session.commit
    real_rollback = session.rollback

    def flush_instead():
        session.flush()

    def refuse_rollback():
        # A restorer asking to roll back would discard the sections restored
        # before it; the failure it is reacting to must surface instead.
        logger.debug("Restore: a rollback inside the transaction was ignored")

    session.commit = flush_instead
    session.rollback = refuse_rollback
    try:
        yield session
        # HA: the cluster maintenance is still this restore's, or everything rolls back
        from services.cluster_maintenance import before_restore_commit
        before_restore_commit(session)
        session.commit = real_commit
        session.rollback = real_rollback
        session.commit()
    except Exception:
        session.commit = real_commit
        session.rollback = real_rollback
        session.rollback()
        raise
    finally:
        session.commit = real_commit
        session.rollback = real_rollback
