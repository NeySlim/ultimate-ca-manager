"""2FA enforcement policy (#141).

Centralises the decision "must this user enrol TOTP before getting a full
session?" so the login flows, the require_auth gate, and the disable guard all
agree. Local accounts are gated by the global ``enforce_2fa`` setting; SSO
accounts by their provider's own ``enforce_2fa`` toggle (independent switches).
"""
import logging

logger = logging.getLogger(__name__)

# Session flag marking a partially-authenticated session that may only reach the
# 2FA enrolment endpoints until TOTP is confirmed.
ENROLL_SESSION_KEY = 'must_enroll_2fa'

# Exact request paths reachable while in the forced-enrolment state. Everything
# else returns 403 until the user confirms TOTP (or logs out).
ENROLL_ALLOWED_PATHS = frozenset({
    '/api/v2/account/2fa/enable',
    '/api/v2/account/2fa/confirm',
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


def must_enroll_2fa(user, *, auth_method='password', provider=None):
    """Whether ``user`` must enrol TOTP before receiving a full session.

    Returns False for users already enrolled, explicitly exempt, or logging in
    via a strong second factor (mTLS/WebAuthn).
    """
    if getattr(user, 'totp_confirmed', False):
        return False
    if auth_method in _EXEMPT_AUTH_METHODS:
        return False
    return enforcement_active_for(user, provider=provider)
