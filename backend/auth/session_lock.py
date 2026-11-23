"""A locked session keeps its account and serves nothing until that account proves itself again.

The lock lives in the session data, so a shared store (SQL, Redis) holds it on every node.
Only an explicit unlock (api/v2/auth_unlock.py) or a sign-out lifts it: no sign-in door,
certificate auto-login or SSO return replaces it.
"""
from flask import request, session

LOCK_KEY = 'locked'
# The second factor owed by a password unlock, bound to the locked account
UNLOCK_2FA_KEY = 'unlock_2fa'
SESSION_LOCKED_PROBLEM = 'urn:ucm:problem:session-locked'
# A lock the store did not take: its record went meanwhile ('gone') or stayed held ('busy')
LOCK_NOT_STORED_PROBLEM = 'urn:ucm:problem:session-lock-not-stored'
LOCK_RETRY_AFTER_SECONDS = 1


class SessionLocked(Exception):
    """A sign-in tried to start a session over a locked one."""


def locked_state(data=None):
    """The lock of ``data`` (the request's session by default): {'at', 'reason'}, or None."""
    state = (session if data is None else data).get(LOCK_KEY)
    return state if isinstance(state, dict) else None


def is_locked(data=None) -> bool:
    return locked_state(data) is not None


def locks_this_request() -> bool:
    """The session cookie of this request is locked; a presented API key is its own credential."""
    from auth.unified import presented_api_key
    return is_locked() and not presented_api_key(request)


def lock_session(reason):
    from utils.datetime_utils import utc_now
    session.pop(UNLOCK_2FA_KEY, None)
    session[LOCK_KEY] = {'at': utc_now().isoformat(), 'reason': reason}


def store_lock():
    """Writes the lock of this request's session now: None once stored, else why not."""
    from flask import current_app
    write_now = getattr(current_app.session_interface, 'write_now', None)
    return write_now(current_app, session) if write_now is not None else None


def lock_not_stored(cause):
    """The 409 of a lock the store did not take: the client sends it again, then signs out."""
    from utils.response import error_response
    response, status = error_response('Session lock not stored: send it again', 409,
                                      problem_type=LOCK_NOT_STORED_PROBLEM,
                                      details={'cause': cause})
    response.headers['Retry-After'] = str(LOCK_RETRY_AFTER_SECONDS)
    return response, status


def locked_refusal():
    """The 401 of a locked session, told apart from "not signed in" by its type."""
    from utils.response import error_response
    state = locked_state() or {}
    return error_response('Session locked', 401, problem_type=SESSION_LOCKED_PROBLEM,
                          details={'username': session.get('username'),
                                   'reason': state.get('reason')})


def refuse_sign_in_while_locked(door):
    """A sign-in door's answer while the session is locked (audited), else None.

    Refused before any credential is read: another account signs in after a sign-out."""
    if not locks_this_request():
        return None
    audit_unlock_failure(session.get('username'), session.get('user_id'),
                         f'{door} sign-in refused: the session is locked')
    return locked_refusal()


def audit_unlock_failure(username, user_id, details):
    from services.audit_service import AuditService
    AuditService.log_auth('session_unlock_failure', username=username or 'unknown',
                          user_id=user_id, details=details, success=False)


def locked_account():
    """The active account of the locked session, or None (gone, disabled, or a recreated id)."""
    from auth.session_start import holds_account
    from models import User, db
    user_id = session.get('user_id')
    user = db.session.get(User, user_id) if user_id else None
    if user is None or not user.active or not holds_account(session, user):
        return None
    return user


def local_password(user) -> bool:
    from api.v2.sso.account_state import SSO_NO_PASSWORD
    return bool(user.password_hash) and user.password_hash != SSO_NO_PASSWORD


def directory_of(user):
    """The enabled LDAP provider attached to ``user`` (lowest id), or None."""
    providers = [row.provider for row in user.sso_identities
                 if row.provider is not None and row.provider.provider_type == 'ldap'
                 and row.provider.enabled]
    return min(providers, key=lambda p: p.id) if providers else None


def password_source(user):
    """('ldap', provider), ('local', None) or (None, None): where an unlock checks the password.
    The directory wins for a session it opened, or for an account without a local password."""
    directory = directory_of(user)
    if directory is not None and (session.get('auth_method') == 'ldap' or not local_password(user)):
        return 'ldap', directory
    if local_password(user):
        return 'local', None
    return None, None


def has_certificate(user) -> bool:
    from models.auth_certificate import AuthCertificate
    from services.mtls_auth_service import MTLSAuthService
    from utils.datetime_utils import to_naive_utc, utc_now
    if not MTLSAuthService.is_mtls_enabled():
        return False
    now = to_naive_utc(utc_now())
    return any(cert.valid_until is None or to_naive_utc(cert.valid_until) > now
               for cert in AuthCertificate.query.filter_by(user_id=user.id, enabled=True))


def has_passkey(user) -> bool:
    from models.webauthn import WebAuthnCredential
    return WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True).first() is not None


def unlock_methods(user):
    """The doors this account may unlock with on this instance, in the lock screen's order."""
    if user is None:
        return []
    methods = []
    if password_source(user)[0]:
        methods.append('password')
    if has_certificate(user):
        methods.append('certificate')
    if has_passkey(user):
        methods.append('passkey')
    return methods


def locked_summary():
    """What the lock screen shows of a locked session: its account and the ways to unlock it."""
    user = locked_account()
    state = locked_state() or {}
    custom = getattr(user, 'custom_role', None)
    return {
        'username': session.get('username') or (user.username if user else None),
        'name': user.full_name if user else None,
        'role': (custom.name if custom is not None else user.role) if user else None,
        'method': session.get('auth_method'),
        'reason': state.get('reason'),
        'methods': unlock_methods(user),
    }
