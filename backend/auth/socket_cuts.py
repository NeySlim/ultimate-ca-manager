"""The WebSockets of sessions a transaction ends close once it commits, on every process.

A socket that only listens never revalidates: without this cut, a session closed by a
credential change, a factor change, an administrator or a restore would keep receiving
events. Registered at the change, run after the commit (a reconnecting socket then meets
the ended session), forgotten on a rollback.
"""
import logging

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_PENDING = 'ucm_socket_cuts'
_OWED = '_ucm_owed_socket_cuts'


def _on_commit(db_session, cut):
    db_session.info.setdefault(_PENDING, []).append(cut)


def _websocket():
    from websocket import events
    return events


def _callers_session(user_id, replaced):
    """The caller's own session id when ``keep_current_session`` may keep it, else None."""
    from flask import g, has_request_context, session
    if not has_request_context():
        return None
    if getattr(g, 'auth_method', None) != 'session' or getattr(g, 'user_id', None) != user_id:
        return None
    if (session.get('session_version') or 0) != replaced:
        return None
    return getattr(session, 'sid', None)


def _owe(session_id):
    """The spared caller's session: cut at the end of the request unless it moved (kept)."""
    from flask import after_this_request, g, has_request_context
    if not session_id or not has_request_context():
        return
    owed = g.get(_OWED)
    if owed is None:
        owed = set()
        setattr(g, _OWED, owed)

        @after_this_request
        def _cut_owed(response):
            from auth.session_start import close_session_sockets
            for sid in list(g.get(_OWED) or ()):
                close_session_sockets(sid)
            g.get(_OWED, set()).clear()
            return response
    owed.add(session_id)


def account_sessions_ended(db_session, user_id, new_version):
    """``user_id``'s sessions under ``new_version`` end with ``db_session``'s transaction:
    their sockets close at its commit, but the caller's, which keep_current_session may keep."""
    spare = _callers_session(user_id, new_version - 1)

    def cut():
        _owe(spare)
        _websocket().end_account_sockets(user_id, below=new_version, spare_session_id=spare)
    _on_commit(db_session, cut)


def session_moved(session_id, new_session_id, version):
    """A kept session moved to a new identifier: its sockets follow it, none is owed a cut."""
    from flask import g, has_request_context
    if has_request_context():
        (g.get(_OWED) or set()).discard(session_id)
    try:
        _websocket().move_session_sockets(session_id, new_session_id, version)
    except Exception as exc:  # noqa: BLE001  # the socket then dies at its revalidation
        logger.warning("WebSocket sockets not moved with their session: %s", exc)


def epoch_advanced(db_session, epoch):
    """A restore's epoch: every socket opened before it closes at the commit."""
    _on_commit(db_session, lambda: _websocket().end_sockets_before_epoch(epoch))


@event.listens_for(Session, 'before_flush')
def _accounts_closed(db_session, _flush_context, _instances):
    """A deleted or deactivated account keeps no socket."""
    from models.user import User
    for user in db_session.deleted:
        if isinstance(user, User) and user.id is not None:
            _on_commit(db_session, lambda uid=user.id: _websocket().end_account_sockets(uid))
    for user in db_session.dirty:
        if (isinstance(user, User) and user.id is not None and not user.active
                and inspect(user).attrs.active.history.has_changes()):
            _on_commit(db_session, lambda uid=user.id: _websocket().end_account_sockets(uid))


@event.listens_for(Session, 'after_commit')
def _cut_after_commit(db_session):
    if db_session.in_nested_transaction():
        return  # a savepoint: the root transaction may still roll back
    for cut in db_session.info.pop(_PENDING, None) or ():
        try:
            cut()
        except Exception as exc:  # noqa: BLE001  # never fails the committed change
            logger.warning("WebSocket sockets of ended sessions not closed: %s", exc)


@event.listens_for(Session, 'after_transaction_end')
def _forget_on_rollback(db_session, transaction):
    if transaction.parent is None:
        db_session.info.pop(_PENDING, None)
