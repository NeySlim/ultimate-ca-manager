"""
Encryption utilities for sensitive data in database
Uses Fernet symmetric encryption with key from environment
"""

import os
import base64
import hashlib
from cryptography.fernet import Fernet
from functools import lru_cache


def _get_encryption_key() -> bytes:
    """
    Get or generate encryption key from environment.
    Key is derived from UCM_DB_ENCRYPTION_KEY or a default based on machine ID.
    """
    key = os.environ.get('UCM_DB_ENCRYPTION_KEY')
    
    if key:
        # Use provided key (should be base64-encoded 32 bytes)
        return key.encode()
    
    # Generate deterministic key from machine-specific data
    # This ensures the same key is used across restarts
    machine_id_paths = [
        '/etc/machine-id',
        '/var/lib/dbus/machine-id',
        '/opt/ucm/data/.machine-key'
    ]
    
    machine_id = None
    for path in machine_id_paths:
        try:
            with open(path, 'r') as f:
                machine_id = f.read().strip()
                break
        except:
            continue
    
    if not machine_id:
        # Create a persistent machine key
        import secrets
        machine_id = secrets.token_hex(32)
        try:
            os.makedirs('/opt/ucm/data', exist_ok=True)
            with open('/opt/ucm/data/.machine-key', 'w') as f:
                f.write(machine_id)
        except:
            pass
    
    # Derive Fernet-compatible key (32 bytes, base64 encoded)
    derived = hashlib.pbkdf2_hmac(
        'sha256',
        machine_id.encode(),
        b'ucm-pro-encryption-salt',
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
    """
    if not encrypted:
        return encrypted
    
    try:
        cipher = get_cipher()
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
    except:
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
