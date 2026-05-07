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


def serial_to_int(serial: str | int | None) -> int | None:
    """Return the integer form of a certificate serial.

    Mirrors ``serial_to_hex`` (DB has historical hex/decimal mix). Returns
    ``None`` for falsy or unparseable inputs (caller decides how to handle).
    """
    if serial is None or serial == '':
        return None
    if isinstance(serial, int):
        return serial
    s = str(serial).replace(':', '').strip()
    if s.lower().startswith('0x'):
        s = s[2:]
    # Decimal first (canonical, recent code uses str(int))
    try:
        return int(s, 10)
    except ValueError:
        pass
    # Hex fallback (legacy rows; safe because hex strings of real serials
    # almost always contain a-f letters which fail int(s, 10) above)
    try:
        return int(s, 16)
    except ValueError:
        return None


def serial_to_hex(serial: str | int | None) -> str:
    """Return the lowercase hex form of a certificate serial.

    Accepts decimal strings (DB format), hex strings (already-converted), or
    integers. Returns an empty string for falsy inputs. Never raises.
    """
    if serial is None or serial == '':
        return ''
    if isinstance(serial, int):
        return format(serial, 'x')
    n = serial_to_int(serial)
    if n is None:
        return str(serial).lower()
    return format(n, 'x')
