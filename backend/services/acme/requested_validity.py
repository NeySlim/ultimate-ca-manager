"""The validity an ACME order asks for (RFC 8555 §7.4 notBefore / notAfter).

The server issues exactly the requested dates or refuses: it "MUST NOT issue a
certificate with contents other than those requested". The profile's validity
is the longest window granted; the issuing CA's own window bounds it too.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

from utils.datetime_utils import CERT_NOT_BEFORE_SKEW, utc_now


class RequestedValidityError(ValueError):
    """The requested window cannot be issued as asked."""


def parse_order_time(value, field: str) -> Optional[datetime]:
    """An RFC 3339 date-time as naive UTC; None when absent."""
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise RequestedValidityError(f'{field} must be an RFC 3339 date-time')
    text = value[:-1] + '+00:00' if value[-1] in 'Zz' else value
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        raise RequestedValidityError(f'{field} must be an RFC 3339 date-time') from None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def window_error(not_before: Optional[datetime], not_after: Optional[datetime],
                 validity_days: int, *, now: Optional[datetime] = None,
                 ca_window: Optional[tuple] = None, at_order: bool = False) -> Optional[str]:
    """Why the window cannot be issued, or None. ``at_order`` adds the newOrder-only
    checks: a date already past, and a notBefore earlier than UCM's own backdating."""
    now = now or utc_now()
    if not_before and not_after and not_before >= not_after:
        return 'notBefore must be earlier than notAfter'
    if at_order:
        if not_after and not_after <= now:
            return 'notAfter is in the past'
        if not_before and not_before < now - CERT_NOT_BEFORE_SKEW:
            return 'notBefore is in the past'
    if not_after and not_after > (not_before or now) + timedelta(days=validity_days):
        return f'The requested validity exceeds the {validity_days} days this profile allows'
    if ca_window:
        ca_not_before, ca_not_after = ca_window
        if not_after and not_after > ca_not_after:
            return 'notAfter is later than the issuing CA certificate expires'
        if not_before and not_before < ca_not_before:
            return 'notBefore is earlier than the issuing CA certificate is valid'
    return None
