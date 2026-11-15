"""The installation's session epoch: every session carries the one it began under, and a
restore advances it, so no session begun before a restore is accepted after it.

One system_config row, never exported nor restored (services/backup/installation.py),
shared by every node and worker whatever store holds the sessions. It is read twice:
- once as a request starts, before any identity check (remember_request_epoch, and the
  certificate sign-in on a page), and a session the request opens carries that value: a
  restore that commits while a login checks old credentials refuses the session it opens;
- by every request that presents a session (holds_current_epoch), against the row as it
  is then.
Protocol and probe paths, static files and the SPA shell open no session and skip the first.
"""
from models import SystemConfig, db

EPOCH_KEY = 'session.restore_epoch'
SESSION_KEY = 'restore_epoch'


def current_epoch() -> int:
    value = db.session.query(SystemConfig.value).filter_by(key=EPOCH_KEY).scalar()
    return int(value) if value else 0


_AT_START = 'session_epoch_at_start'


def opens_sessions(path) -> bool:
    """Only the API signs in (the certificate middleware on a page reads for itself)."""
    from utils.admin_allowlist import is_exempt_path
    return path.startswith('/api/') and not is_exempt_path(path)


def remember_request_epoch():
    """before_request, ahead of every hook that may sign in."""
    from flask import request
    if opens_sessions(request.path):
        note_request_epoch()


def note_request_epoch():
    """The epoch as this request started, read once, before its credentials are checked."""
    from flask import g
    if _AT_START not in g:
        setattr(g, _AT_START, current_epoch())


def request_epoch() -> int:
    """The epoch a session opened by this request carries: the one read as it started."""
    from flask import g, has_request_context
    if has_request_context() and _AT_START in g:
        return g.get(_AT_START)
    return current_epoch()


def holds_current_epoch(data) -> bool:
    return (data.get(SESSION_KEY) or 0) == current_epoch()


def advance_epoch() -> int:
    """Commits the next epoch and returns it; raises when it could not be stored."""
    try:
        # Nodes creating the row together: one INSERT lands, the others do nothing,
        # and the row lock then orders every increment
        if db.session.connection().dialect.name == 'postgresql':
            from sqlalchemy.dialects.postgresql import insert
        else:
            from sqlalchemy.dialects.sqlite import insert
        db.session.execute(insert(SystemConfig.__table__).values(
            key=EPOCH_KEY, value='0', encrypted=False,
            description='Sessions begun before the last restore are refused',
        ).on_conflict_do_nothing(index_elements=['key']))
        row = (SystemConfig.query.filter_by(key=EPOCH_KEY)
               .with_for_update().populate_existing().one())
        row.value = str(int(row.value or 0) + 1)
        db.session.commit()
        return int(row.value)
    except Exception:
        db.session.rollback()
        raise
