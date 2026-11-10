"""
Backup Service for UCM
Handles creation of encrypted, portable backup archives
"""
import os
import json
import struct
import uuid
import hashlib
import base64
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Iterator, List, Optional, Tuple

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

import fips_mode
from auth.permissions import PERMISSIONS_REVISION
from models import db
from config.settings import Config
from utils.datetime_utils import utc_now, utc_isoformat
from utils.randomness import csp_bytes

logger = logging.getLogger(__name__)

from . import container
from .container import ContainerError
from .errors import BackupExportError
from .export_generic import IdentityIndex, export_section, identity_of, load_model
from .manifest import SECTIONS
from .export_core import ExportCoreMixin
from .export_extended import ExportExtendedMixin
from .decrypt_mixin import DecryptMixin
from .restore_core import RestoreCoreMixin
from .restore_rbac import RestoreRbacMixin
from .restore_auth import RestoreAuthMixin
from .restore_notifications import RestoreNotificationsMixin
from .restore_policies import RestorePoliciesMixin
from .restore_extended import RestoreExtendedMixin



# Callers (and older archives) name a few sections differently from the
# manifest; both spellings are accepted on the way in.
_INCLUDE_ALIASES = {
    'cas': 'certificate_authorities',
    'templates': 'certificate_templates',
    'policies': 'certificate_policies',
    'truststore': 'trusted_certificates',
}


class BackupPasswordError(ValueError):
    """A backup password refused by the strength rules (#346).

    Its message names the rule that was hit and is safe to return to the
    caller, unlike the other ValueErrors raised while building a backup.
    """

def check_backup_kdf(kdf: Optional[str]) -> None:
    """A KDF a caller may ask for: None, 'pbkdf2', or 'argon2id' outside FIPS mode."""
    if kdf not in (None, 'pbkdf2', 'argon2id'):
        raise ValueError("kdf must be 'pbkdf2' or 'argon2id'")
    if kdf == 'argon2id':
        fips_mode.refuse('Argon2id backups')
        if not _ARGON2_AVAILABLE:
            raise ValueError("Argon2id backups need argon2-cffi")


class BackupService(ExportCoreMixin, ExportExtendedMixin, DecryptMixin,
                   RestoreCoreMixin, RestoreRbacMixin, RestoreAuthMixin,
                   RestoreNotificationsMixin, RestorePoliciesMixin, RestoreExtendedMixin):
    """Service for creating encrypted system backups

    Format v4 container layout (written today):
        [0:4]      magic = b'UCMB'
        [4]        format_version = 0x04
        [5]        flags (bit 0 = gzip-compressed chunks)
        [6]        kdf_id (1=PBKDF2-SHA256, 2=Argon2id)
        [7]        reserved = 0x00
        [8:10]     metadata_len (big-endian uint16)
        [10:10+N]  metadata JSON (cleartext header: ucm_version, created_at,
                   backup_type, kdf params, salt_b64, nonce_base_b64,
                   chunk_max, sections)
        then       chunks: len (big-endian uint32) || AES-256-GCM ciphertext

    Chunk i is sealed with nonce = nonce_base || i (uint32) and additional
    data = header || i || last flag. It holds one part of one section
    `{"section", "part", "rows"}`; the last chunk is the end record carrying
    each section's SHA-256, part and row counts. See container.py.

    Format v3 is a single GCM ciphertext after the same header, the whole
    header as additional data; v2 authenticates only the magic. Both are
    still read, never written.

    Format v1 (legacy): raw 32-byte salt + 12-byte nonce + GCM ciphertext.
    restore_backup() auto-detects the format from the magic bytes.
    """

    # v1/legacy constants (PBKDF2)
    PBKDF2_ITERATIONS = 100000
    KEY_SIZE = 32  # 256 bits for AES-256
    NONCE_SIZE = 12  # 96 bits for GCM
    SALT_SIZE = 32

    # Container constants (the framing itself lives in container.py)
    MAGIC = container.MAGIC
    FORMAT_VERSION_V2 = container.FORMAT_VERSION_V2
    FORMAT_VERSION_V3 = container.FORMAT_VERSION_V3
    FORMAT_VERSION_V4 = container.FORMAT_VERSION_V4
    CHUNK_MAX = container.CHUNK_MAX_DEFAULT
    FLAG_GZIP = container.FLAG_GZIP
    KDF_PBKDF2 = container.KDF_PBKDF2
    KDF_ARGON2ID = container.KDF_ARGON2ID

    # Logical schema of the payload, independent of the container framing. A
    # reader refuses a schema it does not know before touching the database.
    SCHEMA_VERSION = 3
    MIN_READER_SCHEMA_VERSION = 3

    # Argon2id params (OWASP 2024 recommendation for sensitive data) and the
    # stronger PBKDF2 used when Argon2 is unavailable. Both come from the
    # reader's whitelist, so what is written is by construction what will be
    # accepted on the way back in.
    ARGON2_TIME_COST = container.KDF_PROFILES[container.KDF_ARGON2ID]['emitted']['time_cost']
    ARGON2_MEMORY_COST = container.KDF_PROFILES[container.KDF_ARGON2ID]['emitted']['memory_cost']
    ARGON2_PARALLELISM = container.KDF_PROFILES[container.KDF_ARGON2ID]['emitted']['parallelism']
    ARGON2_SALT_SIZE = container.KDF_PROFILES[container.KDF_ARGON2ID]['salt_size']
    PBKDF2_ITERATIONS_V2 = container.KDF_PROFILES[container.KDF_PBKDF2]['emitted']['iterations']

    def __init__(self):
        self.app_version = Config.APP_VERSION
        self.last_payload_size = 0    # decompressed bytes of the last archive created
        self.last_export_warnings = []  # what the last export left out, to say in its result
    def create_backup(
        self,
        password: str,
        backup_type: str = "full",
        include: Optional[Dict[str, bool]] = None,
        kdf: Optional[str] = None
    ) -> bytes:
        """The whole archive in memory: `iter_backup` joined, for callers that need bytes."""
        return b''.join(self.iter_backup(password, backup_type, include, kdf))

    def iter_backup(
        self,
        password: str,
        backup_type: str = "full",
        include: Optional[Dict[str, bool]] = None,
        kdf: Optional[str] = None
    ) -> Iterator[bytes]:
        """
        Yield an encrypted v4 archive: the header, then one chunk at a time

        Args:
            password: Encryption password (min 12 chars)
            backup_type: "full", "database", or "certificates"
            include: Dict of what to include (cas, certificates, users, etc.)
            kdf: "pbkdf2" or "argon2id"; None picks Argon2id when it can

        Sections are exported one after the other and written as they come: no
        step holds the whole payload, only the section being written.
        """
        # Validate password
        self._validate_password(password)

        # What a backup carries is decided by the manifest: everything it
        # declares, minus the sections marked historical, which are opt-in.
        default_include = {
            name: not section.optional for name, section in SECTIONS.items()
        }
        if include is None:
            include = default_include
        else:
            merged = dict(default_include)
            for key, wanted in include.items():
                merged[_INCLUDE_ALIASES.get(key, key)] = wanted
            include = merged

        def _section(name, fn, *args, **kwargs):
            """Run one exporter; any failure aborts the backup.

            Substituting an empty section turned a missing table, an
            undecryptable key or an unexpected column into an archive that was
            announced as a successful backup while silently missing users, CAs
            or secrets — and said so only on the day it was restored.
            """
            try:
                return fn(*args, **kwargs)
            except BackupExportError:
                raise
            except Exception as exc:
                logger.error("Backup export of section '%s' failed: %s", name, exc,
                             exc_info=True)
                raise BackupExportError(
                    f"Section '{name}' could not be exported"
                ) from exc

        index = IdentityIndex()
        self.last_export_warnings = []
        self.last_payload_size = 0
        custom_exporters = {
            'configuration': self._export_configuration,
            'certificate_authorities': self._export_cas,
            'certificates': self._export_certificates,
            'revoked_serials': self._export_revoked_serials,
            'ssh_cas': self._export_ssh_cas,
        }

        def export(name):
            section = SECTIONS[name]
            if not include.get(name, not section.optional):
                return {} if name == 'configuration' else []
            if name in custom_exporters:
                rows = _section(name, custom_exporters[name], True)
                if section.custom and name != 'configuration':
                    rows = _section(
                        name, self._merge_with_manifest, name, rows, index)
                return rows
            return _section(name, export_section, name, index, self.last_export_warnings)

        # Choose KDF: Argon2id if available, else strong PBKDF2. The profile
        # written here is the one the reader whitelists, taken from the same
        # table: a parameter changed on one side and not the other would
        # produce archives this server refuses to read back.
        # FIPS mode: PBKDF2 only, Argon2id is not an approved KDF.
        # kdf='pbkdf2' writes an archive a FIPS instance can restore.
        check_backup_kdf(kdf)
        use_argon2 = kdf != 'pbkdf2' and _ARGON2_AVAILABLE and not fips_mode.enabled()
        kdf_id = self.KDF_ARGON2ID if use_argon2 else self.KDF_PBKDF2
        profile = container.KDF_PROFILES[kdf_id]
        kdf_params = {'type': profile['type'], **profile['emitted']}
        # A salt per archive: no two archives share a key, whatever their nonces
        salt = csp_bytes(profile['salt_size'])

        if kdf_id == self.KDF_ARGON2ID:
            master_key = self._derive_argon2id(
                password, salt,
                time_cost=kdf_params['time_cost'],
                memory_cost=kdf_params['memory_cost'],
                parallelism=kdf_params['parallelism'],
                hash_len=kdf_params['hash_len'],
            )
        else:
            master_key = self._derive_pbkdf2(password, salt, kdf_params['iterations'])

        # The header is every chunk's additional data: editing any byte of it
        # (the version, the backup type, the KDF profile, the section list)
        # breaks every tag.
        names = ['metadata', *SECTIONS, 'https_server']
        nonce_base = csp_bytes(container.NONCE_BASE_SIZE)
        header = container.build_header(
            format_version=self.FORMAT_VERSION_V4,
            flags=self.FLAG_GZIP,
            kdf_id=kdf_id,
            metadata={
                'format_version': self.FORMAT_VERSION_V4,
                'ucm_version': self.app_version,
                'created_at': utc_now().isoformat() + 'Z',
                'backup_type': backup_type,
                'kdf': kdf_params,
                'salt_b64': base64.b64encode(salt).decode(),
                'nonce_base_b64': base64.b64encode(nonce_base).decode(),
                'chunk_max': self.CHUNK_MAX,
                'sections': names,
            },
        )
        writer = container.ChunkWriter(master_key, header, nonce_base, names,
                                       chunk_max=self.CHUNK_MAX)

        def write(name, value):
            try:
                yield from writer.section(name, value)
            except ContainerError as exc:
                raise BackupExportError(str(exc)) from exc

        yield header

        metadata = self._get_metadata(backup_type)
        metadata.update({
            'schema_version': self.SCHEMA_VERSION,
            'min_reader_schema_version': self.MIN_READER_SCHEMA_VERSION,
            'permissions_revision': PERMISSIONS_REVISION,
            'database_dialect': self._database_dialect(),
            'excluded_sections': sorted(name for name, wanted in include.items() if not wanted),
        })
        yield from write('metadata', metadata)

        # Group members and WebAuthn keys are not nested in their owner any
        # more: a reader of v4 applies their flat sections, always present.
        key_mismatches: List[str] = []
        for name in SECTIONS:
            rows = export(name)
            if name in self._PRIVATE_KEY_SECTIONS:
                self._encrypt_section_keys(rows, master_key)
                key_mismatches.extend(self._key_mismatches({name: rows}))
            yield from write(name, rows)
            del rows

        # Files, not a table: the HTTPS certificate and key the server serves
        yield from write('https_server', _section('https_server', self._export_https_files))

        yield writer.finish({'key_mismatches': key_mismatches})
        self.last_payload_size = writer.payload_bytes

    # Sections whose rows carry a private key, encrypted one by one under the master key
    _PRIVATE_KEY_SECTIONS = ('certificate_authorities', 'certificates', 'ssh_cas')

    def _encrypt_section_keys(self, rows, master_key: bytes) -> None:
        for row in rows:
            if isinstance(row, dict) and '_private_key_plaintext' in row:
                row['private_key_pem_encrypted'] = self._encrypt_private_key(
                    row.pop('_private_key_plaintext'), master_key)

    def _merge_with_manifest(self, section_name, rows, index):
        """Complete a hand-written section with every column of its model.

        The dedicated exporters carry what is not a column (a PEM, a decrypted
        key, a list of URLs). Everything else comes from the manifest, so a
        column added to the model reaches the archive without anyone having to
        remember this function exists.
        """
        from .manifest import SECTIONS as _SECTIONS
        section = _SECTIONS[section_name]
        generic = export_section(section_name, index)
        by_identity = {
            tuple(str(row.get(name)) for name in section.identity): row
            for row in generic
        }
        merged = []
        for row in rows:
            key = tuple(str(row.get(name)) for name in section.identity)
            base = by_identity.get(key, {})
            merged.append({**base, **row})
        return merged

    @staticmethod
    def _key_mismatches(backup_data: Dict[str, Any]) -> List[str]:
        """Records whose stored key is not their certificate's.

        Carried so a restore can refuse the pair with a name to give the
        administrator, and so the state is visible in the archive rather than
        only in a log line on the machine that wrote it.
        """
        found = []
        for section in ('certificate_authorities', 'certificates', 'ssh_cas'):
            for row in backup_data.get(section, []):
                if isinstance(row, dict) and row.get('_key_mismatch'):
                    found.append(f"{section}:{row.get('refid')}")
        return found

    @staticmethod
    def _section_digests(backup_data: Dict[str, Any]) -> Dict[str, str]:
        """A digest per section, so a restore can tell which one arrived short.

        The whole-payload checksum says an archive is damaged; these say
        where, which is what an administrator needs to decide whether the
        damage touches the authorities or an optional history.
        """
        digests = {}
        for name, value in backup_data.items():
            if name == 'metadata':
                continue
            try:
                canonical = json.dumps(value, sort_keys=True, default=str).encode()
            except (TypeError, ValueError):
                continue
            digests[name] = hashlib.sha256(canonical).hexdigest()
        return digests

    @staticmethod
    def _database_dialect() -> str:
        """The dialect actually in use, not the one this code was written on."""
        try:
            return db.session.get_bind().dialect.name
        except Exception:
            logger.warning("Could not determine the database dialect for the backup")
            return 'unknown'

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

    # A backup file is offline data: the password is the only thing between a
    # stolen file and every private key in it, so a trivially repeated
    # password is refused. The floor scales with length, since a longer
    # password compensates for a smaller alphabet (#346).
    MIN_PASSWORD_LENGTH = 12
    MIN_DISTINCT_CHARS = 8
    LONG_PASSWORD_LENGTH = 16
    MIN_DISTINCT_CHARS_LONG = 6

    @classmethod
    def validate_password(cls, password: str) -> None:
        """The backup password rule, for every place that accepts one (the
        backup routes, the scheduled backup setting): raises
        BackupPasswordError with the reason."""
        cls._validate_password(cls, password)

    def _validate_password(self, password: str):
        """Validate backup password strength.

        Raises BackupPasswordError, whose message is meant to be shown to
        the operator: a generic refusal left them guessing which rule they
        had hit, with the strength meter calling the password strong (#346).
        """
        if len(password) < self.MIN_PASSWORD_LENGTH:
            raise BackupPasswordError(
                f"Backup password must be at least {self.MIN_PASSWORD_LENGTH} characters"
            )

        distinct = len(set(password))
        required = (
            self.MIN_DISTINCT_CHARS_LONG
            if len(password) >= self.LONG_PASSWORD_LENGTH
            else self.MIN_DISTINCT_CHARS
        )
        if distinct < required:
            raise BackupPasswordError(
                f"Backup password repeats too few characters: it uses {distinct} "
                f"distinct characters and needs at least {required} "
                f"(a password of {self.LONG_PASSWORD_LENGTH} characters or more "
                f"needs {self.MIN_DISTINCT_CHARS_LONG})"
            )

    def _derive_master_key(self, password: str) -> tuple:
        """Legacy v1 PBKDF2 derivation (kept for backward-compat restore)"""
        salt = csp_bytes(self.SALT_SIZE)
        key = self._derive_pbkdf2(password, salt, self.PBKDF2_ITERATIONS)
        return key, salt

    def _encrypt_backup(self, data: bytes, key: bytes) -> bytes:
        """Legacy v1 AES-256-GCM encrypt (kept for tests / fallback)"""
        nonce = csp_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, data, None)
        return nonce + ciphertext

    def _encrypt_private_key(self, key_pem: str, master_key: bytes) -> Dict[str, str]:
        """Encrypt individual private key with unique salt.

        The 10 000 iterations here are NOT the archive's password stretch and
        must not be aligned on it. The input is ``master_key`` — 32 bytes
        already derived from the password by the container KDF — so there is no
        low-entropy secret left to stretch; the derivation only separates one
        key's AES key from another's, per salt.

        More to the point, the count cannot be changed. The blob below records
        the algorithm, the salt and the nonce, and nothing else: it carries no
        version and no KDF parameters. Raising the count would not be refused
        by an older archive, it would surface as "wrong password or corrupted
        file" on restore, for every private key in every backup ever taken.
        Moving it needs a new field in this dict and a reader that honours it —
        the container's master KDF is the example to follow, which is exactly
        why that one could go from 100 000 to 600 000 while keeping 100 000 as
        the accepted floor. ``_decrypt_private_key`` holds the other half of
        this constant; ``tests/test_kdf_parameters_are_frozen.py`` pins both
        with a vector produced before any such change.
        """
        # Derive unique key for this specific private key
        salt = csp_bytes(self.SALT_SIZE)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_SIZE,
            salt=salt,
            iterations=10000,  # see the docstring: frozen by the stored format
            backend=default_backend()
        )
        key = kdf.derive(master_key)

        # Encrypt
        nonce = csp_bytes(self.NONCE_SIZE)
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(nonce, key_pem.encode(), None)

        return {
            'algorithm': 'AES-256-GCM',
            'salt': salt.hex(),
            'nonce': nonce.hex(),
            'ciphertext': ciphertext.hex()
        }
