"""Centralised helpers for loading/storing private keys from DB columns.

UCM stores private keys in two layers:

1. Wire format on disk/in DB (``CA.prv``, ``Certificate.prv``):
   ``base64( [ENC: ciphertext] | raw_pem_bytes )``

   - At rest, the column may be **encrypted** (when ``KEY_ENCRYPTION_KEY``
     is set) — the ciphertext starts with the ``ENC:`` marker.
   - When encryption is disabled, the column is plain
     ``base64(pem_bytes)`` — no marker, no Fernet.

   :func:`security.encryption.decrypt_private_key` is **transparent** for
   both cases (no-op if marker is missing).

2. PEM bytes ready for ``cryptography.hazmat.primitives.serialization`` —
   what every caller actually needs.

The pattern ``base64.b64decode(decrypt_private_key(model.prv))`` was
duplicated in ~26 call sites across api/v2 and services/. This module
centralises it so:

- Imports of ``decrypt_private_key`` + ``base64`` collapse to one import.
- Future changes to the wire format (e.g., switching from base64 to a
  binary-safe blob, or adding HSM-backed unwrap) only touch one file.
- Error messages are consistent (``ValueError`` with the model class +
  id, instead of an opaque ``binascii.Error``).

This is a **cosmetic refactor** — behaviour is identical to the inline
pattern. No bug fix, no security change.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import logging
import re
from typing import Optional, Union

import fips_mode
from security.encryption import decrypt_private_key, encrypt_private_key

logger = logging.getLogger(__name__)


def load_pem_bytes(encrypted_prv: Optional[Union[str, bytes]],
                   *,
                   context: str = "private key") -> bytes:
    """Decrypt + base64-decode a stored private key column to raw PEM bytes.

    Parameters
    ----------
    encrypted_prv:
        Value of ``CA.prv`` / ``Certificate.prv`` (base64-encoded, may be
        Fernet-encrypted with the ENC: marker).
    context:
        Short human-readable label included in the error message when
        decoding fails (e.g. ``"CA 'Root CA'"``, ``"certificate 42"``).
        Helps operators correlate errors with the affected resource.

    Returns
    -------
    bytes
        PEM bytes ready for
        ``cryptography.hazmat.primitives.serialization.load_pem_private_key``.

    Raises
    ------
    ValueError
        If ``encrypted_prv`` is empty or cannot be decoded. The original
        exception is chained for debugging.
    """
    if not encrypted_prv:
        raise ValueError(f"No private key stored for {context}")

    try:
        decrypted = decrypt_private_key(encrypted_prv)
        return base64.b64decode(decrypted)
    except Exception as e:
        # Don't leak the raw value into the message; just enough context
        # for an operator to identify which row failed.
        logger.error(f"Failed to load PEM bytes for {context}: {e.__class__.__name__}: {e}")
        raise ValueError(
            f"Stored private key for {context} is malformed or "
            f"encrypted with a different KEY_ENCRYPTION_KEY"
        ) from e


def store_pem_bytes(pem_bytes: Union[str, bytes]) -> str:
    """Encode + encrypt PEM bytes for storage in a ``.prv`` column.

    Inverse of :func:`load_pem_bytes`. Accepts either ``bytes`` (typical:
    output of ``private_key.private_bytes(PEM)``) or ``str``
    (already-base64-encoded).

    Returns the wire-format string ready to assign to ``model.prv``.
    """
    if isinstance(pem_bytes, bytes):
        b64 = base64.b64encode(pem_bytes).decode('ascii')
    elif isinstance(pem_bytes, str):
        # Caller already encoded it; trust them.
        b64 = pem_bytes
    else:
        raise TypeError(f"pem_bytes must be bytes or str, got {type(pem_bytes).__name__}")

    return encrypt_private_key(b64)


__all__ = ['load_pem_bytes', 'store_pem_bytes', 'private_key_to_pem',
           'load_private_key_any', 'normalize_private_key_pem',
           'eddsa_key_name', 'refuse_eddsa_key', 'MalformedKey']


def private_key_to_pem(private_key) -> bytes:
    """Unencrypted PEM for a private key of any type UCM handles.

    RSA, EC and DSA keys keep the OpenSSL "traditional" form every existing
    consumer reads; Ed25519 and Ed448 have no such form and are written as
    PKCS#8, which load_pem_private_key reads the same way. Serialising them
    as traditional raised "format is invalid with this key" and turned an
    import of such a key into a generic refusal (#347 review).
    """
    from cryptography.hazmat.primitives import serialization
    try:
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    except ValueError:
        return private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )


# EdDSA keys fail to load in FIPS mode with an opaque error: they are
# recognised from their encoding instead (PKCS#8/SPKI OID, OpenSSH type name)
_EDDSA_OIDS = {b'\x2b\x65\x70': 'Ed25519', b'\x2b\x65\x71': 'Ed448'}
_EDDSA_SSH_TYPES = {
    b'ssh-ed25519': 'Ed25519', b'ssh-ed25519-cert-v01@openssh.com': 'Ed25519',
    b'sk-ssh-ed25519@openssh.com': 'Ed25519', b'sk-ssh-ed25519-cert-v01@openssh.com': 'Ed25519',
    b'ssh-ed448': 'Ed448', b'ssh-ed448-cert-v01@openssh.com': 'Ed448',
}
_PEM_BLOCK = re.compile(rb'-----BEGIN ([A-Z0-9 ]+)-----(.*?)-----END \1-----', re.S)


def _der_tlv(buf: bytes, pos: int):
    """(tag, value start, value end) of the DER element at *pos*."""
    tag, length = buf[pos], buf[pos + 1]
    pos += 2
    if length & 0x80:
        count = length & 0x7f
        if not 0 < count <= 4:
            raise ValueError('unsupported DER length')
        length = int.from_bytes(buf[pos:pos + count], 'big')
        pos += count
    if pos + length > len(buf):
        raise ValueError('truncated DER')
    return tag, pos, pos + length


def _der_eddsa(der: bytes) -> Optional[str]:
    """PKCS#8 or SubjectPublicKeyInfo: the first inner SEQUENCE is the AlgorithmIdentifier."""
    tag, pos, end = _der_tlv(der, 0)
    if tag != 0x30:
        return None
    while pos < end:
        tag, start, stop = _der_tlv(der, pos)
        if tag == 0x30:
            oid_tag, oid_start, oid_end = _der_tlv(der, start)
            return _EDDSA_OIDS.get(der[oid_start:oid_end]) if oid_tag == 0x06 else None
        pos = stop
    return None


def _ssh_blob_eddsa(blob: bytes) -> Optional[str]:
    """SSH wire blob (key, certificate, openssh-key-v1 file) holding a length-prefixed EdDSA type."""
    for name, label in _EDDSA_SSH_TYPES.items():
        if len(name).to_bytes(4, 'big') + name in blob:
            return label
    return None


def eddsa_key_name(data) -> Optional[str]:
    """'Ed25519' or 'Ed448' when *data* (PEM, DER, OpenSSH private key, public
    key line or certificate) holds an EdDSA key, else None; never raises."""
    if isinstance(data, str):
        data = data.encode('utf-8', 'replace')
    if not isinstance(data, (bytes, bytearray)) or not data:
        return None
    data = bytes(data)
    try:
        blocks = _PEM_BLOCK.findall(data)
        for label, body in blocks:
            der = base64.b64decode(b''.join(body.split()))
            if label == b'OPENSSH PRIVATE KEY':
                found = _ssh_blob_eddsa(der)
            elif label in (b'PRIVATE KEY', b'PUBLIC KEY'):
                found = _der_eddsa(der)
            else:
                found = None
            if found:
                return found
        if blocks:
            return None
        if data[:1] == b'\x30':
            return _der_eddsa(data)
        for token in data.split()[:2]:
            if token in _EDDSA_SSH_TYPES:
                return _EDDSA_SSH_TYPES[token]
            try:
                found = _ssh_blob_eddsa(base64.b64decode(token, validate=True))
            except (ValueError, binascii.Error):
                continue
            if found:
                return found
    except (ValueError, IndexError, binascii.Error):
        return None
    return None


def refuse_eddsa_key(data, context: str = 'key') -> None:
    """In FIPS mode, FipsRestricted naming *context* before an EdDSA key reaches the crypto library."""
    if not fips_mode.enabled():
        return
    name = eddsa_key_name(data)
    if name:
        fips_mode.refuse(f'{name} key of {context}')


# OpenSSL writes ML-DSA private keys with seed and expanded key ("both") by default;
# pyca reads the seed alone (RFC 9881 section 6). Below: read "both" from its seed.
SEEDLESS_MLDSA = (
    'This {label} private key holds only its expanded form, without the seed it was made '
    'from, and cannot be imported. Export it again with its seed from a key file that still '
    'holds it: openssl pkey -in key.pem -provparam ml-dsa.output_formats=seed-only -out key-seed.pem')


class MalformedKey(ValueError):
    """A key whose encoding UCM reads but whose content is inconsistent; the message says why."""


def _decrypt_pkcs8(der: bytes, password: bytes) -> Optional[bytes]:
    """Inner PKCS#8 of an EncryptedPrivateKeyInfo under PBES2 with PBKDF2 and AES-CBC (OpenSSL's
    default) or DES-EDE3-CBC; None for any other scheme or a wrong password."""
    from cryptography.hazmat.primitives import hashes, padding
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    from pyasn1.codec.der import decoder
    from pyasn1_modules import rfc5958, rfc8018
    prfs = {rfc8018.id_hmacWithSHA1: hashes.SHA1, rfc8018.id_hmacWithSHA224: hashes.SHA224,
            rfc8018.id_hmacWithSHA256: hashes.SHA256, rfc8018.id_hmacWithSHA384: hashes.SHA384,
            rfc8018.id_hmacWithSHA512: hashes.SHA512}
    ciphers = {rfc8018.aes128_CBC_PAD: (algorithms.AES, 16), rfc8018.aes192_CBC_PAD: (algorithms.AES, 24),
               rfc8018.aes256_CBC_PAD: (algorithms.AES, 32)}
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
        ciphers[rfc8018.des_EDE3_CBC] = (TripleDES, 24)
    except ImportError:
        pass
    try:
        info, rest = decoder.decode(der, asn1Spec=rfc5958.EncryptedPrivateKeyInfo())
        scheme = info['encryptionAlgorithm']
        if rest or scheme['algorithm'] != rfc8018.id_PBES2:
            return None
        pbes2, _ = decoder.decode(scheme['parameters'], asn1Spec=rfc8018.PBES2_params())
        kdf, enc = pbes2['keyDerivationFunc'], pbes2['encryptionScheme']
        if kdf['algorithm'] != rfc8018.id_PBKDF2 or enc['algorithm'] not in ciphers:
            return None
        params, _ = decoder.decode(kdf['parameters'], asn1Spec=rfc8018.PBKDF2_params())
        prf = params['prf']['algorithm'] if params['prf'].isValue else rfc8018.id_hmacWithSHA1
        cipher, size = ciphers[enc['algorithm']]
        if prf not in prfs or (params['keyLength'].isValue and int(params['keyLength']) != size):
            return None
        iv, _ = decoder.decode(enc['parameters'])
        key = PBKDF2HMAC(prfs[prf](), size, bytes(params['salt']['specified']),
                         int(params['iterationCount'])).derive(password)
        decryptor = Cipher(cipher(key), modes.CBC(bytes(iv))).decryptor()
        unpadder = padding.PKCS7(cipher.block_size).unpadder()
        padded = decryptor.update(bytes(info['encryptedData'])) + decryptor.finalize()
        return unpadder.update(padded) + unpadder.finalize()
    except Exception:  # pyca's own error stands for whatever cannot be opened here
        return None


def _pkcs8_der(data: bytes, password: Optional[bytes] = None) -> Optional[bytes]:
    """DER of a PKCS#8 given as PEM or DER, an encrypted one opened with *password*;
    None for anything else."""
    blocks = _PEM_BLOCK.findall(data)
    if blocks:
        bodies = [body for label, body in blocks if label == b'PRIVATE KEY']
        if bodies:
            return base64.b64decode(b''.join(bodies[0].split())) if len(bodies) == 1 else None
        sealed = [body for label, body in blocks if label == b'ENCRYPTED PRIVATE KEY']
        if len(sealed) != 1 or not password:
            return None
        return _decrypt_pkcs8(base64.b64decode(b''.join(sealed[0].split())), password)
    if data[:1] != b'\x30':
        return None
    # a password does not make DER encrypted: fall back to the DER itself
    return (_decrypt_pkcs8(data, password) if password else None) or data


def _mldsa_from_layout(der: bytes):
    """The ML-DSA key of a PKCS#8 in OpenSSL's "both" layout, its expanded key checked
    against the seed; None when *der* is not an ML-DSA PKCS#8 that needs this."""
    from pyasn1.codec.der import decoder
    from pyasn1.error import PyAsn1Error
    from pyasn1_modules import rfc5958
    from utils import key_algorithms
    try:
        info, rest = decoder.decode(der, asn1Spec=rfc5958.OneAsymmetricKey())
    except PyAsn1Error:
        return None
    label = key_algorithms.label_for_signature_oid(str(info['privateKeyAlgorithm']['algorithm']))
    alg = key_algorithms.get(label)
    inner = bytes(info['privateKey'])
    if rest or alg is None or not inner:
        return None
    if inner[0] == 0x04:
        from utils.algorithm_refusal import UnsupportedForKeyAlgorithm
        raise UnsupportedForKeyAlgorithm(SEEDLESS_MLDSA.format(label=label), key_algorithm=label)
    if inner[0] != 0x30:
        return None
    try:
        both, rest = decoder.decode(inner)
        seed, expanded = bytes(both[0]), bytes(both[1])
    except (PyAsn1Error, IndexError, TypeError):
        raise MalformedKey(f'Malformed {label} private key') from None
    if rest or len(seed) != 32:
        raise MalformedKey(f'Malformed {label} private key')
    key = alg.private_class.from_seed_bytes(seed)
    public = key.public_key().public_bytes_raw()
    # FIPS 204 skEncode starts with rho (from pk) then K, then tr = SHAKE256(pk, 64)
    if expanded[:32] != public[:32] or expanded[64:128] != hashlib.shake_256(public).digest(64):
        raise MalformedKey(f'The seed and the expanded key of this {label} private key do not match')
    return key


def load_private_key_any(data, password=None):
    """Private key from PEM or DER, as pyca reads it; an ML-DSA key in OpenSSL's "both"
    layout, encrypted or not, is read from its seed, a seedless one refused
    (UnsupportedForKeyAlgorithm), one whose halves disagree raises MalformedKey."""
    from cryptography.hazmat.primitives import serialization
    if isinstance(data, str):
        data = data.encode('utf-8')
    data = bytes(data)
    pem = data.lstrip().startswith(b'-----')
    load = serialization.load_pem_private_key if pem else serialization.load_der_private_key
    try:
        return load(data, password=password)
    except ValueError as e:
        if 'Incorrect password' in str(e):  # pyca's verdict on the password stands
            raise
        der = _pkcs8_der(data, password)
        key = _mldsa_from_layout(der) if der else None
        if key is None:
            raise
        return key


def normalize_private_key_pem(data):
    """*data* unchanged, unless it is an ML-DSA key in the "both" layout: then the same key
    as seed-only PKCS#8 PEM. A seedless ML-DSA key raises UnsupportedForKeyAlgorithm."""
    raw = data.encode('utf-8') if isinstance(data, str) else bytes(data)
    der = _pkcs8_der(raw)
    key = _mldsa_from_layout(der) if der else None
    if key is None:
        return data
    pem = private_key_to_pem(key)
    return pem.decode('ascii') if isinstance(data, str) else pem
