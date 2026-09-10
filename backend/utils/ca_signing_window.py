"""The issuing CA's own validity window, checked the same way on every
issuance path.

A CA certificate can only vouch for a leaf between its own notBefore and
notAfter, and no leaf may outlive it (RFC 5280 §6.1: path validation checks
every certificate's validity at the time of use, so a leaf signed by an
expired or not-yet-valid CA, or one that outlives it, fails as soon as the CA
does). Each builder used to reimplement or skip part of this: the shared
CSR-signing trunk clamped nothing, the mTLS path turned an expired CA into
the issuer of a one-day certificate, and no path compared notBefore with now.

Project convention: naive datetimes are UTC (``utils.datetime_utils``).
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from cryptography import x509

from utils.datetime_utils import utc_now


class IssuerWindowError(ValueError):
    """The CA certificate cannot sign at this moment."""


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def issuer_window(ca_cert: x509.Certificate) -> Tuple[datetime, datetime]:
    """``(not_before, not_after)`` of the CA certificate, naive UTC."""
    return (
        _naive_utc(ca_cert.not_valid_before_utc),
        _naive_utc(ca_cert.not_valid_after_utc),
    )


def check_issuer_window(ca_cert: x509.Certificate, now: Optional[datetime] = None) -> None:
    """Raise :class:`IssuerWindowError` unless ``now`` falls inside the CA
    certificate's validity window."""
    moment = _naive_utc(now) if now is not None else utc_now()
    not_before, not_after = issuer_window(ca_cert)
    if moment < not_before:
        raise IssuerWindowError(
            f'Issuing CA certificate is not yet valid (valid from {not_before.isoformat()}Z)'
        )
    if moment >= not_after:
        raise IssuerWindowError(
            f'Issuing CA certificate has expired (expired {not_after.isoformat()}Z)'
        )


def clamp_not_after(not_after: datetime, ca_cert: x509.Certificate) -> datetime:
    """The requested leaf expiry, never later than the CA certificate's own.

    Returns a naive UTC datetime whatever the input's awareness."""
    return min(_naive_utc(not_after), issuer_window(ca_cert)[1])
