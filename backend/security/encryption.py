"""
Private Key Encryption Module
Encrypts private keys at rest using Fernet (AES-128-CBC with HMAC-SHA256) under a
data-encryption key (DEK) that the key-encryption key (KEK) wraps: see security.envelope.

KEK sources (in order of priority):
1. master.key in the configuration directory (UCM_CONFIG_DIR, default /etc/ucm)
2. KEY_ENCRYPTION_KEY environment variable (backward compat)
"""

import os
import time
import base64
import tempfile
import logging
from pathlib import Path
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from config.paths import master_key_file
from utils.randomness import csp_bytes

logger = logging.getLogger(__name__)

ENCRYPTED_MARKER = b'ENC:'
# A process re-reads the DEK rows before using a key once its last read is this old: a
# change committed elsewhere (rotation, disable) reaches every process within that bound
REFRESH_SECONDS = 2.0
MASTER_KEY_PATH = master_key_file()


def key_encryption_required() -> bool:
    """True when the deployment opted in to refusing plaintext key storage.

    Accepts the same truthy spellings as the rest of the codebase
    (see security.rate_limiter._get_env_bool): '1', 'true', 'yes', 'on'.
    Public so the disable-encryption endpoint can refuse up front instead
    of exploding halfway through (#245 follow-up).
    """
    val = os.getenv('UCM_REQUIRE_KEY_ENCRYPTION', '').strip().lower()
    return val in ('1', 'true', 'yes', 'on')


def log_encryption_disabled() -> None:
    logger.error(
        "🔓 Private-key encryption is DISABLED, no %s and no "
        "KEY_ENCRYPTION_KEY. CA and certificate private keys will be "
        "stored UNENCRYPTED at rest. Configure a key, and set "
        "UCM_REQUIRE_KEY_ENCRYPTION=true to refuse startup without one.",
        MASTER_KEY_PATH,
    )


def _table_missing(error) -> bool:
    """The DEK table does not exist yet (SQLite, PostgreSQL 42P01); any other error is not that."""
    orig = getattr(error, 'orig', error)
    if getattr(orig, 'sqlstate', None) == '42P01' or getattr(orig, 'pgcode', None) == '42P01':
        return True
    message = str(orig).lower()
    return 'no such table' in message and 'encryption_keys' in message


_UNREAD = object()


def _read_rows():
    """The DEK rows, [] before migration 153, None outside an application context."""
    from security import envelope
    try:
        return envelope.stored_rows()
    except Exception as e:
        if not _table_missing(e):
            raise
        from models import db
        db.session.rollback()
        logger.debug(f"DEK table not read: {type(e).__name__}")
        return []


class KeyEncryption:
    """
    Handles encryption/decryption of private keys stored in database.
    Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
    """
    
    _instance = None
    _fernet = None  # the active DEK: every new value is encrypted with it
    _decryptor = None  # every DEK this process holds, the active one first
    _key_bytes = None  # the KEK
    _versions = ()
    _active_version = None
    _rows_loaded = False
    _rows = None  # the DEK rows last read
    _read_at = 0.0  # time.monotonic() of that read
    _enabled = False
    _key_source = None  # 'file', 'env', or None
    dek_error = None  # why stored DEKs were not loaded ('kek_mismatch'), or None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize encryption from master.key file or env var"""
        key = None
        
        # Priority 1: master.key file
        if MASTER_KEY_PATH.exists():
            try:
                # Validate file permissions (should be 0600 or stricter)
                file_mode = MASTER_KEY_PATH.stat().st_mode & 0o777
                if file_mode & 0o077:
                    logger.warning(
                        f"⚠️ {MASTER_KEY_PATH} has insecure permissions {oct(file_mode)}, "
                        f"should be 0600. Fixing..."
                    )
                    MASTER_KEY_PATH.chmod(0o600)
                key = MASTER_KEY_PATH.read_text().strip()
                self._key_source = 'file'
                logger.info(f"🔑 Encryption key loaded from {MASTER_KEY_PATH}")
            except Exception as e:
                logger.error(f"❌ Failed to read {MASTER_KEY_PATH}: {e}")
        
        # Priority 2: environment variable (backward compat)
        if not key:
            key = os.getenv('KEY_ENCRYPTION_KEY')
            if key:
                self._key_source = 'env'
                logger.info("🔑 Encryption key loaded from KEY_ENCRYPTION_KEY env var")
        
        if not key:
            # No key configured. encrypt() below then returns its input
            # unchanged, so CA.prv / Certificate.prv — including CA *signing*
            # keys — are stored as plaintext in the database. That used to
            # happen silently; make it loud, and let deployments refuse to run
            # rather than write crown-jewel keys in the clear.
            if key_encryption_required():
                raise RuntimeError(
                    'Private-key encryption is required (UCM_REQUIRE_KEY_ENCRYPTION) '
                    f'but no key is configured. Provide {MASTER_KEY_PATH} or set '
                    'KEY_ENCRYPTION_KEY.'
                )
            from config.settings import Config
            if Config.AUTO_MASTER_KEY:
                # The start check creates the key or logs the final state
                logger.info("🔓 No master key loaded yet (%s)", MASTER_KEY_PATH)
            else:
                log_encryption_disabled()
            self._enabled = False
            self._key_source = None
            return
        
        try:
            key_bytes = key.encode('utf-8')
            Fernet(key_bytes)
            kek = base64.urlsafe_b64decode(key_bytes)
        except Exception as e:
            logger.error(f"❌ Invalid encryption key: {e}")
            # A key that EXISTS but does not parse must not bypass the
            # require flag: falling back to disabled would write private
            # keys to the database in plaintext — exactly the fail-open
            # the flag exists to refuse (#245 follow-up).
            if key_encryption_required():
                raise RuntimeError(
                    'Private-key encryption is required (UCM_REQUIRE_KEY_ENCRYPTION) '
                    f'but the configured key (source: {self._key_source}) is invalid: {e}. '
                    f'Fix {MASTER_KEY_PATH} or KEY_ENCRYPTION_KEY, refusing to run '
                    'with plaintext key storage.'
                )
            self._enabled = False
            return
        self._key_bytes = kek
        # A database error propagates: reload() then keeps the keys it had
        self._load_data_keys()
        if self._enabled:
            logger.info("✅ Private key encryption enabled")
    
    def _set_deks(self, deks: dict, active) -> None:
        self._versions = tuple(sorted(deks))
        self._active_version = active
        if active is None:
            self._fernet = self._decryptor = None
            self._enabled = False
            return
        self._fernet = deks[active]
        self._decryptor = MultiFernet([deks[active]] + [f for v, f in sorted(deks.items())
                                                        if v != active])
        self._enabled = True

    def _load_data_keys(self, rows=_UNREAD) -> None:
        """The DEKs the database holds under this KEK; outside an app context, the KEK alone.

        No row: the KEK is DEK version 1. A row this KEK did not wrap leaves encryption off
        (dek_error), so nothing is written under a key the database does not know.
        """
        from security import envelope
        rows = _read_rows() if rows is _UNREAD else rows
        self.dek_error = None
        self._set_deks({}, None)
        self._rows_loaded = rows is not None
        if rows is not None:
            self._rows, self._read_at = rows, time.monotonic()
        mine = envelope.kek_id(self._key_bytes)
        keys = [r for r in rows or () if r[1] in (envelope.ACTIVE, envelope.PREVIOUS)]
        disabled = any(r[1] == envelope.DISABLED and r[2] == mine for r in rows or ())
        if not keys:
            if disabled:
                return  # turned off from the UI while this KEK was configured
            self._set_deks({1: Fernet(base64.urlsafe_b64encode(self._key_bytes))}, 1)
            return
        deks, active = {}, None
        for version, state, wrapping_kek, wrapped in keys:
            try:
                if wrapping_kek != mine:
                    raise ValueError(f'DEK version {version} is wrapped by another key')
                dek = envelope.material(self._key_bytes, version, wrapped)
            except ValueError as e:
                self.dek_error = 'kek_mismatch'
                logger.error(f"❌ {e}: the configured key-encryption key is not this database's")
                return
            deks[version] = Fernet(base64.urlsafe_b64encode(dek))
            if state == envelope.ACTIVE:
                active = max(active or 0, version)
        self._set_deks(deks, active if active is not None else max(deks))
        if disabled:
            # Being disabled: every value still opens, nothing new is encrypted
            self._fernet = None

    _FIELDS = ('_fernet', '_decryptor', '_key_bytes', '_versions', '_active_version',
               '_rows_loaded', '_rows', '_read_at', '_enabled', '_key_source', 'dek_error')

    def _swap_in(self, build) -> None:
        """Build the new state on a scratch object, then publish it in one dict update.

        A request (or greenlet) running while the DEKs reload sees the old keys or the
        new ones, never encryption off: a write in that gap would land in plaintext.
        """
        fresh = object.__new__(type(self))
        for name in self._FIELDS:
            setattr(fresh, name, getattr(type(self), name))
        build(fresh)
        self.__dict__.update({name: getattr(fresh, name) for name in self._FIELDS})

    def _ensure_loaded(self) -> None:
        """The DEK rows, read before a use when never read or older than REFRESH_SECONDS.

        A read that fails raises: the use fails rather than run on keys that may be stale.
        """
        if self._key_bytes is None:
            return
        if self._rows_loaded and time.monotonic() - self._read_at < REFRESH_SECONDS:
            return
        from flask import has_app_context
        if not has_app_context():
            return
        rows = _read_rows()
        if self._rows_loaded and rows == self._rows:
            self._read_at = time.monotonic()
            return
        kek, source = self._key_bytes, self._key_source

        def build(fresh):
            fresh._key_bytes, fresh._key_source = kek, source
            fresh._load_data_keys(rows)
        self._swap_in(build)

    def reload(self):
        """Reload the KEK and the DEKs (after enable, disable, rotation or a cluster command)"""
        self._swap_in(lambda fresh: fresh._initialize())
    
    def unload(self):
        """Run as without a key, e.g. when the configured one is not the database's."""
        self._fernet = self._decryptor = None
        self._key_bytes = None
        self._enabled = False
        self._versions = ()
        self._active_version = None

    @property
    def kek_loaded(self) -> bool:
        return self._key_bytes is not None

    @property
    def active_version(self):
        return self._active_version

    @property
    def dek_versions(self) -> tuple:
        return self._versions

    def kek_fingerprint(self) -> Optional[str]:
        """The KEK's public fingerprint (security.envelope.kek_id), None without a KEK."""
        if self._key_bytes is None:
            return None
        from security.envelope import kek_id
        return kek_id(self._key_bytes)

    def kek_bytes_for_envelope(self) -> Optional[bytes]:
        """For security.envelope and the rotation only: never logged, never returned by the API."""
        return self._key_bytes

    def _decrypt_token(self, token: bytes) -> bytes:
        """Any DEK this process holds: during a rotation a value is under the old or the new one."""
        return self._decryptor.decrypt(token)

    def refresh(self) -> None:
        """Re-read the DEK rows now: under the key-state lock, the state the database holds."""
        self._read_at = float('-inf')
        self._ensure_loaded()

    @property
    def is_enabled(self) -> bool:
        self._ensure_loaded()
        return self._enabled

    @property
    def is_encrypting(self) -> bool:
        """Enabled and not being disabled: new values are encrypted."""
        return self.is_enabled and self._fernet is not None
    
    @property
    def key_source(self) -> Optional[str]:
        return self._key_source

    def derive_key(self, label: bytes, length: int = 32) -> Optional[bytes]:
        """A key of its own for ``label``, derived from the KEK (HKDF-SHA256).

        None without a KEK. Bound to the KEK, not the DEK: a DEK rotation changes no derived key.
        """
        if not self._key_bytes:
            return None
        return HKDF(algorithm=hashes.SHA256(), length=length, salt=None,
                    info=label).derive(self._key_bytes)
    
    def encrypt(self, data: str) -> str:
        if not self.is_encrypting or not data:
            return data
        
        try:
            decoded = base64.b64decode(data)
            if decoded.startswith(ENCRYPTED_MARKER):
                return data
        except Exception:
            # Input is not base64 — fall through to encrypt path. Expected
            # for raw text on the encrypt_text/decrypt_text path; not worth
            # logging at info level (would be noisy on every PEM write).
            pass
        
        try:
            raw_data = base64.b64decode(data)
            encrypted = self._fernet.encrypt(raw_data)
            marked = ENCRYPTED_MARKER + encrypted
            return base64.b64encode(marked).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise RuntimeError(f"Failed to encrypt private key data: {e}")
    
    def decrypt(self, data: str) -> str:
        if not data:
            return data
        
        # Step 1: probe whether data is base64-encoded with our marker.
        # PEM blobs (and any other non-base64 string) will fail b64decode here
        # — that's our "not encrypted by us, pass through" signal.
        try:
            decoded = base64.b64decode(data)
        except Exception:
            return data
        
        if not decoded.startswith(ENCRYPTED_MARKER):
            return data
        
        if not self.is_enabled:
            logger.error("Cannot decrypt: encryption key not available")
            raise ValueError("Encryption key not configured")
        
        # Step 2: actual decryption — only failures here are real errors.
        try:
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            decrypted = self._decrypt_token(encrypted_data)
            return base64.b64encode(decrypted).decode('utf-8')
        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key?)")
            raise ValueError("Failed to decrypt private key - wrong encryption key")
    
    def is_encrypted(self, data: str) -> bool:
        if not data:
            return False
        try:
            decoded = base64.b64decode(data)
            return decoded.startswith(ENCRYPTED_MARKER)
        except Exception:
            return False
    
    @staticmethod
    def generate_key() -> str:
        return base64.urlsafe_b64encode(csp_bytes(32)).decode('utf-8')
    
    @staticmethod
    def _fill_key_file(fd: int, key: str) -> None:
        """Write `key` to the open file `fd`, sync it and give it to the ucm user."""
        with os.fdopen(fd, 'w') as handle:
            handle.write(key + '\n')
            handle.flush()
            os.fsync(handle.fileno())
            try:
                import pwd
                ucm_user = pwd.getpwnam('ucm')
                os.fchown(handle.fileno(), ucm_user.pw_uid, ucm_user.pw_gid)
            except (KeyError, OSError) as e:
                # No ucm user (dev mode): a root-owned 0600 file still works
                logger.debug(f"chown master.key to ucm:ucm skipped: {e}")

    @staticmethod
    def write_key_file(key: str, exclusive: bool = False) -> None:
        """Write the master key file (0600), complete or not at all.

        `exclusive` never replaces an existing file: FileExistsError instead.
        Without hard links it creates the file with O_EXCL and removes it if the write fails.
        """
        MASTER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=MASTER_KEY_PATH.parent, prefix='.master.', suffix='.tmp')
        try:
            KeyEncryption._fill_key_file(fd, key)
            if exclusive:
                try:
                    os.link(tmp, MASTER_KEY_PATH)
                except FileExistsError:
                    raise
                except OSError:
                    fd = os.open(MASTER_KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    try:
                        KeyEncryption._fill_key_file(fd, key)
                    except BaseException:
                        MASTER_KEY_PATH.unlink(missing_ok=True)
                        raise
            else:
                os.replace(tmp, MASTER_KEY_PATH)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        logger.info(f"🔑 Master key written to {MASTER_KEY_PATH}")

    @staticmethod
    def remove_key_file() -> bool:
        """Remove master.key file. Returns True if file was removed."""
        if MASTER_KEY_PATH.exists():
            MASTER_KEY_PATH.unlink()
            logger.info(f"🔑 Master key removed from {MASTER_KEY_PATH}")
            return True
        return False
    
    @staticmethod
    def key_file_exists() -> bool:
        return MASTER_KEY_PATH.exists()

    def encrypt_string(self, plaintext: str) -> str:
        """Encrypt a plaintext string (e.g., LDAP bind password). Returns prefixed base64."""
        if not self.is_encrypting or not plaintext:
            return plaintext
        try:
            encrypted = self._fernet.encrypt(plaintext.encode('utf-8'))
            marked = ENCRYPTED_MARKER + encrypted
            return base64.b64encode(marked).decode('utf-8')
        except Exception as e:
            logger.error(f"String encryption failed: {e}")
            return plaintext

    def decrypt_string(self, data: str) -> str:
        """Decrypt a string encrypted with encrypt_string(). Returns plaintext."""
        if not data:
            return data
        try:
            decoded = base64.b64decode(data)
            if not decoded.startswith(ENCRYPTED_MARKER):
                return data
            if not self.is_enabled:
                logger.error("Cannot decrypt: encryption key not available")
                return data
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            return self._decrypt_token(encrypted_data).decode('utf-8')
        except Exception:
            return data

    def is_string_encrypted(self, data: str) -> bool:
        """Check if a string is encrypted with our marker."""
        if not data:
            return False
        try:
            decoded = base64.b64decode(data)
            return decoded.startswith(ENCRYPTED_MARKER)
        except Exception:
            return False


def decrypt_private_key(encoded_data: str) -> str:
    """Decrypt private key data. Handles both encrypted and unencrypted transparently."""
    if not encoded_data:
        return encoded_data
    return key_encryption.decrypt(encoded_data)


def encrypt_private_key(encoded_data: str) -> str:
    """Encrypt private key data (if encryption enabled)."""
    if not encoded_data:
        return encoded_data
    return key_encryption.encrypt(encoded_data)


def encrypt_text(plaintext: str) -> str:
    """Encrypt arbitrary text (PEM, JSON, secrets) at rest.

    Unlike :func:`encrypt_private_key`, this does NOT expect base64-encoded
    input — use it for human-readable blobs (PEM keys, ACME proxy account
    keys, LDAP bind passwords, etc.). No-op if encryption is disabled.
    """
    if not plaintext:
        return plaintext
    return key_encryption.encrypt_string(plaintext)


def decrypt_text(data: str) -> str:
    """Decrypt text encrypted with :func:`encrypt_text`.

    Transparently passes through plaintext that was never encrypted (legacy
    rows from before encryption was enabled).
    """
    if not data:
        return data
    return key_encryption.decrypt_string(data)


# Every value stored under the master key: (module, model, attribute, format).
# 'b64' holds base64 key material (encrypt_private_key), 'text' anything else
# (encrypt_text). SSOProvider's property takes off its database-layer wrapping.
MASTER_KEY_COLUMNS = (
    ('models.ca', 'CA', 'prv', 'b64'),
    ('models.certificate', 'Certificate', 'prv', 'b64'),
    ('models.ssh', 'SSHCertificateAuthority', 'private_key', 'b64'),
    ('models.deploy', 'DeployTarget', 'private_key', 'text'),
    ('models.deploy', 'DeployTarget', 'http_headers', 'text'),
    ('models.acme_client_account', 'AcmeClientAccount', 'account_key', 'text'),
    ('models.acme_client_account', 'AcmeClientAccount', '_eab_hmac_key', 'text'),
    ('models.scep', 'ScepProfile', 'challenge_password', 'text'),
    ('models.sso', 'SSOProvider', 'ldap_bind_password', 'text'),
    ('models.acme_models', 'AcmeClientOrder', '_pending_key', 'b64'),
)
# SystemConfig values stored under the master key, as fnmatch patterns
MASTER_KEY_CONFIG_KEYS = (
    'acme.client.eab_hmac_key',
    'acme.proxy.eab_hmac_key',
    'acme.account.*.private_key',
    # Pre-031 account keys: no reader left, but still encrypted on old installs
    'acme.client.*.account_key',
    'acme.proxy.account_key',
)


def master_key_values():
    """Yield (label, row, attribute, format) for every non-empty value stored
    under the master key. An empty column means no secret."""
    import importlib
    from sqlalchemy.orm.attributes import InstrumentedAttribute
    from models import SystemConfig

    for module, name, attribute, fmt in MASTER_KEY_COLUMNS:
        model = getattr(importlib.import_module(module), name)
        query = model.query
        column = getattr(model, attribute)
        if isinstance(column, InstrumentedAttribute):
            query = query.filter(column.isnot(None), column != '')
        for row in query.all():
            if getattr(row, attribute):
                label = getattr(row, 'refid', None) or row.id
                yield f"{name} {label}", row, attribute, fmt

    for row in SystemConfig.query.filter(SystemConfig.key.like('acme.%')).all():
        if row.value and _is_master_key_config(row.key):
            yield f"SystemConfig {row.key}", row, 'value', 'text'


def _is_master_key_config(key: str) -> bool:
    from fnmatch import fnmatchcase
    return any(fnmatchcase(key, pattern) for pattern in MASTER_KEY_CONFIG_KEYS)


def encrypt_master_key_value(value: str, fmt: str) -> str:
    """Encrypt one value of MASTER_KEY_COLUMNS; raises instead of passing through."""
    if fmt == 'b64':
        return key_encryption.encrypt(value)
    encrypted = key_encryption.encrypt_string(value)
    if not key_encryption.is_encrypted(encrypted):
        raise RuntimeError("Encryption failed")
    return encrypted


def decrypt_master_key_value(value: str, fmt: str) -> str:
    """Decrypt one value of MASTER_KEY_COLUMNS; raises instead of passing through."""
    if fmt == 'b64':
        return key_encryption.decrypt(value)
    if not key_encryption.is_enabled:
        raise ValueError("Encryption key not configured")
    token = base64.b64decode(value)[len(ENCRYPTED_MARKER):]
    try:
        return key_encryption._decrypt_token(token).decode('utf-8')
    except InvalidToken:
        raise ValueError("Failed to decrypt - wrong encryption key")


def count_master_key_values() -> Tuple[int, int]:
    """Return (encrypted, unencrypted) counts of the values under the master key."""
    encrypted = unencrypted = 0
    for _, row, attribute, _ in master_key_values():
        if key_encryption.is_encrypted(getattr(row, attribute)):
            encrypted += 1
        else:
            unencrypted += 1
    return encrypted, unencrypted


def has_unencrypted_master_key_values() -> bool:
    """True when a value under the master key is still stored unencrypted.

    Columns are filtered in SQL on the base64 prefix every ENC: value starts with,
    so a start with everything encrypted loads no row of them.
    """
    import importlib
    from sqlalchemy.orm.attributes import InstrumentedAttribute
    from models import db, SystemConfig

    prefix = base64.b64encode(ENCRYPTED_MARKER).decode()[:5]
    for module, name, attribute, _ in MASTER_KEY_COLUMNS:
        model = getattr(importlib.import_module(module), name)
        column = getattr(model, attribute)
        if not isinstance(column, InstrumentedAttribute):
            # A property over a wrapped column: only Python sees the value
            values = (getattr(row, attribute) for row in model.query.all())
            if any(v and not key_encryption.is_encrypted(v) for v in values):
                return True
            continue
        # substr, not LIKE: SQLite's LIKE ignores case
        if model.query.filter(column.isnot(None), column != '',
                              db.func.substr(column, 1, len(prefix)) != prefix).first():
            return True
    return any(not key_encryption.is_encrypted(row.value)
               for row in SystemConfig.query.filter(SystemConfig.key.like('acme.%')).all()
               if row.value and _is_master_key_config(row.key))


def decrypt_all_keys(dry_run: bool = True) -> tuple:
    """
    Decrypt every value stored under the master key. Nothing is written when
    one of them fails, since the caller then keeps the key.
    Returns: (decrypted_count, skipped_count, errors)
    """
    if not key_encryption.is_enabled:
        return 0, 0, ["Encryption not enabled"]

    from models import db

    decrypted = 0
    skipped = 0
    errors = []

    for label, row, attribute, fmt in master_key_values():
        value = getattr(row, attribute)
        if not key_encryption.is_encrypted(value):
            skipped += 1
            continue
        try:
            plaintext = decrypt_master_key_value(value, fmt)
            if not dry_run:
                setattr(row, attribute, plaintext)
            decrypted += 1
        except Exception as e:
            errors.append(f"{label}: {e}")

    if not dry_run:
        if errors:
            db.session.rollback()
        else:
            db.session.commit()

    return decrypted, skipped, errors


def encrypt_all_keys(dry_run: bool = True) -> tuple:
    """
    Encrypt every value still stored unencrypted under the master key.
    Returns: (encrypted_count, skipped_count, errors)
    """
    if not key_encryption.is_encrypting:
        return 0, 0, ["Encryption not enabled"]

    from models import db

    encrypted = 0
    skipped = 0
    errors = []

    for label, row, attribute, fmt in master_key_values():
        value = getattr(row, attribute)
        if key_encryption.is_encrypted(value):
            skipped += 1
            continue
        try:
            if not dry_run:
                setattr(row, attribute, encrypt_master_key_value(value, fmt))
            encrypted += 1
        except Exception as e:
            errors.append(f"{label}: {e}")

    if not dry_run:
        db.session.commit()

    return encrypted, skipped, errors


def has_encrypted_keys_in_db() -> bool:
    """Check if any value stored under the master key is encrypted (ENC: marker)"""
    return any(key_encryption.is_encrypted(getattr(row, attribute))
               for _, row, attribute, _ in master_key_values())


# Singleton instance
key_encryption = KeyEncryption()
