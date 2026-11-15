"""The installation's session epoch: every session carries the one it began under, and a
restore advances it, so no session begun before a restore is accepted after it.

One system_config row, never exported nor restored (services/backup/installation.py):
every worker shares it, whatever store holds the sessions. Read as each request starts,
except protocol, probe and static file paths, which never open a session, and again
when a request presents a session. Absent means no restore ever completed here (epoch 0).
"""
from models import SystemConfig, db

EPOCH_KEY = 'session.restore_epoch'
SESSION_KEY = 'restore_epoch'


def current_epoch() -> int:
    value = db.session.query(SystemConfig.value).filter_by(key=EPOCH_KEY).scalar()
    return int(value) if value else 0


def remember_request_epoch():
    """before_request: the epoch as this request starts, before any identity check.
    Protocol, probe and static file paths never open a session and skip the read."""
    from flask import g, request
    from middleware.mtls_middleware import _is_file_request
    from utils.admin_allowlist import is_exempt_path
    if not (is_exempt_path(request.path) or _is_file_request(request.path)):
        g.session_epoch_at_start = current_epoch()


def request_epoch() -> int:
    """The epoch a session opened by this request carries: the one read as it started,
    so a restore that lands during the login refuses the session it opens."""
    from flask import g, has_request_context
    if has_request_context() and 'session_epoch_at_start' in g:
        return g.session_epoch_at_start
    return current_epoch()


def holds_current_epoch(data) -> bool:
    return (data.get(SESSION_KEY) or 0) == current_epoch()


def advance_epoch() -> int:
    """Commits the next epoch and returns it; raises when it could not be stored."""
    from sqlalchemy import Integer, String, cast, update
    table = SystemConfig.__table__
    try:
        # Workers creating the row together: one INSERT lands, the others do nothing;
        # the increment is one UPDATE, so the write lock orders every advance
        if db.session.connection().dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        db.session.execute(insert(table).values(
            key=EPOCH_KEY, value='0', encrypted=False,
            description='Sessions begun before the last restore are refused',
        ).on_conflict_do_nothing(index_elements=['key']))
        db.session.execute(update(table).where(table.c.key == EPOCH_KEY).values(
            value=cast(cast(table.c.value, Integer) + 1, String)))
        epoch = current_epoch()
        db.session.commit()
        return epoch
    except Exception:
        db.session.rollback()
        raise
