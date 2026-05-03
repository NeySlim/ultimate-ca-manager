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
import logging
from typing import Optional, Union

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


__all__ = ['load_pem_bytes', 'store_pem_bytes']
