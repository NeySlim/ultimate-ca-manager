"""The rows of background_jobs: creation under a slot, take, lease, progress and conclusion.

Every change of state is a conditional UPDATE on the previous state: of two actors, one
wins. Plain SQLAlchemy Core on the session or connection given, so a process without the
Flask application (a test's child process) drives the same code.
"""
import json
import logging
import os
import re
import stat
import uuid
from datetime import timedelta

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.exc import IntegrityError

from models.background_job import ACTIVE_STATES, BackgroundJob

logger = logging.getLogger(__name__)

PENDING, RUNNING = 'pending', 'running'
SUCCEEDED, FAILED, CANCELLED = 'succeeded', 'failed', 'cancelled'
FINAL_STATES = (SUCCEEDED, FAILED, CANCELLED)

# Reasons a job ended other than by its own outcome
EXECUTOR_LOST = 'executor_lost'
NOT_TAKEN = 'not_taken'
CANCELLED_REASON = 'cancelled'
ERROR = 'error'
REFUSED = 'refused'
DONE = 'done'

LEASE_SECONDS = 120
NOT_TAKEN_SECONDS = 300
KEEP_DAYS = 30
# pg_advisory_xact_lock key serialising job creation on the whole cluster ('ucmjobs')
CREATE_LOCK_KEY = 0x75636d6a6f6273

FILE_PREFIX = 'job-'
_FILE_NAME = re.compile(r'^job-([0-9a-f-]{36})(\.[a-z0-9]{1,16})?$')

T = BackgroundJob.__table__


class SlotBusy(Exception):
    """Another active job holds the slot (or a restore holds every slot)."""

    def __init__(self, job):
        super().__init__('slot busy')
        self.job = job


class JobLost(Exception):
    """The job is no longer running under this executor: someone else concluded it."""


def _is_pg(executor):
    bind = executor.get_bind() if hasattr(executor, 'get_bind') else executor
    return bind.dialect.name == 'postgresql'


def _job_row(executor, job_id):
    found = executor.execute(select(T).where(T.c.id == job_id)).mappings().first()
    return dict(found) if found is not None else None


def job_row(executor, job_id):
    return _job_row(executor, job_id)


def active_jobs(executor, slot=None):
    query = select(T).where(T.c.state.in_(ACTIVE_STATES)).order_by(T.c.created_at)
    if slot is not None:
        query = query.where(T.c.slot == slot)
    return [dict(r) for r in executor.execute(query).mappings()]


def _conflict(session, job_id, slot, exclusive, exclusive_slots):
    query = select(T).where(T.c.state.in_(ACTIVE_STATES), T.c.id != job_id)
    if not exclusive:
        query = query.where((T.c.slot == slot) | T.c.slot.in_(tuple(exclusive_slots) or ('',)))
    found = session.execute(query.order_by(T.c.created_at).limit(1)).mappings().first()
    return dict(found) if found is not None else None


def create_job(session, *, kind, slot, exclusive, exclusive_slots, now, params=None, secret=None,
           file_name=None, node_id=None, requester=(None, None, None), job_id=None):
    """Insert a pending job and commit, or raise SlotBusy naming the active job.

    PostgreSQL: a transaction lock serialises creations, so the check below sees every
    committed job. SQLite: the insert takes the write lock first. The partial unique index
    on the active slot holds whatever the path."""
    job_id = job_id or str(uuid.uuid4())
    user_id, username, ip = requester
    try:
        if _is_pg(session):
            session.execute(text('SELECT pg_advisory_xact_lock(:k)'), {'k': CREATE_LOCK_KEY})
        session.execute(T.insert().values(
            id=job_id, kind=kind, slot=slot, state=PENDING, node_id=node_id,
            requested_by_id=user_id, requested_by_name=username, requested_ip=ip,
            params=json.dumps(params) if params is not None else None, secret=secret,
            file_name=file_name, cancel_requested=False, created_at=now))
        conflict = _conflict(session, job_id, slot, exclusive, exclusive_slots)
        if conflict is not None:
            session.rollback()
            raise SlotBusy(conflict)
        session.commit()
    except IntegrityError:
        session.rollback()
        held = active_jobs(session, slot)
        raise SlotBusy(held[0] if held else None)
    return job_id


def claim_job(session, job_id, executor, now, lease_seconds=LEASE_SECONDS):
    """Take a pending job: the row as it was (secret included, for memory only), or None.

    The secret is cleared in the same transaction that takes the job."""
    row = _job_row(session, job_id)
    if row is None or row['state'] != PENDING:
        session.rollback()
        return None
    done = session.execute(update(T).where(T.c.id == job_id, T.c.state == PENDING).values(
        state=RUNNING, executor=executor, started_at=now, secret=None,
        lease_expires_at=now + timedelta(seconds=lease_seconds))).rowcount
    if done != 1:
        session.rollback()
        return None
    session.commit()
    return row


def renew_lease(conn, job_id, executor, now, lease_seconds=LEASE_SECONDS):
    return conn.execute(update(T).where(
        T.c.id == job_id, T.c.state == RUNNING, T.c.executor == executor).values(
        lease_expires_at=now + timedelta(seconds=lease_seconds))).rowcount == 1


def write_progress(conn, job_id, executor, done=None, total=None, phase=None):
    """Write the progress of a running job; True when a cancellation was asked. JobLost when
    the job is no longer this executor's."""
    values = {k: v for k, v in (('progress_done', done), ('progress_total', total),
                                ('phase', phase)) if v is not None}
    where = (T.c.id == job_id, T.c.state == RUNNING, T.c.executor == executor)
    if values:
        if conn.execute(update(T).where(*where).values(**values)).rowcount != 1:
            raise JobLost(job_id)
    asked = conn.execute(select(T.c.cancel_requested).where(*where)).first()
    if asked is None:
        raise JobLost(job_id)
    return bool(asked[0])


def conclude_job(session, job_id, *, state, reason, from_states, now, result=None, executor=None,
             where=(), result_line=None):
    """Move a job to a final state if it is still in one of ``from_states``; True when this
    call did it. ``result_line(row, state, reason)`` writes the job's one result line in the same
    transaction and commits it; a falsy return undoes the conclusion."""
    assert state in FINAL_STATES
    row = _job_row(session, job_id)
    conditions = [T.c.id == job_id, T.c.state.in_(tuple(from_states)), *where]
    if executor is not None:
        conditions.append(T.c.executor == executor)
    done = session.execute(update(T).where(*conditions).values(
        state=state, reason=reason, finished_at=now, secret=None, lease_expires_at=None,
        result=json.dumps(result) if result is not None else None)).rowcount
    if done != 1:
        session.rollback()
        return False
    if result_line is not None:
        try:
            written = result_line(row, state, reason)
        except Exception as e:
            logger.error(f"Job {job_id}: result line not written: {type(e).__name__}")
            written = False
        if not written:
            session.rollback()
            return False
    else:
        session.commit()
    if row and row.get('file_name'):
        purge_file(row['file_name'])
    return True


def cancel_or_flag(session, job_id, now, result_line=None):
    """'cancelled' (it was pending), 'requested' (the executor stops at its next check),
    or 'final' (already over)."""
    if conclude_job(session, job_id, state=CANCELLED, reason=CANCELLED_REASON, from_states=(PENDING,),
                now=now, result_line=result_line):
        return 'cancelled'
    done = session.execute(update(T).where(T.c.id == job_id, T.c.state == RUNNING).values(
        cancel_requested=True)).rowcount
    session.commit()
    return 'requested' if done == 1 else 'final'


def recover_orphans(session, *, now, all_running, audit_for=None, mine=None):
    """Conclude the jobs whose executor is gone; returns how many.

    ``all_running``: every running job is an orphan (single node, the scheduler process
    holds the host lock and has just started); otherwise only those whose lease has ended.
    ``mine``: {job id: executor} of jobs this process ran whose thread is gone. Pending jobs
    older than NOT_TAKEN_SECONDS end ``not_taken``."""
    concluded = 0
    lapsed = T.c.lease_expires_at < now
    mine = mine or {}
    query = select(T.c.id, T.c.kind, T.c.executor).where(T.c.state == RUNNING)
    rows = session.execute(query).all()
    session.rollback()
    for job_id, kind, executor in rows:
        extra = () if all_running or mine.get(job_id) == executor else (lapsed,)
        if conclude_job(session, job_id, state=FAILED, reason=EXECUTOR_LOST, from_states=(RUNNING,),
                    now=now, executor=executor, where=extra,
                    result_line=audit_for(kind) if audit_for else None):
            logger.warning(f"Background job {job_id} ({kind}) lost its executor: failed")
            concluded += 1
    cutoff = now - timedelta(seconds=NOT_TAKEN_SECONDS)
    stale = session.execute(select(T.c.id, T.c.kind).where(
        T.c.state == PENDING, T.c.created_at < cutoff)).all()
    session.rollback()
    for job_id, kind in stale:
        if conclude_job(session, job_id, state=FAILED, reason=NOT_TAKEN, from_states=(PENDING,),
                    now=now, where=(T.c.created_at < cutoff,),
                    result_line=audit_for(kind) if audit_for else None):
            logger.warning(f"Background job {job_id} ({kind}) was never taken: failed")
            concluded += 1
    return concluded


def purge_finished(session, now, keep_days=KEEP_DAYS):
    """Drop final jobs older than ``keep_days``, except the latest of each kind."""
    latest = select(T.c.kind, func.max(T.c.created_at).label('at')).where(
        T.c.state.in_(FINAL_STATES)).group_by(T.c.kind)
    keep = set()
    for kind, at in session.execute(latest).all():
        found = session.execute(select(T.c.id).where(
            T.c.kind == kind, T.c.created_at == at, T.c.state.in_(FINAL_STATES))).first()
        if found:
            keep.add(found[0])
    cutoff = now - timedelta(days=keep_days)
    statement = delete(T).where(T.c.state.in_(FINAL_STATES), T.c.finished_at < cutoff)
    if keep:
        statement = statement.where(T.c.id.notin_(keep))
    dropped = session.execute(statement).rowcount
    session.commit()
    return dropped


# -- the file bound to a job -------------------------------------------------

def file_name_for(job_id, suffix=''):
    return f'{FILE_PREFIX}{job_id}{suffix}'


def jobs_tmp_dir():
    from config.settings import DATA_DIR
    return os.path.join(str(DATA_DIR), 'tmp')


def purge_file(name, directory=None):
    """Remove the job's file: a regular file of the job pattern only, never through a link."""
    if not _FILE_NAME.match(name or ''):
        logger.error("Background job file name refused")
        return False
    path = os.path.join(directory or jobs_tmp_dir(), name)
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISREG(info.st_mode):
        logger.warning("Background job file is not a regular file: left in place")
        return False
    try:
        os.unlink(path)
    except OSError as e:
        logger.error(f"Background job file not removed: {type(e).__name__}")
        return False
    return True


def sweep_job_files(executor, directory=None):
    """At start: remove every job file whose job is final or unknown, never an active job's."""
    directory = directory or jobs_tmp_dir()
    try:
        names = os.listdir(directory)
    except OSError:
        return 0
    removed = 0
    for name in names:
        match = _FILE_NAME.match(name)
        if not match:
            continue
        row = _job_row(executor, match.group(1))
        if row is not None and row['state'] in ACTIVE_STATES:
            continue
        removed += purge_file(name, directory)
    return removed
