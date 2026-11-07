"""Where a login starts its session, and where a credential change keeps the current one."""
from flask import current_app, g, session


def _new_identifier():
    """Drop the stored session and give this one a fresh identifier (RFC 6265 §8.4).

    Flask-Session's regenerate() skips an empty session: call it once a key is set.
    """
    regenerate = getattr(current_app.session_interface, 'regenerate', None)
    if regenerate is not None:
        regenerate(session)


def begin_session(user):
    """Empty session under a new identifier, bound to ``user``'s session version.

    Every login goes through here: an identifier planted before the login never
    becomes an authenticated session.
    """
    session.clear()
    session['session_version'] = user.session_version or 0
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
    """False once the account's sessions were closed after this one began."""
    return session.get('session_version', 0) == (user.session_version or 0)
