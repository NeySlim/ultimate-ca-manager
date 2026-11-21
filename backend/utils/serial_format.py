"""
Serial number format helpers.

UCM stores certificate serial numbers in these forms:

- **certificates.serial_number and revoked_serials.serial_number**: the decimal
  string of the integer (``"182716277442602097566978062183857154669354824224"``),
  written only through ``canonical_serial`` (a model validator enforces it), so the
  unique (caref, serial_number) index sees one spelling per serial (upgrade step 144).
- **est_signer_certs.serial_number**: a copy of its certificate row's serial, compared
  to it by string equality, so the same decimal ``str(int)``.
- **OCSP cache (OCSPResponse.cert_serial)**: lowercase hexadecimal string
  without ``0x`` prefix (e.g. ``"2008b...e0"``), matching ``format(int, 'x')``.
- Tables never joined to certificates by string equality keep their own form
  (auth_certificates, trusted_certificates, discovered_certificates,
  ca_cross_certificates, certificate_authorities); ``serial_variants`` reads them.

The API keeps returning the stored string; the UI renders it as colon hex.
"""
from __future__ import annotations

import base64
import re

_DECIMAL = re.compile(r'-?[0-9]+')
_HEX = re.compile(r'[0-9a-fA-F]+')


def canonical_serial(value: str | int | None) -> str | None:
    """The one stored form of a serial: the decimal string of its integer.

    An int is exact. Text is hexadecimal when it says so (``0x``, colons, or a
    letter a-f) and decimal otherwise; an all-digit hex spelling is therefore
    ambiguous and writers pass the integer. Unreadable text comes back unchanged.
    """
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value)
    raw = str(value).strip()
    if not raw:
        return raw
    s = raw.replace(':', '').replace(' ', '')
    marked = s[:2].lower() == '0x' or ':' in raw
    if marked:
        s = s[2:] if s[:2].lower() == '0x' else s
    if not marked and _DECIMAL.fullmatch(s):
        return str(int(s, 10))
    if s and _HEX.fullmatch(s):
        return str(int(s, 16))
    return raw


def serial_readings(value: str | int | None) -> set[int]:
    """Every integer *value* may spell: its decimal and its hexadecimal reading."""
    if value is None or isinstance(value, bool):
        return set()
    if isinstance(value, int):
        return {value}
    s = str(value).strip().replace(':', '').replace(' ', '')
    if s[:2].lower() == '0x':
        s = s[2:]
    found = set()
    for base in (10, 16):
        try:
            found.add(int(s, base))
        except ValueError:
            continue
    return found


def serial_search_forms(text: str | None) -> list[str]:
    """Stored forms of every serial *text* may name in full (decimal, hex, colon hex)."""
    return sorted(str(n) for n in serial_readings(text) if n >= 0)


def certificate_serial(crt) -> int | None:
    """The serial of a stored certificate (base64 of PEM, PEM or DER), or None."""
    if not crt:
        return None
    from cryptography import x509
    data = crt.encode() if isinstance(crt, str) else bytes(crt)
    try:
        if b'-----BEGIN' not in data:
            data = base64.b64decode(data, validate=False)
        if b'-----BEGIN' in data:
            return x509.load_pem_x509_certificate(data).serial_number
        return x509.load_der_x509_certificate(data).serial_number
    except Exception:
        return None


def canonical_stored_serial(stored: str | int | None, crt=None) -> str | None:
    """``canonical_serial`` of a stored value, settled by the row's certificate when
    one of the value's readings is that certificate's serial (never reinterpreted otherwise)."""
    readings = serial_readings(stored)
    # Text with one reading needs no certificate: only digits read in both bases
    actual = certificate_serial(crt) if len(readings) > 1 else None
    if actual is not None and actual in readings:
        return str(actual)
    return canonical_serial(stored)


# Its step 144 stores every serial in decimal; a fresh 3.0 install records it when created
CANONICAL_MIGRATION = '300_upgrade_from_2_254'


def recorded_before_canonical(recorded_at) -> bool:
    """True when *recorded_at* (naive UTC) precedes the decimal serials on this database, or
    when either date is unknown: the hex reading of digits is then still allowed."""
    if recorded_at is None:
        return True
    from datetime import datetime
    from sqlalchemy import text
    from models import db
    # `_migrations.applied_at` is naive UTC on both backends (migration_runner writes it so, and a
    # backend switch copies it as is); a row written before that on PostgreSQL holds session time.
    try:
        with db.session.begin_nested():
            applied = db.session.execute(text("SELECT applied_at FROM _migrations WHERE name = :n"),
                                         {'n': CANONICAL_MIGRATION}).scalar()
    except Exception:
        return True
    if applied is None:
        return True
    try:
        if not isinstance(applied, datetime):
            applied = datetime.fromisoformat(str(applied))
        return recorded_at < applied.replace(tzinfo=None)
    except (TypeError, ValueError):
        return True


def names_certificate(recorded: str | int | None, cert, recorded_at=None) -> bool:
    """True when *recorded* is the serial of *cert*, whose column is canonical. Its decimal
    reading decides; the certificate settles an all-digit hex spelling only for a value
    recorded before the upgrade step 144, when every writer still stored the row's own spelling."""
    if canonical_serial(recorded) == cert.serial_number:
        return True
    if not recorded_before_canonical(recorded_at):
        return False
    return canonical_stored_serial(recorded, getattr(cert, 'crt', None)) == cert.serial_number


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


def serial_variants(serial: int) -> set[str]:
    """String forms a serial may take in a table that is not canonicalised.

    Only for columns outside certificates/revoked_serials (see module docstring).
    """
    return {str(serial), format(serial, 'x'), format(serial, 'X')}


def format_serial_colon(serial: str | int | None) -> str:
    """Return serial as colon-separated uppercase hex pairs (OpenSSL display style)."""
    if serial is None or serial == '':
        return ''
    n = serial_to_int(serial)
    if n is not None:
        hex_str = format(n, 'X')
    else:
        hex_str = str(serial).replace(':', '').upper()
    if len(hex_str) % 2:
        hex_str = '0' + hex_str
    return ':'.join(hex_str[i:i + 2] for i in range(0, len(hex_str), 2))


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
