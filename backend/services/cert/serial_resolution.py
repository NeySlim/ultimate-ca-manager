"""The integer serial a stored record actually carries.

Since the upgrade step 144, ``Certificate.serial_number`` and ``RevokedSerial.serial_number``
hold the decimal string (``utils/serial_format.canonical_serial``); rows that
migration left pending, ``CA.serial_number`` and older archives may still hold
what the historical writers stored:

- decimal, ``str(n)`` — ``services/cert/mixins/lifecycle.py``, the import
  routes, ``api/wstep_protocol.py``, OPNsense and smart import;
- lowercase hex, ``format(n, 'x')`` — ``api/v2/certificates/cert_create.py``,
  ``services/cert/renewal.py``, ``api/v2/policies.py``;
- uppercase hex, ``format(n, 'X')`` — ``api/v2/msca.py``.

Read back, an all-digit column is ambiguous: ``"12345"`` is 12345 for the
first writer and 0x12345 = 74565 for the other two. ``serial_to_int`` answers
decimal first, so a hex writer's serial comes back as some other
certificate's — the CRL then published that other serial and left the revoked
one unlisted, while the OCSP responder, which settles the ambiguity against
the stored certificate, answered ``revoked`` for the real one. Two answers for
one certificate.

The stored certificate settles it: a record holding a PEM knows its own
serial, whatever its column says. Records holding none (``RevokedSerial``,
whose certificate is gone by design) keep the column reading, which is all
there is to read.

Deliberately *not* merged with ``services/ocsp_service._record_holds_serial``:
that one answers a different question (does this record hold *this* serial),
tri-state, and treats an unreadable certificate as "cannot say, accept the
match". Folding it onto this resolver would turn those into a rejection and
change what the responder answers for a row stored without its PEM.
"""

import base64
import logging
from typing import Optional

from cryptography import x509

from utils.serial_format import serial_to_int

logger = logging.getLogger(__name__)


def resolve_record_serial(record) -> Optional[int]:
    """The integer serial ``record`` carries, from its certificate when it
    holds one, else from its ``serial_number`` column.

    Returns ``None`` when neither can be read.
    """
    pem = getattr(record, 'crt', None)
    if pem:
        try:
            return x509.load_pem_x509_certificate(base64.b64decode(pem)).serial_number
        except Exception as e:
            logger.debug(
                "serial: unreadable certificate on %s id=%s (%s); "
                "falling back on the serial_number column",
                type(record).__name__, getattr(record, 'id', None), e,
            )
    return serial_to_int(getattr(record, 'serial_number', None))


def same_serial(left, right) -> bool:
    """Whether two records name the same serial.

    True when the columns are written identically — the historical test — and
    also when they resolve to the same integer, so a decimal row and a hex row
    for one certificate are recognised as one. Only ever finds *more* matches
    than comparing the columns, so a caller using this to drop duplicates
    never starts keeping an entry it used to drop.
    """
    left_column = getattr(left, 'serial_number', None)
    right_column = getattr(right, 'serial_number', None)
    if left_column is not None and left_column == right_column:
        return True
    left_int = resolve_record_serial(left)
    return left_int is not None and left_int == resolve_record_serial(right)
