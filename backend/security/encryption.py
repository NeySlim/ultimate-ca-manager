"""
Private Key Encryption Module
Encrypts private keys at rest using Fernet (AES-256-CBC with HMAC)

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


class KeyEncryption:
    """
    Handles encryption/decryption of private keys stored in database.
    Uses Fernet symmetric encryption (AES-256-CBC + HMAC-SHA256).
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
        except:
            pass
        
        try:
            raw_data = base64.b64decode(data)
            encrypted = self._fernet.encrypt(raw_data)
            marked = ENCRYPTED_MARKER + encrypted
            return base64.b64encode(marked).decode('utf-8')
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data
    
    def decrypt(self, data: str) -> str:
        if not data:
            return data
        
        try:
            decoded = base64.b64decode(data)
            
            if not decoded.startswith(ENCRYPTED_MARKER):
                return data
            
            if not self._enabled:
                logger.error("Cannot decrypt: encryption key not available")
                raise ValueError("Encryption key not configured")
            
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            decrypted = self._fernet.decrypt(encrypted_data)
            return base64.b64encode(decrypted).decode('utf-8')
            
        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key?)")
            raise ValueError("Failed to decrypt private key - wrong encryption key")
        except ValueError:
            raise
        except Exception as e:
            logger.debug(f"Data not encrypted or decryption skipped: {e}")
            return data
    
    def is_encrypted(self, data: str) -> bool:
        if not data:
            return False
        try:
            decoded = base64.b64decode(data)
            return decoded.startswith(ENCRYPTED_MARKER)
        except:
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
        except (KeyError, OSError):
            pass  # ucm user doesn't exist (dev mode) or chown failed
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


def decrypt_all_keys(dry_run: bool = True) -> tuple:
    """
    Decrypt all encrypted private keys in database.
    Returns: (decrypted_count, skipped_count, errors)
    """
    if not key_encryption.is_enabled:
        return 0, 0, ["Encryption not enabled"]
    
    from models import db, CA, Certificate
    
    decrypted = 0
    skipped = 0
    errors = []
    
    for ca in CA.query.filter(CA.prv.isnot(None)).all():
        try:
            if key_encryption.is_encrypted(ca.prv):
                if not dry_run:
                    ca.prv = key_encryption.decrypt(ca.prv)
                decrypted += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"CA {ca.refid}: {e}")
    
    for cert in Certificate.query.filter(Certificate.prv.isnot(None)).all():
        try:
            if key_encryption.is_encrypted(cert.prv):
                if not dry_run:
                    cert.prv = key_encryption.decrypt(cert.prv)
                decrypted += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Certificate {cert.refid}: {e}")
    
    if not dry_run:
        db.session.commit()
    
    return decrypted, skipped, errors


def encrypt_all_keys(dry_run: bool = True) -> tuple:
    """
    Encrypt all unencrypted private keys in database.
    Returns: (encrypted_count, skipped_count, errors)
    """
    if not key_encryption.is_enabled:
        return 0, 0, ["Encryption not enabled"]
    
    from models import db, CA, Certificate
    
    encrypted = 0
    skipped = 0
    errors = []
    
    for ca in CA.query.filter(CA.prv.isnot(None)).all():
        try:
            if not key_encryption.is_encrypted(ca.prv):
                if not dry_run:
                    ca.prv = key_encryption.encrypt(ca.prv)
                encrypted += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"CA {ca.refid}: {e}")
    
    for cert in Certificate.query.filter(Certificate.prv.isnot(None)).all():
        try:
            if not key_encryption.is_encrypted(cert.prv):
                if not dry_run:
                    cert.prv = key_encryption.encrypt(cert.prv)
                encrypted += 1
            else:
                skipped += 1
        except Exception as e:
            errors.append(f"Certificate {cert.refid}: {e}")
    
    if not dry_run:
        db.session.commit()
    
    return encrypted, skipped, errors


def has_encrypted_keys_in_db() -> bool:
    """Check if any private keys in DB are encrypted (have ENC: marker)"""
    from models import CA, Certificate
    
    for ca in CA.query.filter(CA.prv.isnot(None)).all():
        if key_encryption.is_encrypted(ca.prv):
            return True
    
    for cert in Certificate.query.filter(Certificate.prv.isnot(None)).all():
        if key_encryption.is_encrypted(cert.prv):
            return True
    
    return False


# Singleton instance
key_encryption = KeyEncryption()
