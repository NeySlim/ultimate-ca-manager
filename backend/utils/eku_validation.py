"""
Extended Key Usage (EKU) OID validation and helpers.

RFC 5280 §4.2.1.12 — ExtKeyUsageSyntax ::= SEQUENCE SIZE (1..MAX) OF KeyPurposeId
                     KeyPurposeId      ::= OBJECT IDENTIFIER

Any well-formed dotted OID is valid. We additionally:
  - cap the count to prevent oversized certificates
  - cap each OID length to prevent DoS via huge strings
  - reject the wildcard anyExtendedKeyUsage OID by default (defeats the purpose)
"""
import re
from typing import List, Optional, Tuple

from cryptography import x509

# Re-export for the API/UI
from utils.cert_extensions import EKU_NAMES  # noqa: F401

# Validation limits
MAX_EKU_COUNT = 16
MAX_OID_LENGTH = 64

# RFC 5510 / X.660: first arc is 0, 1, or 2; second arc 0..39 for arcs 0/1
# We accept any dotted OID with ≥2 arcs and no leading zeros.
OID_REGEX = re.compile(r'^[0-2](?:\.(?:0|[1-9]\d*)){1,15}$')

# Wildcard OID — RFC 5280 says using this defeats the purpose of EKU
ANY_EXTENDED_KEY_USAGE = '2.5.29.37.0'


class EKUValidationError(ValueError):
    """Raised when an EKU OID list fails validation."""


def validate_oid(oid: str) -> Optional[str]:
    """
    Validate a single OID string.
    Returns an error message, or None if valid.
    """
    if not isinstance(oid, str):
        return 'OID must be a string'
    oid = oid.strip()
    if not oid:
        return 'OID is empty'
    if len(oid) > MAX_OID_LENGTH:
        return f'OID too long (max {MAX_OID_LENGTH} chars)'
    if not OID_REGEX.match(oid):
        return f'Invalid OID format: {oid}'
    if oid == ANY_EXTENDED_KEY_USAGE:
        return 'anyExtendedKeyUsage (2.5.29.37.0) is not allowed; specify concrete EKUs instead'
    return None


def normalize_extra_ekus(items) -> Tuple[List[str], Optional[str]]:
    """
    Normalize and validate a list of EKU entries.
    Each entry may be a dotted OID (e.g. '1.3.6.1.4.1.311.54.1.2') or a
    well-known short name (e.g. 'msRemoteDesktop' → resolves via EKU_NAMES).

    Returns:
        (oids, error_message)
        oids: deduplicated list of dotted OID strings (empty if items is None/empty)
        error_message: None if valid, otherwise a user-facing error
    """
    if items is None:
        return [], None
    if not isinstance(items, list):
        return [], 'extra_ekus must be a list'
    if len(items) > MAX_EKU_COUNT:
        return [], f'Too many EKUs (max {MAX_EKU_COUNT})'

    # Build reverse name → oid lookup (case-insensitive)
    name_to_oid = {name.lower(): oid for oid, name in EKU_NAMES.items()}

    seen = set()
    out = []
    for raw in items:
        if not isinstance(raw, str):
            return [], 'each EKU entry must be a string'
        candidate = raw.strip()
        if not candidate:
            continue
        # Resolve well-known names to OIDs
        if not OID_REGEX.match(candidate):
            mapped = name_to_oid.get(candidate.lower())
            if mapped:
                candidate = mapped
        err = validate_oid(candidate)
        if err:
            return [], err
        if candidate not in seen:
            seen.add(candidate)
            out.append(candidate)
    return out, None


def to_object_identifiers(oids: List[str]) -> List[x509.ObjectIdentifier]:
    """Convert a list of dotted OID strings to x509.ObjectIdentifier instances."""
    return [x509.ObjectIdentifier(oid) for oid in oids]


def merge_eku_lists(
    base_oids: List[x509.ObjectIdentifier],
    extra_oids: List[x509.ObjectIdentifier],
) -> List[x509.ObjectIdentifier]:
    """Merge two ObjectIdentifier lists, preserving order and deduplicating."""
    seen = set()
    out = []
    for oid in list(base_oids) + list(extra_oids):
        key = oid.dotted_string
        if key not in seen:
            seen.add(key)
            out.append(oid)
    return out
