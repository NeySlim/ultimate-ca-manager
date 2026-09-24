"""
Private Key Encryption Module
Encrypts private keys at rest using Fernet (AES-128-CBC with HMAC-SHA256)

Key sources (in order of priority):
1. /etc/ucm/master.key file (recommended)
2. KEY_ENCRYPTION_KEY environment variable (backward compat)
"""

import os
import stat
import base64
import logging
from pathlib import Path
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

ENCRYPTED_MARKER = b'ENC:'
MASTER_KEY_PATH = Path('/etc/ucm/master.key')


def key_encryption_required() -> bool:
    """True when the deployment opted in to refusing plaintext key storage.

    Accepts the same truthy spellings as the rest of the codebase
    (see security.rate_limiter._get_env_bool): '1', 'true', 'yes', 'on'.
    Public so the disable-encryption endpoint can refuse up front instead
    of exploding halfway through (#245 follow-up).
    """
    val = os.getenv('UCM_REQUIRE_KEY_ENCRYPTION', '').strip().lower()
    return val in ('1', 'true', 'yes', 'on')


class KeyEncryption:
    """
    Handles encryption/decryption of private keys stored in database.
    Uses Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256).
    """
    
    _instance = None
    _fernet = None
    _enabled = False
    _key_source = None  # 'file', 'env', or None
    
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
            logger.error(
                "🔓 Private-key encryption is DISABLED, no %s and no "
                "KEY_ENCRYPTION_KEY. CA and certificate private keys will be "
                "stored UNENCRYPTED at rest. Configure a key, and set "
                "UCM_REQUIRE_KEY_ENCRYPTION=true to refuse startup without one.",
                MASTER_KEY_PATH,
            )
            self._enabled = False
            self._key_source = None
            return
        
        try:
            key_bytes = key.encode('utf-8')
            self._fernet = Fernet(key_bytes)
            self._enabled = True
            logger.info("✅ Private key encryption enabled")
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
    
    def reload(self):
        """Reload encryption key (after enable/disable)"""
        self._fernet = None
        self._enabled = False
        self._key_source = None
        self._initialize()
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    @property
    def key_source(self) -> Optional[str]:
        return self._key_source
    
    def encrypt(self, data: str) -> str:
        if not self._enabled or not data:
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
        
        if not self._enabled:
            logger.error("Cannot decrypt: encryption key not available")
            raise ValueError("Encryption key not configured")
        
        # Step 2: actual decryption — only failures here are real errors.
        try:
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            decrypted = self._fernet.decrypt(encrypted_data)
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
        return Fernet.generate_key().decode('utf-8')
    
    @staticmethod
    def write_key_file(key: str) -> None:
        """Write encryption key to master.key file with secure permissions"""
        MASTER_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        MASTER_KEY_PATH.write_text(key + '\n')
        os.chmod(MASTER_KEY_PATH, stat.S_IRUSR | stat.S_IWUSR)  # 0600
        # Set ownership to ucm user if it exists (service runs as ucm)
        try:
            import pwd
            ucm_user = pwd.getpwnam('ucm')
            os.chown(MASTER_KEY_PATH, ucm_user.pw_uid, ucm_user.pw_gid)
        except (KeyError, OSError) as e:
            # ucm user doesn't exist (dev mode) or chown failed — running
            # as root with stricter file perms is fine, just less ideal.
            logger.debug(f"chown master.key to ucm:ucm skipped: {e}")
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
        if not self._enabled or not plaintext:
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
            if not self._enabled:
                logger.error("Cannot decrypt: encryption key not available")
                return data
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            return self._fernet.decrypt(encrypted_data).decode('utf-8')
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
    ('models.acme_client_account', 'AcmeClientAccount', 'account_key', 'text'),
    ('models.acme_client_account', 'AcmeClientAccount', '_eab_hmac_key', 'text'),
    ('models.scep', 'ScepProfile', 'challenge_password', 'text'),
    ('models.sso', 'SSOProvider', 'ldap_bind_password', 'text'),
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
    from fnmatch import fnmatchcase
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
        if row.value and any(fnmatchcase(row.key, pattern)
                             for pattern in MASTER_KEY_CONFIG_KEYS):
            yield f"SystemConfig {row.key}", row, 'value', 'text'


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
        return key_encryption._fernet.decrypt(token).decode('utf-8')
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
    if not key_encryption.is_enabled:
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
