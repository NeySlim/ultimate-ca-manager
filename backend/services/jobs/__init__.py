"""Background jobs: long operations a route starts and the scheduler process runs.

A route calls ``start(kind, ...)``, which creates the job under its slot (SlotBusy when
taken) and hands it to an executor: the scheduler process under gunicorn, a thread of this
process otherwise. ``wait`` bounds how long the route waits for the end. A job type is a
``JobType`` registered once at import; its ``run(ctx)`` returns a ``JobOutcome``.
"""
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Optional

from services.jobs import store
from services.jobs.store import (  # noqa: F401  (the vocabulary of the callers)
    CANCELLED, EXECUTOR_LOST, FAILED, FINAL_STATES, NOT_TAKEN, PENDING, RUNNING, SUCCEEDED,
    JobLost, SlotBusy,
)

logger = logging.getLogger(__name__)

# Slots: one active job each. A restore holds them all: nothing else runs beside it.
SLOT_BACKUP, SLOT_AUDIT_VERIFY, SLOT_RESTORE = 'backup', 'audit_verify', 'restore'
SLOTS = frozenset({SLOT_BACKUP, SLOT_AUDIT_VERIFY, SLOT_RESTORE})
EXCLUSIVE_SLOTS = frozenset({SLOT_RESTORE})

# The bounded wait of a starting route, under a proxy's 60 s and the worker's timeout
JOB_WAIT_SECONDS = 25


class JobCancelled(Exception):
    """Raised by ctx.progress()/ctx.check() when a cancellation was asked: the run stops."""


@dataclass
class JobOutcome:
    """What a finished run answers: the response the route would have given (code, message,
    data) and the fixed phrase of its audit line. A code of 400 or more ends ``failed``."""
    code: int = 200
    message: Optional[str] = None
    data: Any = None
    audit_details: Optional[str] = None


@dataclass(frozen=True)
class JobType:
    kind: str
    slot: str
    permission: str
    run: Callable[['Any'], JobOutcome]
    label: str
    # None: the job writes no audit line (the audit verification writes none, as before)
    audit_action: Optional[str] = None
    resource_type: str = 'system'
    # HA: only the node that created the job takes it (a restore reads a file of that node)
    node_bound: bool = False
    # Final message when the run gave none (lost, never taken, cancelled), by reason
    messages: Dict[str, str] = field(default_factory=dict)


_TYPES: Dict[str, JobType] = {}


def register(job_type: JobType) -> JobType:
    if job_type.slot not in SLOTS:
        raise ValueError(f'unknown job slot {job_type.slot}')
    _TYPES[job_type.kind] = job_type
    return job_type


def unregister(kind: str) -> None:
    _TYPES.pop(kind, None)


def job_type(kind: str) -> Optional[JobType]:
    return _TYPES.get(kind)


def types() -> Dict[str, JobType]:
    return dict(_TYPES)


def _now(executor=None):
    from services.scheduler_leader import cluster_utc_now
    return cluster_utc_now(executor)


def _requester():
    from flask import g, has_request_context
    if not has_request_context():
        return None, 'system', None
    from utils.trusted_proxy import client_ip
    user = getattr(g, 'current_user', None)
    try:
        ip = client_ip()
    except Exception:
        ip = None
    return (getattr(g, 'user_id', None) or getattr(user, 'id', None),
            getattr(user, 'username', None), ip)


def _node_id():
    from config.settings import Config
    return Config.NODE_ID


def start_job(kind: str, params: Optional[dict] = None, secret: Optional[str] = None,
          file_name: Optional[str] = None, job_id: Optional[str] = None) -> str:
    """Create the job (SlotBusy when its slot is held) and hand it to an executor; its id.

    ``secret`` is encrypted here and stored until the executor takes the job."""
    from models import db
    from utils.ha import ha_enabled
    jt = _TYPES[kind]
    cipher = None
    if secret is not None:
        from utils.encryption import encrypt_value
        cipher = encrypt_value(secret)
    job_id = store.create_job(
        db.session, kind=kind, slot=jt.slot, exclusive=jt.slot in EXCLUSIVE_SLOTS,
        exclusive_slots=EXCLUSIVE_SLOTS, now=_now(), params=params, secret=cipher,
        file_name=file_name, node_id=_node_id() if jt.node_bound and ha_enabled() else None,
        requester=_requester(), job_id=job_id)
    from services.jobs import runner
    runner.dispatch_job(job_id)
    return job_id


def get_job(job_id: str) -> Optional[dict]:
    from models import db
    row = store.job_row(db.session, job_id)
    db.session.rollback()
    return row


def active_job(kind: str) -> Optional[dict]:
    from models import db
    jt = _TYPES[kind]
    rows = [r for r in store.active_jobs(db.session, jt.slot) if r['kind'] == kind]
    db.session.rollback()
    return rows[0] if rows else None


def list_jobs(kinds, state: Optional[str] = None, limit: int = 20) -> list:
    from sqlalchemy import select
    from models import db
    T = store.T
    query = select(T).where(T.c.kind.in_(tuple(kinds) or ('',)))
    if state == 'active':
        query = query.where(T.c.state.in_((PENDING, RUNNING)))
    elif state == 'final':
        query = query.where(T.c.state.in_(FINAL_STATES))
    rows = [dict(r) for r in db.session.execute(
        query.order_by(T.c.created_at.desc()).limit(limit)).mappings()]
    db.session.rollback()
    return rows


def audit_writer(kind: str):
    """The callback store.conclude_job() calls to write the job's result line, or None."""
    jt = _TYPES.get(kind)
    if jt is None or jt.audit_action is None:
        return None

    def _write_job_result_line(row, state, reason, details=None):
        from services.audit_service import AuditService
        written = AuditService.log_action(
            action=jt.audit_action, resource_type=jt.resource_type, resource_name=jt.label,
            resource_id=(row or {}).get('id'),
            details=details or _phrase(jt, state, reason), success=state == SUCCEEDED,
            username=(row or {}).get('requested_by_name') or 'system',
            user_id=(row or {}).get('requested_by_id'),
            ip_address=(row or {}).get('requested_ip'))
        return written is not None
    return _write_job_result_line


_PHRASES = {
    (SUCCEEDED, None): '{label} finished',
    (FAILED, EXECUTOR_LOST): '{label} stopped: the process running it was lost',
    (FAILED, NOT_TAKEN): '{label} was never started',
    (CANCELLED, None): '{label} cancelled',
    (FAILED, None): '{label} failed',
}


def _phrase(jt, state, reason):
    return (_PHRASES.get((state, reason)) or _PHRASES[(state, None)]).format(label=jt.label)


def request_cancellation(job_id: str) -> str:
    """'cancelled', 'requested' or 'final' (store.request_cancel)."""
    from models import db
    row = store.job_row(db.session, job_id)
    db.session.rollback()
    return store.cancel_or_flag(db.session, job_id, _now(), result_line=audit_writer(row['kind']))


def wait_for_job(job_id: str, seconds: float) -> Optional[dict]:
    from services.jobs import runner
    return runner.wait_for_job(job_id, seconds)


def public_view(row: dict, with_result: bool = True) -> dict:
    """What the API shows of a job: no secret, no path, no host name."""
    from utils.datetime_utils import utc_isoformat
    out = {
        'id': row['id'], 'kind': row['kind'], 'state': row['state'], 'reason': row['reason'],
        'phase': row['phase'],
        'progress': {'done': row['progress_done'], 'total': row['progress_total']},
        'cancel_requested': bool(row['cancel_requested']),
        'requested_by': {'id': row['requested_by_id'], 'username': row['requested_by_name']},
        'created_at': utc_isoformat(row['created_at']),
        'started_at': utc_isoformat(row['started_at']),
        'finished_at': utc_isoformat(row['finished_at']),
    }
    if with_result:
        out['result'] = json.loads(row['result']) if row['result'] else None
    return out


# The job types this release ships, registered in every process that imports the service
from services.jobs import audit_verify  # noqa: E402,F401
