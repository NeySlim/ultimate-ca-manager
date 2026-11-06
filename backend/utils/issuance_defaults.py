"""Algorithms of the issuance paths where nobody picks one (#397).

The template bound to the path decides first; without one, the issuing CA's
key; the issuance policies then bound the result. One rule for EST, SCEP,
WSTEP, Sign CSR, renewals and the keys UCM generates for a requester.
"""
from __future__ import annotations

from cryptography.hazmat.primitives.asymmetric import ec

from utils import key_algorithms
from utils.ca_profile import default_digest_for_key_type


def _public(key):
    try:
        return key.public_key()
    except (AttributeError, TypeError):
        return key


def _algorithm_digest(alg) -> str | None:
    if not alg.needs_digest:
        return None
    return default_digest_for_key_type(alg.curve_names[0]) if alg.curve_names else 'sha256'


def digest_for_key(key) -> str | None:
    """Digest matching *key* (public or private): the curve's for EC (P-384 SHA-384,
    P-521 SHA-512, CA/Browser Forum BR 7.1.3.2.2), SHA-256 for RSA, None when it takes none."""
    public = _public(key)
    if not key_algorithms.needs_digest(public):
        return None
    if isinstance(public, ec.EllipticCurvePublicKey):
        return default_digest_for_key_type(public.curve.name)
    return 'sha256'


def digest_for_label(label) -> str | None:
    """``digest_for_key`` for a key type label ('EC-P384'); SHA-256 when unknown."""
    alg = key_algorithms.get(label)
    return _algorithm_digest(alg) if alg else 'sha256'


def template_digest(template, ca_key) -> str | None:
    """The digest of the template bound to a protocol path, a choice the policies check;
    None when it is weaker than the CA key's (a seeded SHA-256 must not lower a P-384 CA)."""
    from services.policy_service import POLICY_DIGESTS, normalize_digest
    chosen = normalize_digest(getattr(template, 'digest', None)) if template is not None else None
    floor = digest_for_key(ca_key) if chosen else None
    if floor is None or floor not in POLICY_DIGESTS:
        return chosen
    return chosen if POLICY_DIGESTS.index(chosen) >= POLICY_DIGESTS.index(floor) else None
