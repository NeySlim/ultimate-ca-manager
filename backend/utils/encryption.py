"""
Encryption utilities for sensitive data in database
Uses Fernet symmetric encryption with key from environment
"""

import os
import base64
import hashlib
import logging
import tempfile
from cryptography.fernet import Fernet
from functools import lru_cache

logger = logging.getLogger(__name__)

MACHINE_KEY_PATH = '/opt/ucm/data/.machine-key'
MACHINE_ID_PATHS = ('/etc/machine-id', '/var/lib/dbus/machine-id', MACHINE_KEY_PATH)


def _require_db_encryption_key() -> bool:
    """True when the deployment opted in to refusing the machine-id fallback.

    Accepts the same truthy spellings as the rest of the codebase
    (see security.rate_limiter._get_env_bool): '1', 'true', 'yes', 'on'.
    """
    val = os.environ.get('UCM_REQUIRE_DB_ENCRYPTION_KEY', '').strip().lower()
    return val in ('1', 'true', 'yes', 'on')


def _read_machine_key():
    try:
        with open(MACHINE_KEY_PATH, 'r') as f:
            return f.read().strip() or None
    except OSError:
        return None


def _create_machine_key() -> str:
    """Persist a new .machine-key exactly once (0600); a worker that loses the
    first-start race gets the winner's key, never a second one."""
    from utils.randomness import csp_bytes
    candidate = csp_bytes(32).hex()
    directory = os.path.dirname(MACHINE_KEY_PATH)
    try:
        os.makedirs(directory, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=directory, prefix='.machine-key.')  # 0600
        try:
            with os.fdopen(fd, 'w') as f:
                f.write(candidate)
                f.flush()
                os.fsync(f.fileno())
            try:
                os.link(tmp, MACHINE_KEY_PATH)  # atomic, fails if the key already exists
            except FileExistsError:
                raise
            except OSError:
                # No hard links on this filesystem: exclusive create, then write.
                key_fd = os.open(MACHINE_KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(key_fd, 'w') as f:
                    f.write(candidate)
        finally:
            os.unlink(tmp)
        return candidate
    except FileExistsError:
        existing = _read_machine_key()
        if existing:
            return existing
        logger.error(f'{MACHINE_KEY_PATH} exists but is empty: integration secrets '
                     'will not be readable after a restart')
    except OSError as e:
        logger.error(f'Could not persist {MACHINE_KEY_PATH}: integration secrets '
                     f'will not be readable after a restart ({e})')
    return candidate


def _get_encryption_key() -> bytes:
    """
    Get or generate encryption key from environment.
    Key is derived from UCM_DB_ENCRYPTION_KEY or a default based on machine ID.
    """
    key = os.environ.get('UCM_DB_ENCRYPTION_KEY')

    if key:
        # Use provided key (should be base64-encoded 32 bytes)
        return key.encode()

    # No explicit key. The fallback below derives one from the machine id with
    # a salt that is a constant in this source file — so anyone holding a copy
    # of the database AND /etc/machine-id (world-readable, and routinely
    # captured in backups and VM images) can reconstruct the key and decrypt
    # every integration secret: DNS-provider credentials, LDAP/ADCS/WinRM
    # passwords, SMTP and OAuth secrets, SSO client secrets, webhook secrets,
    # ACME EAB keys and HSM credentials.
    #
    # The derivation is kept for backward compatibility — changing it would
    # make existing encrypted rows undecryptable — but it is now loud, and
    # deployments can refuse to run without a real key.
    if _require_db_encryption_key():
        raise RuntimeError(
            'UCM_DB_ENCRYPTION_KEY is not set and UCM_REQUIRE_DB_ENCRYPTION_KEY '
            'is enabled. Set UCM_DB_ENCRYPTION_KEY to a base64-encoded 32-byte '
            'Fernet key.'
        )

    logger.warning(
        'UCM_DB_ENCRYPTION_KEY is not set, falling back to a key derived from '
        'the machine id with a static, in-source salt. Anyone with a copy of '
        'the database and /etc/machine-id can decrypt all stored integration '
        'secrets. Set UCM_DB_ENCRYPTION_KEY (and UCM_REQUIRE_DB_ENCRYPTION_KEY=true '
        'to enforce it).'
    )

    # Generate deterministic key from machine-specific data
    # This ensures the same key is used across restarts
    machine_id = None
    for path in MACHINE_ID_PATHS:
        try:
            with open(path, 'r') as f:
                machine_id = f.read().strip()
        except Exception:
            continue
        if machine_id:
            break  # an empty machine-id (common in containers) falls through to the next

    if not machine_id:
        machine_id = _create_machine_key()

    # Derive Fernet-compatible key (32 bytes, base64 encoded).
    #
    # Every parameter below is frozen: the algorithm, the in-source salt, the
    # 100 000 iterations and the 32-byte length are all part of how existing
    # rows were encrypted, and nothing records them alongside the ciphertext.
    # Changing any one of them does not fail loudly — decrypt_value() returns
    # None on a wrong key — so every integration secret in the database would
    # simply start reading back as empty. The count is unrelated to the two in
    # services/backup/: this one has a machine id as input, those have an
    # archive password and a derived master key. tests/
    # test_kdf_parameters_are_frozen.py pins this derivation with a vector.
    derived = hashlib.pbkdf2_hmac(
        'sha256',
        machine_id.encode(),
        b'ucm-encryption-salt',
        100000,
        dklen=32
    )
    return base64.urlsafe_b64encode(derived)


@lru_cache(maxsize=1)
def get_cipher() -> Fernet:
    """Get cached Fernet cipher instance"""
    return Fernet(_get_encryption_key())


def encrypt_value(value: str) -> str:
    """
    Encrypt a string value for database storage.
    Returns base64-encoded encrypted string.
    """
    if not value:
        return value
    
    cipher = get_cipher()
    encrypted = cipher.encrypt(value.encode())
    return encrypted.decode()


def decrypt_value(encrypted: str) -> str:
    """
    Decrypt a value from database.
    Returns original string or None if decryption fails.

    Raises if the cipher itself cannot be constructed (missing key with
    UCM_REQUIRE_DB_ENCRYPTION_KEY enabled, or a malformed key): that is a
    configuration refusal, not a data problem, and it must never be
    indistinguishable from "no value" — swallowing it here made every
    integration secret silently read back as None (#245 follow-up).
    """
    if not encrypted:
        return encrypted

    # Deliberately OUTSIDE the try: a cipher-construction failure is loud.
    cipher = get_cipher()

    try:
        decrypted = cipher.decrypt(encrypted.encode())
        return decrypted.decode()
    except Exception:
        # Return None if decryption fails (corrupted or wrong key)
        return None


def is_encrypted(value: str) -> bool:
    """Check if a value appears to be encrypted (Fernet format)"""
    if not value:
        return False
    
    try:
        # Fernet tokens start with 'gAAAAA'
        return value.startswith('gAAAAA') and len(value) > 50
    except Exception:
        return False


def encrypt_if_needed(value: str) -> str:
    """Encrypt value only if not already encrypted"""
    if not value or is_encrypted(value):
        return value
    return encrypt_value(value)


def decrypt_if_needed(value: str) -> str:
    """Decrypt value only if it appears encrypted"""
    if not value or not is_encrypted(value):
        return value
    return decrypt_value(value)


def _refuse_startup_if_key_required_but_missing() -> None:
    """Import-time guard for UCM_REQUIRE_DB_ENCRYPTION_KEY (#245 follow-up).

    The check inside _get_encryption_key() only fires on the first
    encrypt/decrypt call, and every use of this module is lazy — so a
    deployment that set the require flag without a key still booted
    normally and only found out when integrations started reading their
    secrets back as None. This module IS imported during application
    startup (models.hsm via models/__init__, before create_app finishes),
    so raising here refuses startup the same way security.encryption's
    import-time singleton does for UCM_REQUIRE_KEY_ENCRYPTION.

    A key that is PRESENT but does not parse is refused too: presence is
    not usability, and the sibling flag already treats an invalid key as
    fatal (security/encryption.py).
    """
    if not _require_db_encryption_key():
        return

    if not os.environ.get('UCM_DB_ENCRYPTION_KEY'):
        raise RuntimeError(
            'UCM_DB_ENCRYPTION_KEY is not set and UCM_REQUIRE_DB_ENCRYPTION_KEY '
            'is enabled, refusing to start. Set UCM_DB_ENCRYPTION_KEY to a '
            'base64-encoded 32-byte Fernet key, or unset '
            'UCM_REQUIRE_DB_ENCRYPTION_KEY to fall back to the machine-id '
            'derived key.'
        )

    # Presence is not usability. A set-but-unparseable key (e.g. the output
    # of `openssl rand -hex 32` — hex, not the base64 Fernet expects) would
    # otherwise boot fine and only fail at first cipher use — and the
    # encrypted-property setters swallow that ValueError (models/sso.py,
    # models/email_notification.py), silently storing NEW secrets in
    # PLAINTEXT under the very flag whose purpose is to forbid that.
    # Calling get_cipher() rather than Fernet() directly also warms the
    # lru_cache on the success path; lru_cache does not memoize exceptions,
    # so the cache_clear() is belt-and-braces only.
    try:
        get_cipher()
    except Exception as e:
        get_cipher.cache_clear()
        raise RuntimeError(
            'UCM_DB_ENCRYPTION_KEY is set but is not a usable Fernet key '
            f'({e}) and UCM_REQUIRE_DB_ENCRYPTION_KEY is enabled, refusing '
            'to start. Generate one with: python -c "from cryptography.fernet '
            'import Fernet; print(Fernet.generate_key().decode())"'
        ) from e


_refuse_startup_if_key_required_but_missing()
