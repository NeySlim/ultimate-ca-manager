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


def confirm_account_holder(user, data):
    """None once the caller proved again that the account is theirs (OWASP ASVS 4.0.3
    V3.7.1), else the 403 or 429 to send. The local password when the account has one;
    an account opened by its provider alone answers with its authenticator code instead,
    and one with neither cannot add a sign-in credential from a session."""
    from api.v2.sso.account_state import SSO_NO_PASSWORD
    from utils.response import error_response
    data = data if isinstance(data, dict) else {}
    if user.password_hash != SSO_NO_PASSWORD:
        password = data.get('password')
        if not isinstance(password, str) or not password:
            return error_response('Enter your password to confirm this change', 403,
                                  details={'reauth': 'password'})
        return check_session_password(
            user, password, error_response('Invalid password', 403, details={'reauth': 'password'}))
    if not user.totp_confirmed:
        return error_response('This account has no password and no authenticator app to '
                              'confirm this change: set up an authenticator app first', 403,
                              details={'reauth': 'none'})
    code = data.get('code')
    if not isinstance(code, str) or not code.strip():
        return error_response('Enter your authenticator code to confirm this change', 403,
                              details={'reauth': 'code'})
    from api.v2.auth_methods import TWO_FA, _clear_2fa_failures, _reserve_2fa_attempt, too_many_attempts
    from auth.totp import consume_totp
    from auth.twofa_enforcement import lock_user
    from models import db
    user_id = user.id
    if not _reserve_2fa_attempt(TWO_FA, str(user_id)):
        return too_many_attempts(TWO_FA, str(user_id))
    holder = lock_user(user_id)
    if holder is None or not consume_totp(holder, code.strip()):
        db.session.rollback()
        return error_response('Invalid verification code', 403, details={'reauth': 'code'})
    db.session.commit()  # the step is spent even if the change fails afterwards
    _clear_2fa_failures(TWO_FA, str(user_id))
    return None
