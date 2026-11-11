"""Envelope encryption: data-encryption keys (DEK) in the database, wrapped by the KEK.

KEK = master.key or KEY_ENCRYPTION_KEY, the only secret to back up. A DEK row holds
"1:" + base64(nonce || AES-256-GCM(HKDF(KEK, 'ucm dek wrap v1'), DEK)), AAD = version and KEK id.
No row: the KEK material itself is DEK version 1, so an upgraded database reads as it is.
derive_key (audit chain) stays bound to the KEK: rotating the DEK leaves every seal verifiable.
"""
import base64
import hashlib
import logging

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from utils.randomness import csp_bytes

logger = logging.getLogger(__name__)

WRAP_FORMAT = '1'
ACTIVE, PREVIOUS, DISABLED = 'active', 'previous', 'disabled'
_WRAP_LABEL = b'ucm dek wrap v1'
_FINGERPRINT_LABEL = b'ucm kek fingerprint v1'


def _hkdf(kek: bytes, label: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=label).derive(kek)


def kek_id(kek: bytes) -> str:
    """16 hex digits of SHA-256 over a derivation of the KEK: names it, never reveals it."""
    return hashlib.sha256(_hkdf(kek, _FINGERPRINT_LABEL)).hexdigest()[:16]


def _aad(version: int, wrapping_kek_id: str) -> bytes:
    return f'ucm-dek|{WRAP_FORMAT}|v{int(version)}|{wrapping_kek_id}'.encode()


def new_dek() -> bytes:
    return csp_bytes(32)


def wrap(kek: bytes, version: int, dek: bytes) -> str:
    nonce = csp_bytes(12)
    sealed = AESGCM(_hkdf(kek, _WRAP_LABEL)).encrypt(nonce, dek, _aad(version, kek_id(kek)))
    return f'{WRAP_FORMAT}:' + base64.b64encode(nonce + sealed).decode('ascii')


def unwrap(kek: bytes, version: int, wrapped: str) -> bytes:
    """The DEK; raises ValueError when this KEK did not wrap it (or the row was altered)."""
    from cryptography.exceptions import InvalidTag
    fmt, _, body = (wrapped or '').partition(':')
    if fmt != WRAP_FORMAT or not body:
        raise ValueError(f'DEK version {version}: unknown wrapping format')
    raw = base64.b64decode(body)
    try:
        return AESGCM(_hkdf(kek, _WRAP_LABEL)).decrypt(raw[:12], raw[12:], _aad(version, kek_id(kek)))
    except InvalidTag:
        raise ValueError(f'DEK version {version} does not unwrap with this key-encryption key')


def material(kek: bytes, version: int, wrapped) -> bytes:
    """A row's DEK: NULL ``wrapped`` stands for the KEK material itself (version 1 adopted)."""
    return kek if wrapped is None else unwrap(kek, version, wrapped)


def stored_rows():
    """[(version, state, kek_id, wrapped)], or None outside an application context."""
    from flask import has_app_context
    if not has_app_context():
        return None
    from models import db, EncryptionKey
    with db.session.no_autoflush:
        return [(r.version, r.state, r.kek_id, r.wrapped)
                for r in EncryptionKey.query.order_by(EncryptionKey.version).all()]
