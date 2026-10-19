"""RFC 5280 §5.3.1 CRLReason names accepted by the revocation APIs (#334).

The revoke routes used to store whatever string the client sent, and the
web UI never sent one, so every manual revocation was recorded as
``unspecified``. The names below are the canonical spellings UCM stores;
the CRL and OCSP builders map them to ``x509.ReasonFlags``.
``removeFromCRL`` is deliberately absent: it is written by the unhold path
only (RFC 5280 §5.3.1, delta CRLs), never by a revocation request.
"""
from typing import Optional

from cryptography import x509

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


# The CRL builder and the OCSP responder both turn a stored `revoke_reason`
# into an `x509.ReasonFlags`, and each carried its own table. They drifted on
# the one spelling that matters: `normalize_revocation_reason` stores
# `cACompromise`, the CRL table knew it and the responder's did not, so one
# certificate was a CA compromise on the CRL and `unspecified` over OCSP.
# One table, next to the vocabulary it spells, so they cannot drift again.
# It covers every alias the two tables held between them; the callers keep
# whatever rule of their own applies (a responder has no delta CRL, so it
# drops `removeFromCRL` — RFC 5280 §5.3.1).
REASON_FLAGS = {
    'unspecified': x509.ReasonFlags.unspecified,
    'keyCompromise': x509.ReasonFlags.key_compromise,
    'key_compromise': x509.ReasonFlags.key_compromise,
    'cACompromise': x509.ReasonFlags.ca_compromise,
    'caCompromise': x509.ReasonFlags.ca_compromise,
    'CACompromise': x509.ReasonFlags.ca_compromise,
    'ca_compromise': x509.ReasonFlags.ca_compromise,
    'affiliationChanged': x509.ReasonFlags.affiliation_changed,
    'affiliation_changed': x509.ReasonFlags.affiliation_changed,
    'superseded': x509.ReasonFlags.superseded,
    'cessationOfOperation': x509.ReasonFlags.cessation_of_operation,
    'cessation_of_operation': x509.ReasonFlags.cessation_of_operation,
    'certificateHold': x509.ReasonFlags.certificate_hold,
    'certificate_hold': x509.ReasonFlags.certificate_hold,
    'removeFromCRL': x509.ReasonFlags.remove_from_crl,
    'privilegeWithdrawn': x509.ReasonFlags.privilege_withdrawn,
    'privilege_withdrawn': x509.ReasonFlags.privilege_withdrawn,
    'aACompromise': x509.ReasonFlags.aa_compromise,
    'aa_compromise': x509.ReasonFlags.aa_compromise,
}


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


# RFC 5280 §5.3.1 CRLReason codes (7 is unused)
REASON_CODES = {
    x509.ReasonFlags.unspecified: 0,
    x509.ReasonFlags.key_compromise: 1,
    x509.ReasonFlags.ca_compromise: 2,
    x509.ReasonFlags.affiliation_changed: 3,
    x509.ReasonFlags.superseded: 4,
    x509.ReasonFlags.cessation_of_operation: 5,
    x509.ReasonFlags.certificate_hold: 6,
    x509.ReasonFlags.remove_from_crl: 8,
    x509.ReasonFlags.privilege_withdrawn: 9,
    x509.ReasonFlags.aa_compromise: 10,
}
