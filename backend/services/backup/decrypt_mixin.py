"""
Decrypt methods mixin for BackupService

Reading a backup means running on bytes the caller chose. Every step below
is bounded by container.py before it is computed: the framing, the KDF
profile, the decompressed size, the shape of the JSON.
"""
import base64
import json
import logging
from typing import Dict, Any, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Argon2id support
try:
    from argon2.low_level import hash_secret_raw, Type as Argon2Type
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False

import fips_mode
from config.settings import Config
from fips_mode import FipsRestricted
from utils.datetime_utils import utc_now

from . import container
from .container import ContainerError

logger = logging.getLogger(__name__)


class BackupDecryptionError(ValueError):
    """The backup could not be decrypted: wrong password or corrupted file.
    Distinct from other ValueErrors so the operator is told which."""


class DecryptMixin:
    def _decrypt_v1(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Decrypt legacy v1 format: [salt(32)][nonce(12)][ciphertext+tag]

        Unframed and unauthenticated beyond the payload itself, so there is no
        header to check — but the payload bounds apply exactly as they do to a
        current archive.
        """
        if len(backup_bytes) > container.MAX_CONTAINER_BYTES:
            raise ContainerError("Backup file is too large to read")
        if len(backup_bytes) < self.SALT_SIZE + self.NONCE_SIZE + container.GCM_TAG_SIZE:
            raise ValueError("Invalid backup file: too small")

        master_salt = backup_bytes[:self.SALT_SIZE]
        encrypted_data = backup_bytes[self.SALT_SIZE:]
        master_key = self._derive_pbkdf2(password, master_salt, self.PBKDF2_ITERATIONS)

        try:
            nonce = encrypted_data[:self.NONCE_SIZE]
            ciphertext = encrypted_data[self.NONCE_SIZE:]
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        except Exception:
            raise BackupDecryptionError("Decryption failed - wrong password or corrupted file")

        return master_key, container.json_loads_bounded(plaintext)

    def _decrypt_framed(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Read a framed container, v2 or v3.

        The two differ in one respect, and it is the point of v3: v2 signs
        only the magic, so its header could be rewritten without breaking the
        tag, while v3 signs the whole header. Everything else — the bounds on
        the KDF profile, the salt and nonce sizes, the decompressed size, the
        shape of the JSON — applies to both.
        """
        metadata, header, ciphertext = container.parse_header(backup_bytes)
        version = metadata['format_version']
        kdf_id = metadata['kdf_id']

        salt, nonce, kdf_params = container.validate_kdf(kdf_id, metadata)

        if kdf_id == self.KDF_ARGON2ID:
            if fips_mode.enabled():
                raise FipsRestricted(
                    "Backups protected with Argon2id cannot be restored in FIPS mode: "
                    "restore it on a standard instance and back up again with the PBKDF2 KDF")
            if not _ARGON2_AVAILABLE:
                raise ValueError("Backup uses Argon2id but argon2-cffi is not installed")
            master_key = self._derive_argon2id(
                password, salt,
                time_cost=kdf_params['time_cost'],
                memory_cost=kdf_params['memory_cost'],
                parallelism=kdf_params['parallelism'],
                hash_len=kdf_params['hash_len'],
            )
        else:
            master_key = self._derive_pbkdf2(password, salt, kdf_params['iterations'])

        # v3 authenticates the canonical header; v2 only ever authenticated
        # the magic, and is read that way so old archives still open.
        aad = header if version == self.FORMAT_VERSION_V3 else self.MAGIC
        try:
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, aad)
        except Exception:
            raise BackupDecryptionError("Decryption failed - wrong password or corrupted file")

        if metadata['flags'] & self.FLAG_GZIP:
            plaintext = container.decompress_bounded(plaintext)

        return master_key, container.json_loads_bounded(plaintext)

    def _decrypt_private_key(self, encrypted_data: Dict[str, str], master_key: bytes) -> str:
        """Decrypt individual private key.

        The 10 000 iterations below are the other half of
        ``BackupService._encrypt_private_key``'s constant, and are frozen for
        the same reason: the blob carries no KDF parameters, so this reader has
        nothing to read them from and every archive ever written assumes this
        exact number.
        """
        salt = bytes.fromhex(encrypted_data['salt'])
        nonce = bytes.fromhex(encrypted_data['nonce'])
        ciphertext = bytes.fromhex(encrypted_data['ciphertext'])

        # Derive key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,  # see the docstring: frozen by the stored format
            backend=default_backend()
        )
        key = kdf.derive(master_key)

        # Decrypt
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode()
