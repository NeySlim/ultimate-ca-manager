"""
Backup Service for UCM
Handles creation of encrypted, portable backup archives
"""
import os
import json
import gzip
import struct
import uuid
import hashlib
import secrets
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend

# Argon2id support (preferred KDF for v2 backups)
try:
    from argon2.low_level import hash_secret_raw, Type as Argon2Type
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False

from models import db
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat

logger = logging.getLogger(__name__)

from .export_core import ExportCoreMixin
from .export_extended import ExportExtendedMixin
from .decrypt_mixin import DecryptMixin
from .restore_core import RestoreCoreMixin
from .restore_rbac import RestoreRbacMixin
from .restore_auth import RestoreAuthMixin
from .restore_notifications import RestoreNotificationsMixin
from .restore_policies import RestorePoliciesMixin
from .restore_extended import RestoreExtendedMixin


class BackupService(ExportCoreMixin, ExportExtendedMixin, DecryptMixin,
                   RestoreCoreMixin, RestoreRbacMixin, RestoreAuthMixin,
                   RestoreNotificationsMixin, RestorePoliciesMixin, RestoreExtendedMixin):
    """Service for creating encrypted system backups

    Format v2 container layout:
        [0:4]      magic = b'UCMB'
        [4]        format_version = 0x02
        [5]        flags (bit 0 = gzip-compressed plaintext)
        [6]        kdf_id (1=PBKDF2-SHA256, 2=Argon2id)
        [7]        reserved = 0x00
        [8:10]     metadata_len (big-endian uint16)
        [10:10+N]  metadata JSON (unencrypted header: ucm_version, created_at,
                   kdf params, salt_b64, nonce_b64)
        [10+N:]    AES-256-GCM ciphertext (plaintext = gzipped JSON if flag set)

    Format v1 (legacy): raw 32-byte salt + 12-byte nonce + GCM ciphertext.
    restore_backup() auto-detects format from magic bytes.
    """

    # v1/legacy constants (PBKDF2)
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 32

    # v2 constants
    MAGIC = b'UCMB'
    FORMAT_VERSION_V2 = 2
    FLAG_GZIP = 0x01
    KDF_PBKDF2 = 1
    KDF_ARGON2ID = 2

    # Argon2id params (OWASP 2024 recommendation for sensitive data)
    ARGON2_TIME_COST = 3
    ARGON2_MEMORY_COST = 65536  # 64 MiB
    ARGON2_PARALLELISM = 4
    ARGON2_SALT_SIZE = 16

    # Stronger PBKDF2 when Argon2 unavailable
    PBKDF2_ITERATIONS_V2 = 600000

    def __init__(self):
        self.app_version = Config.APP_VERSION
    def create_backup(
        self,
        password: str,
        backup_type: str = "full",
        include: Optional[Dict[str, bool]] = None
    ) -> bytes:
        """
        Create encrypted backup archive

        Args:
            password: Encryption password (min 12 chars)
            backup_type: "full", "database", or "certificates"
            include: Dict of what to include (cas, certificates, users, etc.)

        Returns:
            Encrypted backup as bytes
        """
        # Validate password
        self._validate_password(password)

        # Default includes
        if include is None:
            include = {
                'cas': True,
                'certificates': True,
                'users': True,
                'configuration': True,
                'acme_accounts': True,
                'acme_eab_credentials': True,
                'email_password': False,
                'groups': True,
                'custom_roles': True,
                'certificate_templates': True,
                'trusted_certificates': True,
                'sso_providers': True,
                'hsm_providers': True,
                'api_keys': True,
                'smtp_config': True,
                'notification_config': True,
                'certificate_policies': True,
                'auth_certificates': True,
                'dns_providers': True,
                'acme_domains': True,
                'acme_local_domains': True,
                'ssh_cas': True,
                'ssh_certificates': True,
                'microsoft_cas': True,
                'msca_requests': True,
                'scan_profiles': True,
                'scan_runs': False,  # historical, can be large
                'discovered_certificates': False,  # historical, can be large
                'approval_requests': True,  # pending approvals matter
                'scep_requests': False,  # historical
                'acme_client_orders': False,  # historical
                'hsm_keys': True,
                'audit_logs': False,  # opt-in, tamper-evident chain, can be huge
            }

        # Build backup data structure
        def _safe(fn, *args, **kwargs):
            """Call an export method; return [] on failure (missing table, model import error, etc.)"""
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Backup export {fn.__name__} failed: {e}")
                return [] if 'export' in fn.__name__ else {}

        backup_data = {
            'metadata': self._get_metadata(backup_type),
            'configuration': _safe(self._export_configuration, include.get('configuration', True)),
            'users': _safe(self._export_users, include.get('users', True)),
            'certificate_authorities': _safe(self._export_cas, include.get('cas', True)),
            'certificates': _safe(self._export_certificates, include.get('certificates', True)),
            'acme_accounts': _safe(self._export_acme_accounts, include.get('acme_accounts', True)),
            'acme_eab_credentials': _safe(self._export_acme_eab_credentials, include.get('acme_eab_credentials', True)),
            'groups': _safe(self._export_groups, include.get('groups', True)),
            'custom_roles': _safe(self._export_custom_roles, include.get('custom_roles', True)),
            'certificate_templates': _safe(self._export_templates, include.get('certificate_templates', True)),
            'trusted_certificates': _safe(self._export_truststore, include.get('trusted_certificates', True)),
            'sso_providers': _safe(self._export_sso_providers, include.get('sso_providers', True)),
            'hsm_providers': _safe(self._export_hsm_providers, include.get('hsm_providers', True)),
            'api_keys': _safe(self._export_api_keys, include.get('api_keys', True)),
            'smtp_config': _safe(self._export_smtp_config, include.get('smtp_config', True)),
            'notification_config': _safe(self._export_notification_config, include.get('notification_config', True)),
            'certificate_policies': _safe(self._export_policies, include.get('certificate_policies', True)),
            'auth_certificates': _safe(self._export_auth_certificates, include.get('auth_certificates', True)),
            'dns_providers': _safe(self._export_dns_providers, include.get('dns_providers', True)),
            'acme_domains': _safe(self._export_acme_domains, include.get('acme_domains', True)),
            'acme_local_domains': _safe(self._export_acme_local_domains, include.get('acme_local_domains', True)),
            'ssh_cas': _safe(self._export_ssh_cas, include.get('ssh_cas', True)),
            'ssh_certificates': _safe(self._export_ssh_certificates, include.get('ssh_certificates', True)),
            'microsoft_cas': _safe(self._export_microsoft_cas, include.get('microsoft_cas', True)),
            'msca_requests': _safe(self._export_msca_requests, include.get('msca_requests', True)),
            'scan_profiles': _safe(self._export_scan_profiles, include.get('scan_profiles', True)),
            'scan_runs': _safe(self._export_scan_runs, include.get('scan_runs', False)),
            'discovered_certificates': _safe(self._export_discovered_certificates, include.get('discovered_certificates', False)),
            'approval_requests': _safe(self._export_approval_requests, include.get('approval_requests', True)),
            'scep_requests': _safe(self._export_scep_requests, include.get('scep_requests', False)),
            'acme_client_orders': _safe(self._export_acme_client_orders, include.get('acme_client_orders', False)),
            'hsm_keys': _safe(self._export_hsm_keys, include.get('hsm_keys', True)),
            'audit_logs': _safe(self._export_audit_logs, include.get('audit_logs', False)),
            'https_server': _safe(self._export_https_files),
        }

        # Choose KDF: Argon2id if available, else strong PBKDF2
        if _ARGON2_AVAILABLE:
            kdf_id = self.KDF_ARGON2ID
            salt = secrets.token_bytes(self.ARGON2_SALT_SIZE)
            master_key = self._derive_argon2id(password, salt)
            kdf_params = {
                'type': 'argon2id',
                'time_cost': self.ARGON2_TIME_COST,
                'memory_cost': self.ARGON2_MEMORY_COST,
                'parallelism': self.ARGON2_PARALLELISM,
                'hash_len': self.KEY_SIZE,
            }
        else:
            kdf_id = self.KDF_PBKDF2
            salt = secrets.token_bytes(self.SALT_SIZE)
            master_key = self._derive_pbkdf2(password, salt, self.PBKDF2_ITERATIONS_V2)
            kdf_params = {
                'type': 'pbkdf2-sha256',
                'iterations': self.PBKDF2_ITERATIONS_V2,
                'hash_len': self.KEY_SIZE,
            }

        # Encrypt private keys individually (uses same master_key + PBKDF2 per-key salt for legacy compat)
        backup_data = self._encrypt_private_keys(backup_data, master_key)

        # Calculate checksum of plaintext
        json_str = json.dumps(backup_data, indent=2, sort_keys=True)
        checksum = hashlib.sha256(json_str.encode()).hexdigest()
        backup_data['checksum'] = {
            'algorithm': 'SHA256',
            'value': checksum
        }

        # Serialize final payload
        final_json = json.dumps(backup_data, indent=2, sort_keys=True).encode()

        # Compress (gzip level 6 — good ratio, fast)
        flags = self.FLAG_GZIP
        plaintext = gzip.compress(final_json, compresslevel=6)

        # Encrypt with AES-256-GCM
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        ciphertext = AESGCM(master_key).encrypt(nonce, plaintext, self.MAGIC)

        # Build v2 container
        metadata = {
            'format_version': self.FORMAT_VERSION_V2,
            'ucm_version': self.app_version,
            'created_at': utc_now().isoformat() + 'Z',
            'backup_type': backup_type,
            'kdf': kdf_params,
            'salt_b64': base64.b64encode(salt).decode(),
            'nonce_b64': base64.b64encode(nonce).decode(),
        }
        metadata_bytes = json.dumps(metadata, separators=(',', ':')).encode()
        if len(metadata_bytes) > 65535:
            raise ValueError("Backup metadata too large")

        header = (
            self.MAGIC
            + bytes([self.FORMAT_VERSION_V2, flags, kdf_id, 0])
            + struct.pack('>H', len(metadata_bytes))
            + metadata_bytes
        )
        return header + ciphertext

    def _derive_argon2id(self, password: str, salt: bytes,
                          time_cost: int = None, memory_cost: int = None,
                          parallelism: int = None, hash_len: int = None) -> bytes:
        """Derive key using Argon2id (memory-hard, side-channel resistant)"""
        if not _ARGON2_AVAILABLE:
            raise RuntimeError("argon2-cffi not installed")
        return hash_secret_raw(
            secret=password.encode(),
            salt=salt,
            time_cost=time_cost or self.ARGON2_TIME_COST,
            memory_cost=memory_cost or self.ARGON2_MEMORY_COST,
            parallelism=parallelism or self.ARGON2_PARALLELISM,
            hash_len=hash_len or self.KEY_SIZE,
            type=Argon2Type.ID,
        )

    def _derive_pbkdf2(self, password: str, salt: bytes, iterations: int) -> bytes:
        """Derive key using PBKDF2-SHA256"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode())

    def _validate_password(self, password: str):
        """Validate backup password strength"""
        if len(password) < 12:
            raise ValueError("Backup password must be at least 12 characters")

        # Check entropy (basic)
        unique_chars = len(set(password))
        if unique_chars < 8:
            raise ValueError("Backup password is too simple")

    def _derive_master_key(self, password: str) -> tuple:
        """Legacy v1 PBKDF2 derivation (kept for backward-compat restore)"""
        salt = secrets.token_bytes(self.SALT_SIZE)
        key = self._derive_pbkdf2(password, salt, self.PBKDF2_ITERATIONS)
        return key, salt

    def _encrypt_backup(self, data: bytes, key: bytes) -> bytes:
        """Legacy v1 AES-256-GCM encrypt (kept for tests / fallback)"""
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def _encrypt_private_key(self, key_pem: str, master_key: bytes) -> Dict[str, str]:
        """Encrypt individual private key with unique salt"""
        # Derive unique key for this specific private key
        salt = secrets.token_bytes(self.SALT_SIZE)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,  # Fewer iterations for per-key encryption
            backend=default_backend()
        )
        key = kdf.derive(master_key)

        # Encrypt
        nonce = secrets.token_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, key_pem.encode(), None)

        return {
            'algorithm': 'AES-256-GCM',
            'salt': salt.hex(),
            'nonce': nonce.hex(),
            'ciphertext': ciphertext.hex()
        }
        return plaintext.decode()
