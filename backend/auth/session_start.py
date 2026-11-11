"""Where a login starts its session, and where a credential change keeps the current one."""
from flask import current_app, g, session


def _new_identifier():
    """Drop the stored session and give this one a fresh identifier (RFC 6265 §8.4).

    Flask-Session's regenerate() skips an empty session: call it once a key is set.
    """
    regenerate = getattr(current_app.session_interface, 'regenerate', None)
    if regenerate is not None:
        regenerate(session)


# The account's creation time: an id handed out again (SQLite reuses the last
# one deleted) names another account, which this tells apart.
ACCOUNT_KEY = 'account_created'


def account_proof(user) -> str:
    from utils.datetime_utils import to_naive_utc
    created = to_naive_utc(user.created_at)
    return created.isoformat() if created else ''


def begin_session(user):
    """Empty session under a new identifier, bound to ``user``'s session version.

    Every login goes through here: an identifier planted before the login never
    becomes an authenticated session.
    """
    session.clear()
    session['session_version'] = user.session_version or 0
    session[ACCOUNT_KEY] = account_proof(user)
    _new_identifier()


def keep_current_session(user) -> bool:
    """After ``user.end_sessions()``: this session stays, under a new identifier,
    only if it held the version that bump replaced; a session already closed stays closed."""
    replaced, new = getattr(user, '_sessions_bump', (None, None))
    if replaced is None or session.get('session_version', 0) != replaced:
        return False
    session['session_version'] = new
    _new_identifier()
    return True


def keep_own_session(user):
    """The caller's own session survives a change it made to its own account."""
    if getattr(g, 'auth_method', None) == 'session' and getattr(g, 'user_id', None) == user.id:
        keep_current_session(user)


def session_is_current(user) -> bool:
    """False once the account's sessions were closed after this one began, or
    when the session was opened for an earlier account with the same id.
    A session opened before the proof existed gets it on its first request,
    only if it was opened for this username after this account was created."""
    if session.get('session_version', 0) != (user.session_version or 0):
        return False
    proof = session.get(ACCOUNT_KEY)
    if proof is None:
        if session.get('username') != user.username or not _opened_after_creation(user):
            return False
        session[ACCOUNT_KEY] = account_proof(user)
        return True
    return proof == account_proof(user)


def _opened_after_creation(user) -> bool:
    """Whether the session's login time (naive UTC) is not before the account's creation."""
    from datetime import datetime
    from utils.datetime_utils import to_naive_utc
    try:
        opened = to_naive_utc(datetime.fromisoformat(session.get('login_time') or ''))
    except (TypeError, ValueError):
        return False
    created = to_naive_utc(user.created_at)
    # Every account created since the column exists has a time: NULL is never a recreated one
    return created is None or opened >= created
