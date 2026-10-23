"""Forced password change: until it happens, a session reaches only the change itself.

The account created at first boot carries the documented default password, so
the flag must hold on the server, not only in the UI prompt."""
from flask import session

from auth.twofa_enforcement import ENROLL_ALLOWED_PATHS, ENROLL_SESSION_KEY

DEFAULT_INITIAL_PASSWORD = 'changeme123'
_ALLOWED_PATHS = frozenset({'/api/v2/account/password', '/api/v2/auth/logout'})


def initial_password_needs_change(password) -> bool:
    """Only the public default must be replaced; a password the operator chose is theirs."""
    return password == DEFAULT_INITIAL_PASSWORD


def password_change_allows(path) -> bool:
    """A forced 2FA enrolment comes first in the same session, so its paths stay open then."""
    return path in _ALLOWED_PATHS or (bool(session.get(ENROLL_SESSION_KEY))
                                      and path in ENROLL_ALLOWED_PATHS)


def password_change_pending(auth_result) -> bool:
    """Whether this session's account must change its password first.

    API keys are not gated: creating one already needs a full session."""
    if not auth_result or auth_result.get('auth_method') != 'session':
        return False
    return bool(getattr(auth_result.get('user'), 'force_password_change', False))
