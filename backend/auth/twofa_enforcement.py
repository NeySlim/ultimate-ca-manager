"""2FA enforcement policy (#141).

Centralises the decision "must this login enrol a second factor (TOTP or a
security key) before getting a full session?" so the login flows, the
require_auth gate, and the factor-removal guards all agree. Local accounts are gated by the global ``enforce_2fa`` setting; SSO
accounts by their provider's own ``enforce_2fa`` toggle (independent switches).
"""
import logging

logger = logging.getLogger(__name__)

# Session flag marking a partially-authenticated session that may only reach the
# 2FA enrolment endpoints until TOTP is confirmed or a security key registered.
ENROLL_SESSION_KEY = 'must_enroll_2fa'

# Exact request paths reachable while in the forced-enrolment state. Everything
# else returns 403 until the user confirms TOTP (or logs out).
ENROLL_ALLOWED_PATHS = frozenset({
    '/api/v2/account/2fa/enable',
    '/api/v2/account/2fa/confirm',
    '/api/v2/webauthn/register/options',
    '/api/v2/webauthn/register/verify',
    '/api/v2/auth/logout',
})

# Auth methods that are themselves a strong second factor — never additionally
# forced to enrol TOTP. mTLS in particular is the documented break-glass path.
_EXEMPT_AUTH_METHODS = frozenset({'mtls', 'webauthn'})


def global_enforce_2fa():
    """True when the global 'Enforce Two-Factor Authentication' toggle is ON."""
    try:
        from models import SystemConfig
        cfg = SystemConfig.query.filter_by(key='enforce_2fa').first()
        return bool(cfg and cfg.value == 'true')
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"Failed to read enforce_2fa setting: {e}")
        return False


def enforcement_active_for(user, *, provider=None):
    """Whether 2FA is *mandated* for this user, ignoring current enrolment state.

    Local accounts are gated by the global toggle; SSO accounts by their
    provider's own toggle. Exempt users are never subject to enforcement. Used
    both by :func:`must_enroll_2fa` and by the self-disable guard.
    """
    if user is None:
        return False
    if getattr(user, 'totp_exempt', False):
        return False
    if (getattr(user, 'auth_source', 'local') or 'local') == 'local':
        return global_enforce_2fa()
    prov = provider if provider is not None else getattr(user, 'sso_provider', None)
    return bool(prov is not None and getattr(prov, 'enforce_2fa', False))


def has_security_key(user, *, excluding=None):
    """Whether ``user`` keeps an enabled WebAuthn key (other than ``excluding``)."""
    from models.webauthn import WebAuthnCredential
    query = WebAuthnCredential.query.filter_by(user_id=user.id, enabled=True)
    if excluding is not None:
        query = query.filter(WebAuthnCredential.id != excluding)
    return query.first() is not None


def would_leave_no_second_factor(user, *, dropping_totp=False, dropping_key=None):
    """True when enforced 2FA would be left with neither TOTP nor an enabled key."""
    if not enforcement_active_for(user):
        return False
    totp_left = bool(getattr(user, 'totp_confirmed', False)) and not dropping_totp
    return not totp_left and not has_security_key(user, excluding=dropping_key)


def must_enroll_2fa(user, *, auth_method='password', provider=None):
    """Whether this login gets a restricted session until a second factor is enrolled.

    Enrolled means confirmed TOTP or an enabled security key. Only password logins
    are later challenged for that factor; SSO and LDAP logins get this enrolment
    gate alone. False for exempt users and for mTLS/WebAuthn logins.
    """
    if getattr(user, 'totp_confirmed', False) or has_security_key(user):
        return False
    if auth_method in _EXEMPT_AUTH_METHODS:
        return False
    return enforcement_active_for(user, provider=provider)
