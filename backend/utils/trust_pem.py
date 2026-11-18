"""A trust store entry holds certificates only (RFC 5914 §2): never a private key.

Writes store the certificates re-serialized; reads, exports and backups hand out the certificate
blocks of the stored text and nothing else, whatever an older version stored around them.
"""
import logging
import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

PRIVATE_KEY_REFUSAL = 'A trust store holds certificates only; remove the private key'
REMOVED_ACTION = 'truststore_private_key_removed'

# Any armour label ending in PRIVATE KEY: PKCS#8, encrypted PKCS#8, RSA, EC, DSA, OpenSSH
_PRIVATE_KEY = re.compile(rb'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----')
# A block body is base64 and whitespace only, so no other armour can hide inside one; the legacy
# `X509 CERTIFICATE` label is read, never handed out (RFC 7468 §5.1)
_CERTIFICATE_BLOCK = re.compile(rb'-----BEGIN (?P<label>(?:X509 )?CERTIFICATE)-----[A-Za-z0-9+/=\s]*?'
                                rb'-----END (?P=label)-----(?:\r?\n)?')
# The opening line alone: a block cryptography loads may carry RFC 1421 headers the pattern above refuses
_CERTIFICATE_OPENING = re.compile(rb'-----BEGIN (?:X509 )?CERTIFICATE-----')


class PrivateKeyInEntry(ValueError):
    """The entry offered to the trust store carries a private key."""

    def __init__(self):
        super().__init__(PRIVATE_KEY_REFUSAL)


def _bytes(data):
    return data.encode('utf-8', errors='replace') if isinstance(data, str) else bytes(data or b'')


def holds_private_key(data) -> bool:
    return _PRIVATE_KEY.search(_bytes(data)) is not None


def is_der_certificate(data) -> bool:
    """Whether *data* is one DER certificate: an armour line inside one of its fields is signed public data."""
    try:
        x509.load_der_x509_certificate(_bytes(data))
    except Exception:
        return False
    return True


def opens_a_pem_certificate(data) -> bool:
    """Whether *data* is offered as PEM certificates, readable or not: what an upload must not read as DER."""
    return _CERTIFICATE_OPENING.search(_bytes(data)) is not None


def certificate_blocks(data) -> bytes:
    """The certificate blocks of *data*, in order and under the `CERTIFICATE` label; empty when there is none."""
    return b''.join(m.group(0) if m.group('label') == b'CERTIFICATE'
                    else m.group(0).replace(b'X509 CERTIFICATE', b'CERTIFICATE')
                    for m in _CERTIFICATE_BLOCK.finditer(_bytes(data)))


def canonical_certificates(data):
    """``(PEM text, certificates)`` for an entry offered to the store, re-serialized from the parsed objects.

    Raises PrivateKeyInEntry when it carries a private key, ValueError when a block is not a certificate
    or is left open: a chain cut short is refused whole.
    """
    if holds_private_key(data):
        raise PrivateKeyInEntry()
    certs = x509.load_pem_x509_certificates(_bytes(data))
    if len(_CERTIFICATE_OPENING.findall(_bytes(data))) > len(certs):
        raise ValueError('a certificate block is left open')
    pem = b''.join(c.public_bytes(serialization.Encoding.PEM) for c in certs)
    return pem.decode('ascii'), certs


def served_certificates(stored) -> str:
    """What any read hands out of a stored entry: its certificate blocks, or '' when it has none.

    The blocks are taken as they are only when the pattern matched every opening line; a row where some
    carry RFC 1421 headers is handed out as the certificates cryptography reads in it, or its blocks if none."""
    data = _bytes(stored)
    blocks = certificate_blocks(data)
    if len(_CERTIFICATE_BLOCK.findall(data)) == len(_CERTIFICATE_OPENING.findall(data)):
        return blocks.decode('ascii')
    try:
        certs = x509.load_pem_x509_certificates(data)
    except Exception:
        return blocks.decode('ascii')
    return b''.join(c.public_bytes(serialization.Encoding.PEM) for c in certs).decode('ascii')


def stored_without_key(stored):
    """``(text to store, whether a private key was removed)`` for a row read from a database or an archive."""
    if not stored or not holds_private_key(stored):
        return stored, False
    return served_certificates(stored), True


def removal_warning(entry_id, name):
    """The log line and audit detail for one entry a private key was removed from; never the key."""
    return (f'Trust store entry {entry_id} "{name}" held a private key, removed: it was readable by every '
            'account allowed to read the trust store and by every backup that carried the entry; '
            'treat that key as compromised and replace it')


def strip_stored_private_keys() -> int:
    """Remove the private key from every trust store row that holds one; the row and its certificates stay.

    Run at start in an application context. Idempotent, and a row is written only while it still holds
    the text read, so two starts racing report it once. A row that cannot be read is left and named."""
    from models import db
    from models.truststore import TrustedCertificate
    from services.audit_service import AuditService
    table = TrustedCertificate.__table__
    rows = db.session.execute(db.select(table.c.id, table.c.name, table.c.certificate_pem)).all()
    db.session.rollback()
    removed = 0
    for row_id, name, stored in rows:
        try:
            if stored is not None and not isinstance(stored, str):
                raise TypeError('not text')
            if not stored or not holds_private_key(stored):
                continue
            kept = served_certificates(stored)
            written = db.session.execute(
                table.update().where(table.c.id == row_id, table.c.certificate_pem == stored)
                .values(certificate_pem=kept)).rowcount
            if written != 1:
                db.session.rollback()
                continue
            message = removal_warning(row_id, name)
            # The audit entry commits the update with it; a failed one rolls both back for the next start
            if AuditService.log_action(action=REMOVED_ACTION, resource_type='truststore', resource_id=row_id,
                                       resource_name=name, details=message, success=True,
                                       username='system') is None:
                continue
            logger.warning("%s", message)
            removed += 1
        except Exception as exc:
            db.session.rollback()
            logger.warning("Trust store entry %s could not be checked for a private key (%s): left as is, "
                           "its reads still hand out its certificates only", row_id, type(exc).__name__)
    return removed
