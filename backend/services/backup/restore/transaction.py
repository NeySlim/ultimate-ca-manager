"""One transaction for a whole restore.

The restorers were written to commit as they went, which is why a failure in
a late section left everything before it applied. Rather than rewrite all of
them at once, their commits become flushes for the duration of the restore:
the work reaches the session, stays invisible to everyone else, and is either
committed once at the end or rolled back whole.

A rollback asked for by a restorer is neutralised for the same reason: it
would silently undo the sections that came before it. Errors propagate.
"""
import contextvars
import logging
from contextlib import contextmanager

from models import db

logger = logging.getLogger(__name__)

# What the job running this restore writes in its transaction just before it commits
_commit_mark = contextvars.ContextVar('ucm_restore_commit_mark', default=None)


@contextmanager
def marking(mark):
    """``mark(session, report)`` runs inside the restore transaction, last before its commit:
    whatever it writes commits with the restore or rolls back with it."""
    token = _commit_mark.set(mark)
    try:
        yield
    finally:
        _commit_mark.reset(token)


_progress = contextvars.ContextVar('ucm_restore_progress', default=None)
_row = contextvars.ContextVar('ucm_restore_row', default=None)
_inside = contextvars.ContextVar('ucm_restore_inside', default=False)


@contextmanager
def progressing(hook, row=None):
    """``hook(step)`` runs at each checkpoint of the restore, ``row(applied, total)`` at each
    row of its loops (braked by time on its side); what either raises stops the restore."""
    token = _progress.set(hook)
    row_token = _row.set(row)
    try:
        yield
    finally:
        _row.reset(row_token)
        _progress.reset(token)


def checkpoint(step):
    hook = _progress.get()
    if hook is not None:
        hook(step)


def tick(applied=0):
    """A checkpoint inside a loop of rows: ``applied`` rows written since the last one."""
    row = _row.get()
    if row is not None:
        row(applied)


def expect_rows(total):
    """The rows the restore is about to write, for its progress."""
    row = _row.get()
    if row is not None:
        row(0, total)


def ticking(rows):
    """``rows`` with a row checkpoint before each one (a loop that writes nothing)."""
    for row in rows:
        tick()
        yield row


def inside():
    """The restore transaction is open in this context (SQLite: it holds the database)."""
    return _inside.get()


@contextmanager
def single_transaction(report=None):
    """Run a block where every commit is a flush, and commit once at the end.
    ``report``: the restore's results as known before the commit, given to the job's mark."""
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
    inside_token = _inside.set(True)
    try:
        if session.get_bind().dialect.name == 'postgresql':
            # The tables fill from empty: a plan cached on their first rows would scan them
            # for every later lookup (psycopg prepares from the sixth run), so plan each run
            from sqlalchemy import text
            session.execute(text("SET LOCAL plan_cache_mode = force_custom_plan"))
        yield session
        # HA: the cluster maintenance is still this restore's, or everything rolls back
        from services.cluster_maintenance import before_restore_commit
        before_restore_commit(session)
        mark = _commit_mark.get()
        if mark is not None:
            mark(session, report)
        session.commit = real_commit
        session.rollback = real_rollback
        session.commit()
    except Exception:
        session.commit = real_commit
        session.rollback = real_rollback
        session.rollback()
        raise
    finally:
        _inside.reset(inside_token)
        session.commit = real_commit
        session.rollback = real_rollback
