"""
Decrypt methods mixin for BackupService
"""
import json
import gzip
import struct
import base64
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

from config.settings import Config
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class DecryptMixin:
    def _decrypt_v1(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Decrypt legacy v1 format: [salt(32)][nonce(12)][ciphertext+tag]"""
        if len(backup_bytes) < self.SALT_SIZE + self.NONCE_SIZE:
            raise ValueError("Invalid backup file: too small")

        master_salt = backup_bytes[:self.SALT_SIZE]
        encrypted_data = backup_bytes[self.SALT_SIZE:]
        master_key = self._derive_pbkdf2(password, master_salt, self.PBKDF2_ITERATIONS)

        try:
            nonce = encrypted_data[:self.NONCE_SIZE]
            ciphertext = encrypted_data[self.NONCE_SIZE:]
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, None)
        except Exception:
            raise ValueError("Decryption failed - wrong password or corrupted file")

        try:
            backup_data = json.loads(plaintext.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup format: not valid JSON")

        return master_key, backup_data


    def _decrypt_v2(self, backup_bytes: bytes, password: str) -> Tuple[bytes, Dict[str, Any]]:
        """Decrypt v2 format: magic+version+flags+kdf+metadata+ciphertext"""
        if len(backup_bytes) < 10:
            raise ValueError("Invalid backup file: truncated header")

        magic = backup_bytes[:4]
        if magic != self.MAGIC:
            raise ValueError("Invalid backup file: bad magic bytes")

        version = backup_bytes[4]
        flags = backup_bytes[5]
        kdf_id = backup_bytes[6]
        # reserved = backup_bytes[7]

        if version != self.FORMAT_VERSION_V2:
            raise ValueError(f"Unsupported backup format version: {version}")

        metadata_len = struct.unpack('>H', backup_bytes[8:10])[0]
        if len(backup_bytes) < 10 + metadata_len + self.NONCE_SIZE:
            raise ValueError("Invalid backup file: truncated")

        metadata_bytes = backup_bytes[10:10 + metadata_len]
        ciphertext = backup_bytes[10 + metadata_len:]

        try:
            metadata = json.loads(metadata_bytes.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup metadata")

        # Derive key
        salt = base64.b64decode(metadata['salt_b64'])
        nonce = base64.b64decode(metadata['nonce_b64'])
        kdf_params = metadata.get('kdf', {})

        if kdf_id == self.KDF_ARGON2ID:
            if not _ARGON2_AVAILABLE:
                raise ValueError("Backup uses Argon2id but argon2-cffi is not installed")
            master_key = self._derive_argon2id(
                password, salt,
                time_cost=kdf_params.get('time_cost', self.ARGON2_TIME_COST),
                memory_cost=kdf_params.get('memory_cost', self.ARGON2_MEMORY_COST),
                parallelism=kdf_params.get('parallelism', self.ARGON2_PARALLELISM),
                hash_len=kdf_params.get('hash_len', self.KEY_SIZE),
            )
        elif kdf_id == self.KDF_PBKDF2:
            master_key = self._derive_pbkdf2(
                password, salt, kdf_params.get('iterations', self.PBKDF2_ITERATIONS_V2)
            )
        else:
            raise ValueError(f"Unknown KDF id: {kdf_id}")

        # Decrypt
        try:
            # v2 uses magic bytes as AAD to authenticate the container
            plaintext = AESGCM(master_key).decrypt(nonce, ciphertext, self.MAGIC)
        except Exception:
            raise ValueError("Decryption failed - wrong password or corrupted file")

        # Decompress if gzipped
        if flags & self.FLAG_GZIP:
            try:
                plaintext = gzip.decompress(plaintext)
            except Exception:
                raise ValueError("Invalid backup: gzip decompression failed")

        try:
            backup_data = json.loads(plaintext.decode())
        except json.JSONDecodeError:
            raise ValueError("Invalid backup format: not valid JSON")

        return master_key, backup_data


    def _decrypt_private_key(self, encrypted_data: Dict[str, str], master_key: bytes) -> str:
        """Decrypt individual private key"""
        salt = bytes.fromhex(encrypted_data['salt'])
        nonce = bytes.fromhex(encrypted_data['nonce'])
        ciphertext = bytes.fromhex(encrypted_data['ciphertext'])

        # Derive key
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,
            backend=default_backend()
        )
        key = kdf.derive(master_key)

        # Decrypt
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode()
