"""
Private Key Encryption Module
Encrypts private keys at rest using Fernet (AES-256-CBC with HMAC)

Environment variable: KEY_ENCRYPTION_KEY
- Must be 32 bytes base64-encoded (44 characters)
- Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

import os
import base64
import logging
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

logger = logging.getLogger(__name__)

# Encryption key marker prefix (to detect if data is encrypted)
ENCRYPTED_MARKER = b'ENC:'


class KeyEncryption:
    """
    Handles encryption/decryption of private keys stored in database.
    Uses Fernet symmetric encryption (AES-256-CBC + HMAC-SHA256).
    """
    
    _instance = None
    _fernet = None
    _enabled = False
    
    def __new__(cls):
        """Singleton pattern for key management"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
        return cls._instance
    
    def _initialize(self):
        """Initialize encryption with KEY_ENCRYPTION_KEY from environment"""
        key = os.getenv('KEY_ENCRYPTION_KEY')
        
        if not key:
            logger.warning(
                "⚠️  KEY_ENCRYPTION_KEY not set - private keys stored unencrypted. "
                "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
            self._enabled = False
            return
        
        try:
            # Validate key format
            key_bytes = key.encode('utf-8')
            self._fernet = Fernet(key_bytes)
            self._enabled = True
            logger.info("✅ Private key encryption enabled")
        except Exception as e:
            logger.error(f"❌ Invalid KEY_ENCRYPTION_KEY: {e}")
            self._enabled = False
    
    @property
    def is_enabled(self) -> bool:
        """Check if encryption is enabled"""
        return self._enabled
    
    def encrypt(self, data: str) -> str:
        """
        Encrypt private key data.
        
        Args:
            data: Base64-encoded private key (as stored in DB)
            
        Returns:
            Encrypted data with ENC: prefix (base64)
        """
        if not self._enabled or not data:
            return data
        
        # Check if already encrypted
        try:
            decoded = base64.b64decode(data)
            if decoded.startswith(ENCRYPTED_MARKER):
                return data  # Already encrypted
        except:
            pass
        
        try:
            # Data is base64, decode to get raw bytes
            raw_data = base64.b64decode(data)
            
            # Encrypt
            encrypted = self._fernet.encrypt(raw_data)
            
            # Add marker and re-encode to base64
            marked = ENCRYPTED_MARKER + encrypted
            return base64.b64encode(marked).decode('utf-8')
            
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return data  # Return unencrypted on failure
    
    def decrypt(self, data: str) -> str:
        """
        Decrypt private key data.
        
        Args:
            data: Encrypted data (base64 with ENC: marker)
            
        Returns:
            Original base64-encoded private key
        """
        if not data:
            return data
        
        try:
            # Decode base64
            decoded = base64.b64decode(data)
            
            # Check for encryption marker
            if not decoded.startswith(ENCRYPTED_MARKER):
                # Not encrypted, return as-is
                return data
            
            if not self._enabled:
                logger.error("Cannot decrypt: KEY_ENCRYPTION_KEY not set")
                raise ValueError("Encryption key not configured")
            
            # Remove marker and decrypt
            encrypted_data = decoded[len(ENCRYPTED_MARKER):]
            decrypted = self._fernet.decrypt(encrypted_data)
            
            # Return as base64 (original format)
            return base64.b64encode(decrypted).decode('utf-8')
            
        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key?)")
            raise ValueError("Failed to decrypt private key - check KEY_ENCRYPTION_KEY")
        except Exception as e:
            # If not encrypted or decryption fails, return as-is
            logger.debug(f"Data not encrypted or decryption skipped: {e}")
            return data
    
    def is_encrypted(self, data: str) -> bool:
        """Check if data is encrypted"""
        if not data:
            return False
        try:
            decoded = base64.b64decode(data)
            return decoded.startswith(ENCRYPTED_MARKER)
        except:
            return False
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new encryption key"""
        return Fernet.generate_key().decode('utf-8')


def decrypt_private_key(encoded_data: str) -> str:
    """
    Utility function to decrypt private key data.
    Handles both encrypted and unencrypted data transparently.
    
    Args:
        encoded_data: Base64-encoded private key (potentially encrypted)
        
    Returns:
        Decrypted base64-encoded private key
    """
    if not encoded_data:
        return encoded_data
    
    return key_encryption.decrypt(encoded_data)


def encrypt_private_key(encoded_data: str) -> str:
    """
    Utility function to encrypt private key data.
    
    Args:
        encoded_data: Base64-encoded private key
        
    Returns:
        Encrypted base64-encoded data (if encryption enabled)
    """
    if not encoded_data:
        return encoded_data
    
    return key_encryption.encrypt(encoded_data)


def encrypt_all_keys(dry_run: bool = True) -> tuple:
    """
    Encrypt all unencrypted private keys in database.
    
    Args:
        dry_run: If True, only count keys without modifying
        
    Returns:
        Tuple of (encrypted_count, skipped_count, errors)
    """
    if not key_encryption.is_enabled:
        return 0, 0, ["Encryption not enabled - set KEY_ENCRYPTION_KEY"]
    
    from models import db, CA, Certificate
    
    encrypted = 0
    skipped = 0
    errors = []
    
    # Process CAs
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
    
    # Process Certificates
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


# Singleton instance
key_encryption = KeyEncryption()
