"""Where a login starts its session, and where a credential change keeps the current one."""
import logging

from flask import current_app, g, session

logger = logging.getLogger(__name__)


def _new_identifier(keep_lock=False):
    """Drop the stored session and give this one a fresh identifier (RFC 6265 §8.4).
    ``keep_lock``: the stored record moves to it at once instead, its lock with it.

    Flask-Session's regenerate() skips an empty session: call it once a key is set.
    """
    interface = current_app.session_interface
    renew = getattr(interface, 'rotate' if keep_lock else 'regenerate', None) or getattr(
        interface, 'regenerate', None)
    # A stored session replaced by a new one (a sign-in) ends: its sockets close once it is gone
    replaced = None
    before = getattr(session, 'sid', None)
    if not keep_lock and getattr(session, 'stored_sid', None) == before:
        replaced = session.sid
    if renew is not None:
        renew(session)
    if replaced and replaced != getattr(session, 'sid', None):
        close_session_sockets(replaced)
    elif (keep_lock and before and before != getattr(session, 'sid', None)
          and not getattr(session, 'store_refused', None)
          and not getattr(session, 'record_gone', False)):
        # A kept session's sockets follow it to its new identifier
        from auth.socket_cuts import session_moved
        session_moved(before, session.sid, session.get('session_version', 0))


# The account's creation time: an id handed out again (SQLite reuses the last
# one deleted) names another account, which this tells apart.
ACCOUNT_KEY = 'account_created'


def account_proof(user) -> str:
    from utils.datetime_utils import to_naive_utc
    created = to_naive_utc(user.created_at)
    return created.isoformat() if created else ''


def begin_session(user, unlocking=False):
    """Empty session under a new identifier, bound to ``user``'s session version and
    to the epoch read as the request started, before its credentials were checked.

    Every login goes through here: an identifier planted before the login never
    becomes an authenticated session, and a locked session is replaced only by its unlock.
    """
    from auth.session_epoch import SESSION_KEY, request_epoch
    from auth.session_lock import SessionLocked, is_locked
    if is_locked() and not unlocking:
        raise SessionLocked()
    session.clear()
    session['session_version'] = user.session_version or 0
    session[ACCOUNT_KEY] = account_proof(user)
    session[SESSION_KEY] = request_epoch()
    _new_identifier()


class SessionNotKept(Exception):
    """The change is committed, the caller's session could not move to its new identifier:
    called after the change's audit, the request answers that the change is saved."""
    message = 'The change is saved, but this session could not be kept: sign in again'


def keep_current_session(user) -> bool:
    """After ``user.end_sessions()`` is committed and audited: this session stays, under a new
    identifier, only if it held the version that bump replaced; a session already closed stays
    closed. Raises SessionNotKept when the store fails the move."""
    replaced, new = getattr(user, '_sessions_bump', (None, None))
    if replaced is None or session.get('session_version', 0) != replaced:
        return False
    session['session_version'] = new
    try:
        _new_identifier(keep_lock=True)
    except Exception as exc:
        raise SessionNotKept() from exc
    return True


def _acts_on_own_account(user) -> bool:
    return getattr(g, 'auth_method', None) == 'session' and getattr(g, 'user_id', None) == user.id


def keep_own_session(user):
    """The caller's own session survives a change it made to its own account."""
    if _acts_on_own_account(user):
        keep_current_session(user)


def _own_record(user):
    """Store id of the record the caller's own session was read from, or None."""
    sid = getattr(session, 'stored_sid', None)
    store_id = getattr(current_app.session_interface, '_get_store_id', None)
    return store_id(sid) if sid and store_id and _acts_on_own_account(user) else None


def session_is_current(user) -> bool:
    """False once the account's sessions were closed after this one began, once a
    restore followed its start, or when the session was opened for an earlier account
    with the same id. A session opened before the proof existed gets it on its first
    request, only if it was opened for this username after this account was created."""
    from auth.session_epoch import holds_current_epoch
    if (session.get('session_version', 0) != (user.session_version or 0)
            or not holds_account(session, user) or not holds_current_epoch(session)):
        return False
    if session.get(ACCOUNT_KEY) is None:
        session[ACCOUNT_KEY] = account_proof(user)
    return True


def holds_account(data, user) -> bool:
    """Whether session ``data`` was opened for this account, not for an earlier one of its id:
    by its proof, else by this username and a login not before the account's creation."""
    proof = data.get(ACCOUNT_KEY)
    if proof is None:
        return data.get('username') == user.username and _opened_after_creation(data, user)
    return proof == account_proof(user)


def _opened_after_creation(data, user) -> bool:
    """Whether the session's login time (naive UTC) is not before the account's creation."""
    from datetime import datetime
    from utils.datetime_utils import to_naive_utc
    try:
        opened = to_naive_utc(datetime.fromisoformat(data.get('login_time') or ''))
    except (TypeError, ValueError):
        return False
    created = to_naive_utc(user.created_at)
    # Every account created since the column exists has a time: NULL is never a recreated one
    return created is None or opened >= created


def other_sessions_closed(user):
    """After ``user.end_sessions()`` is committed: the count of the account's other sessions
    that ended (None: store not listed), the caller's record never one of them. The caller's
    own session is kept afterwards, once the change is audited (keep_own_session)."""
    replaced, _new = getattr(user, '_sessions_bump', (None, None))
    if replaced is None:
        return 0
    from utils.session_census import count_sessions
    return count_sessions(user, replaced, other_than=_own_record(user))


def closed_sessions_note(count):
    """Audit wording of other_sessions_closed()."""
    if count is None:
        return 'other sessions closed'
    return f"{count} other session{'' if count == 1 else 's'} closed"


def end_sessions_on_commit(user_id):
    """The account row, locked, its sessions ended in the transaction the factor change
    commits: change and closure stand or fall together. None: no such account."""
    from auth.twofa_enforcement import lock_user
    owner = lock_user(user_id)
    if owner is not None:
        owner.end_sessions()
    return owner


def close_session_sockets(session_id, username=None):
    """The sockets of a session that ends or locks close now, on every node; never fails the
    request (the 60 s revalidation closes them otherwise)."""
    try:
        from websocket.events import end_session_sockets
        end_session_sockets(session_id)
    except Exception as e:  # noqa: BLE001
        logger.warning("Non-blocking: the sockets of %s's session not closed: %s", username, e, exc_info=True)
