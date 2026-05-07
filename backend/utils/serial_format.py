"""
Serial number format helpers.

UCM stores certificate serial numbers in two formats depending on the layer:

- **Database (Certificate.serial_number)**: decimal string
  (e.g. ``"182716277442602097566978062183857154669354824224"``).
- **OCSP cache (OCSPResponse.cert_serial)**: lowercase hexadecimal string
  without ``0x`` prefix (e.g. ``"2008b...e0"``), matching ``format(int, 'x')``.

This helper converts between the two so cache invalidation on revoke does
not silently fail (RFC 6960 §2.2 — a revoked certificate MUST stop being
reported as ``good`` immediately).
"""
from __future__ import annotations


def serial_to_hex(serial: str | int | None) -> str:
    """Return the lowercase hex form of a certificate serial.

    Accepts decimal strings (DB format), hex strings (already-converted), or
    integers. Returns an empty string for falsy inputs. Never raises.
    """
    if serial is None or serial == '':
        return ''
    if isinstance(serial, int):
        return format(serial, 'x')
    s = str(serial).strip()
    # Already hex?
    if s.lower().startswith('0x'):
        s = s[2:]
    # Try decimal first (DB canonical form)
    try:
        return format(int(s, 10), 'x')
    except ValueError:
        pass
    # Fall back to hex parsing
    try:
        return format(int(s, 16), 'x')
    except ValueError:
        return s.lower()
