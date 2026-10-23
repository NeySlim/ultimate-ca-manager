"""Forced password change: until it happens, a session reaches only the change itself.

The account created at first boot carries the documented default password, so
the flag must hold on the server, not only in the UI prompt."""
from auth.twofa_enforcement import ENROLL_ALLOWED_PATHS

# A forced 2FA enrolment comes first in the same session, so its paths (logout
# among them) stay open.
PASSWORD_CHANGE_ALLOWED_PATHS = frozenset({'/api/v2/account/password'}) | ENROLL_ALLOWED_PATHS


def password_change_pending(auth_result) -> bool:
    """Whether this session's account must change its password first.

    API keys are not gated: creating one already needs a full session."""
    if not auth_result or auth_result.get('auth_method') != 'session':
        return False
    return bool(getattr(auth_result.get('user'), 'force_password_change', False))
