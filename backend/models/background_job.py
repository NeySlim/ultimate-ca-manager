"""Long operations run by the scheduler process, one row per job (migration 169)."""
from sqlalchemy import Index, text

from models import db

# At most one active (pending or running) job per slot, on the whole installation
ACTIVE_STATES = ('pending', 'running')
_ACTIVE = text("state IN ('pending', 'running')")


class BackgroundJob(db.Model):
    """A backup, restore or audit verification asked by a route and run outside the web worker.

    Runtime state of this installation: never exported, never touched by a restore, and no
    foreign key to ``users`` (the requester is kept as plain values). ``secret`` is a value
    encrypted by utils.encryption, cleared in the transaction that takes the job."""
    __tablename__ = 'background_jobs'

    id = db.Column(db.String(36), primary_key=True)
    kind = db.Column(db.String(32), nullable=False)
    slot = db.Column(db.String(32), nullable=False)
    state = db.Column(db.String(16), nullable=False)
    reason = db.Column(db.String(64))
    node_id = db.Column(db.String(255))
    executor = db.Column(db.String(255))
    requested_by_id = db.Column(db.Integer)
    requested_by_name = db.Column(db.String(255))
    requested_ip = db.Column(db.String(64))
    params = db.Column(db.Text)
    secret = db.Column(db.Text)
    file_name = db.Column(db.String(255))
    progress_done = db.Column(db.BigInteger)
    progress_total = db.Column(db.BigInteger)
    phase = db.Column(db.String(32))
    cancel_requested = db.Column(db.Boolean, nullable=False, default=False)
    result = db.Column(db.Text)
    steps = db.Column(db.Text)
    created_at = db.Column(db.DateTime, nullable=False)
    started_at = db.Column(db.DateTime)
    finished_at = db.Column(db.DateTime)
    lease_expires_at = db.Column(db.DateTime)

    __table_args__ = (
        Index('uq_background_jobs_active_slot', 'slot', unique=True,
              sqlite_where=_ACTIVE, postgresql_where=_ACTIVE),
        Index('ix_background_jobs_kind_created', 'kind', 'created_at'),
        Index('ix_background_jobs_state', 'state'),
    )
