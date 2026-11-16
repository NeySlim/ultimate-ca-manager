"""A trust store entry holds certificates only (RFC 5914 §2, RFC 5280 §6.1.1(d)): never a private key.

Writes store the certificates re-serialized; reads and exports keep the CERTIFICATE blocks of the
stored text and nothing else, whatever an older version or a direct write left around them.
"""
import re

from cryptography import x509
from cryptography.hazmat.primitives import serialization

PRIVATE_KEY_REFUSAL = 'A trust store holds certificates only; remove the private key'
REMOVED_KEY = 'truststore_private_keys_removed'
REMOVED_ACTION = 'truststore_private_key_removed'

# Any armour label ending in PRIVATE KEY: PKCS#8, encrypted PKCS#8, RSA, EC, DSA, OpenSSH
_PRIVATE_KEY = re.compile(rb'-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----')
# A block body is base64 and whitespace only, so no other armour can hide inside one
_CERTIFICATE_BLOCK = re.compile(rb'-----BEGIN CERTIFICATE-----[A-Za-z0-9+/=\s]*?-----END CERTIFICATE-----(?:\r?\n)?')


class PrivateKeyInEntry(ValueError):
    """The entry offered to the trust store carries a private key."""

    def __init__(self):
        super().__init__(PRIVATE_KEY_REFUSAL)


def _bytes(data):
    return data.encode('utf-8', errors='replace') if isinstance(data, str) else bytes(data or b'')


def holds_private_key(data) -> bool:
    return _PRIVATE_KEY.search(_bytes(data)) is not None


def certificate_blocks(data) -> bytes:
    """The CERTIFICATE blocks of *data*, as stored and in order; empty when there is none."""
    return b''.join(m.group(0) for m in _CERTIFICATE_BLOCK.finditer(_bytes(data)))


def canonical_certificates(data):
    """``(PEM text, certificates)`` for an entry offered to the store, re-serialized from the parsed objects.

    Raises PrivateKeyInEntry when it carries a private key, ValueError when a block is not a certificate.
    """
    if holds_private_key(data):
        raise PrivateKeyInEntry()
    certs = x509.load_pem_x509_certificates(_bytes(data))
    pem = b''.join(c.public_bytes(serialization.Encoding.PEM) for c in certs)
    return pem.decode('ascii'), certs


def stored_without_key(text):
    """``(text to store, whether a private key was removed)`` for a row read from a database or an archive.

    A row without a private key is kept as it is; one with a key keeps only its certificate blocks.
    """
    if not text or not holds_private_key(text):
        return text, False
    return certificate_blocks(text).decode('ascii'), True


def first_fingerprint(text):
    """SHA-256 of the first certificate of *text*, or None when it cannot be read."""
    from cryptography.hazmat.primitives import hashes
    try:
        cert = x509.load_pem_x509_certificate(certificate_blocks(text))
        return cert.fingerprint(hashes.SHA256()).hex()
    except Exception:
        return None


def removal_warning(entry_id, name, fingerprint):
    """The log line and audit detail for one entry a private key was removed from; never the key."""
    return (f'Trust store entry {entry_id} "{name}" (SHA-256 {fingerprint or "unknown"}) held a private key, '
            'removed: it was readable by every account allowed to read the trust store and by every '
            'backup; replace that key')


def report_removed_keys(app) -> int:
    """At start: one audit entry and one WARNING per entry the upgrade removed a private key from, once.

    The list is deleted in the transaction of the first entry: a node that finds it gone reports nothing."""
    import json
    import logging
    from models import db, SystemConfig
    from services.audit_service import AuditService
    with app.app_context():
        row = SystemConfig.query.filter_by(key=REMOVED_KEY).first()
        if row is None:
            return 0
        try:
            entries = [e for e in json.loads(row.value or '[]') if isinstance(e, dict)]
        except ValueError:
            entries = []
        if not db.session.execute(db.delete(SystemConfig).where(SystemConfig.key == REMOVED_KEY)).rowcount:
            db.session.rollback()
            return 0
        if not entries:
            db.session.commit()
            return 0
        for entry in entries:
            text = removal_warning(entry.get('id'), entry.get('name'), entry.get('fingerprint_sha256'))
            logging.getLogger(__name__).warning("%s", text)
            AuditService.log_action(action=REMOVED_ACTION, resource_type='truststore', resource_id=entry.get('id'),
                                    resource_name=entry.get('name'), details=text, success=True, username='system')
        return len(entries)
