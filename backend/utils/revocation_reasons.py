"""RFC 5280 §5.3.1 CRLReason names accepted by the revocation APIs (#334).

The revoke routes used to store whatever string the client sent, and the
web UI never sent one, so every manual revocation was recorded as
``unspecified``. The names below are the canonical spellings UCM stores;
the CRL and OCSP builders map them to ``x509.ReasonFlags``.
``removeFromCRL`` is deliberately absent: it is written by the unhold path
only (RFC 5280 §5.3.1, delta CRLs), never by a revocation request.
"""
from typing import Optional

REVOCATION_REASONS = (
    'unspecified',
    'keyCompromise',
    'cACompromise',
    'affiliationChanged',
    'superseded',
    'cessationOfOperation',
    'certificateHold',
    'privilegeWithdrawn',
    'aACompromise',
)

# Case-insensitive lookup, plus the snake_case spellings older clients and
# the OCSP mapping already understand.
_CANONICAL = {name.lower(): name for name in REVOCATION_REASONS}
_CANONICAL.update({
    'key_compromise': 'keyCompromise',
    'ca_compromise': 'cACompromise',
    'affiliation_changed': 'affiliationChanged',
    'cessation_of_operation': 'cessationOfOperation',
    'certificate_hold': 'certificateHold',
    'privilege_withdrawn': 'privilegeWithdrawn',
    'aa_compromise': 'aACompromise',
})


def normalize_revocation_reason(value) -> Optional[str]:
    """Canonical reason name for *value*, ``'unspecified'`` when absent,
    ``None`` when the value is not a known reason."""
    if value is None:
        return 'unspecified'
    if not isinstance(value, str):
        return None
    key = value.strip().lower()
    if not key:
        return 'unspecified'
    return _CANONICAL.get(key)


def invalid_reason_message(value) -> str:
    return (
        f"Invalid revocation reason {value!r}; accepted values: "
        + ', '.join(REVOCATION_REASONS)
    )
