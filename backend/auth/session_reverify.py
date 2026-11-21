"""A password checked again inside an open session is bounded per account.

Its counter is apart from the login's (``failed_logins``), so a stolen session cannot
lock the holder out of signing in, and apart from the TOTP's: NIST SP 800-63B-4 §3.2.2
limits failures per authenticator. Same threshold and duration as the second factor.
"""
from flask import g

SESSION_PASSWORD = 'session_pw'


def check_session_password(user, password, wrong):
    """None once ``password`` is ``user``'s, the counter cleared; else the response to
    send: the 429 of a locked account, whatever the password, or ``wrong``."""
    from api.v2.auth_methods import (
        _clear_2fa_failures, _get_2fa_lockout_settings, _reserve_attempt, too_many_attempts,
    )
    key = str(user.id)
    rank = _reserve_attempt(SESSION_PASSWORD, key)
    if rank is None:
        return too_many_attempts(SESSION_PASSWORD, key)
    if user.check_password(password):
        _clear_2fa_failures(SESSION_PASSWORD, key)  # also saves a rehashed password
        return None
    max_attempts, _seconds = _get_2fa_lockout_settings()
    if rank == max_attempts:
        # One request gets this rank: the one whose failure armed the lock
        from services.audit_service import AuditService
        caller = getattr(g, 'current_user', None)
        AuditService.log_action(
            action='session_password_locked',
            resource_type='user',
            resource_id=str(user.id),
            resource_name=user.username,
            details=(f'Password checks in a session locked for {user.username} after '
                     f'{max_attempts} failures'),
            success=False,
            username=getattr(caller, 'username', None) or user.username,
        )
    return wrong
