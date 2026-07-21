"""ACME Renewal Information (ARI) — RFC 9773.

Implements the server side of the ``renewalInfo`` resource: given a
certificate identifier built from the cert's AuthorityKeyIdentifier and
serial number, return a ``suggestedWindow`` telling the client when to
renew. This lets ACME clients spread renewals over time and react quickly
when a certificate has been revoked.

The endpoint is unauthenticated (a plain GET, per RFC 9773 §4.1) — anyone
who already knows a certificate's AKI + serial learns only its renewal
window, which is not sensitive.
"""
from __future__ import annotations

import base64
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

from models import Certificate
from models.acme_models import AcmeOrder
from utils.datetime_utils import utc_now
from utils.serial_format import serial_to_int

# How often a client should re-poll the renewalInfo resource (RFC 9773 §4.2
# recommends advertising this via Retry-After).
RETRY_AFTER_SECONDS = 6 * 3600

# Fallback renewal lead time when no auto-renewal policy is configured.
_DEFAULT_RENEW_BEFORE_DAYS = 30


def _b64url_decode(segment: str) -> bytes:
    """Decode a canonical unpadded base64url segment."""
    if not re.fullmatch(r'[A-Za-z0-9_-]+', segment):
        raise ValueError('Invalid base64url segment')
    pad = '=' * (-len(segment) % 4)
    decoded = base64.urlsafe_b64decode(segment + pad)
    canonical = base64.urlsafe_b64encode(decoded).rstrip(b'=').decode('ascii')
    if canonical != segment:
        raise ValueError('Non-canonical base64url segment')
    return decoded


def parse_certid(certid: str) -> Optional[Tuple[str, int]]:
    """Parse an ARI CertID into ``(aki_hex, serial_int)``.

    The CertID is ``base64url(AKI keyIdentifier) "." base64url(serial)``
    (RFC 9773 §4.1). Returns ``None`` if the value is malformed.
    """
    if not certid or certid.count('.') != 1:
        return None
    aki_part, serial_part = certid.split('.', 1)
    if not aki_part or not serial_part:
        return None
    try:
        aki_bytes = _b64url_decode(aki_part)
        serial_bytes = _b64url_decode(serial_part)
    except (ValueError, base64.binascii.Error):
        return None
    if not aki_bytes or not serial_bytes:
        return None
    aki_hex = aki_bytes.hex().lower()
    serial_int = int.from_bytes(serial_bytes, 'big')
    return aki_hex, serial_int


def _aki_matches(stored_aki: Optional[str], wanted_hex: str) -> bool:
    if not stored_aki:
        return False
    return stored_aki.replace(':', '').lower() == wanted_hex


def find_certificate(aki_hex: str, serial_int: int) -> Optional[Certificate]:
    """Locate an issued certificate by AKI + serial.

    Serial numbers are stored inconsistently (decimal or hex) across the
    DB's history, so we match on the integer value and confirm the AKI to
    avoid cross-CA collisions.
    """
    candidates = {
        str(serial_int),
        format(serial_int, 'x'),
        format(serial_int, 'X'),
    }
    rows = (Certificate.query
            .filter(Certificate.crt.isnot(None))
            .filter(Certificate.serial_number.in_(candidates))
            .all())
    for cert in rows:
        if serial_to_int(cert.serial_number) == serial_int and _aki_matches(cert.aki, aki_hex):
            return cert
    return None


def has_valid_replacement(certid: str) -> bool:
    """Return whether a completed ACME order replaced ``certid``."""
    return AcmeOrder.query.filter_by(
        replaces=certid,
        status='valid',
    ).first() is not None


def suggested_window(
    cert: Certificate,
    renew_before_days: Optional[int] = None,
    *,
    replaced: bool = False,
) -> Tuple[datetime, datetime]:
    """Compute the ARI suggested renewal window for a certificate.

    Centered on ``notAfter - renew_before``, where ``renew_before`` follows
    the configured auto-renewal lead time but is never earlier than one
    third into the certificate's lifetime (so freshly issued certs are not
    told to renew immediately). Revoked certificates get a window in the
    past so compliant clients renew right away (RFC 9773 §4.2).
    """
    now = utc_now()
    not_before = cert.valid_from
    not_after = cert.valid_to

    if replaced or cert.revoked or not_after is None or not_before is None:
        return now - timedelta(hours=1), now

    # Normalize to naive/aware consistently with utc_now (naive UTC in UCM).
    lifetime = not_after - not_before
    if lifetime <= timedelta(0):
        return now - timedelta(hours=1), now

    days = renew_before_days if renew_before_days is not None else _DEFAULT_RENEW_BEFORE_DAYS
    renew_before = timedelta(days=max(1, days))
    # Never schedule renewal before 1/3 of the lifetime has elapsed.
    renew_before = min(renew_before, lifetime / 3)

    center = not_after - renew_before
    half = max(timedelta(hours=12), lifetime * 0.02)
    start = center - half
    end = min(center + half, not_after)
    if end <= start:
        end = start + timedelta(hours=1)
    return start, end


def _rfc3339(dt: datetime) -> str:
    # UCM stores naive UTC datetimes; emit an explicit Z offset.
    return dt.replace(microsecond=0).isoformat() + 'Z'


def build_renewal_info(
    cert: Certificate,
    renew_before_days: Optional[int] = None,
    *,
    replaced: bool = False,
) -> dict:
    """Build the RFC 9773 RenewalInfo JSON object for a certificate."""
    start, end = suggested_window(
        cert, renew_before_days, replaced=replaced
    )
    return {
        'suggestedWindow': {
            'start': _rfc3339(start),
            'end': _rfc3339(end),
        },
    }
