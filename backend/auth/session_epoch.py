"""The installation's session epoch: every session carries the one it began under, and a
restore advances it, so no session begun before a restore is accepted after it.

One system_config row, never exported nor restored (services/backup/installation.py),
shared by every node and worker whatever store holds the sessions. It is read twice:
- once as a login request starts, before any identity check (remember_request_epoch on
  the LOGIN_PATHS, and the certificate middleware before it signs in), and the session
  the request opens carries that value: a restore that commits while a login checks old
  credentials refuses the session it opens;
- by every request that presents a session (holds_current_epoch), against the row as it
  is then.
No other request reads the first; a session opened without it raises (request_epoch).
"""
from models import SystemConfig, db

EPOCH_KEY = 'session.restore_epoch'
SESSION_KEY = 'restore_epoch'


def current_epoch() -> int:
    value = db.session.query(SystemConfig.value).filter_by(key=EPOCH_KEY).scalar()
    return int(value) if value else 0


_AT_START = 'session_epoch_at_start'


# Every route that calls begin_session, and the few beside them that prepare a login;
# the certificate middleware reads for itself.
LOGIN_PATHS = ('/api/v2/auth/login', '/api/v2/sso/ldap/login', '/api/v2/sso/callback/',
               '/api/v2/auth/unlock/')


def opens_sessions(path) -> bool:
    return (path == LOGIN_PATHS[0] or path.startswith(LOGIN_PATHS[0] + '/')
            or path.startswith(LOGIN_PATHS[1:]))


def remember_request_epoch():
    """before_request, after the maintenance gate and before a login route runs."""
    from flask import request
    if opens_sessions(request.path):
        note_request_epoch()


def note_request_epoch():
    """The epoch as this request started, read once, before its credentials are checked."""
    from flask import g
    if _AT_START not in g:
        setattr(g, _AT_START, current_epoch())


def request_epoch() -> int:
    """The epoch a session opened by this request carries: the one read as it started.

    Fails closed: a request that opens a session without that value is a login route
    missing from LOGIN_PATHS, and a later read would hide a restore it overlapped."""
    from flask import g, has_request_context
    if not has_request_context():
        return current_epoch()
    if _AT_START not in g:
        raise RuntimeError('session opened without the epoch read as its request started')
    return g.get(_AT_START)


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
        # read under the row lock: after the commit the row may already be another node's
        epoch = int(row.value or 0) + 1
        row.value = str(epoch)
        from auth.socket_cuts import epoch_advanced
        epoch_advanced(db.session, epoch)
        db.session.commit()
        return epoch
    except Exception:
        db.session.rollback()
        raise
