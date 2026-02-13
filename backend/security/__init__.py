"""
UCM Security Module
Phase 4: Security Hardening
- Private key encryption (Fernet/AES-256)
- CSRF protection
- Rate limiting (enhanced)
- Password policy enforcement
"""

from .encryption import (
    KeyEncryption, 
    key_encryption,
    decrypt_private_key,
    encrypt_private_key,
    encrypt_all_keys,
    decrypt_all_keys,
    has_encrypted_keys_in_db,
    MASTER_KEY_PATH
)
from .csrf import CSRFProtection, csrf_protect, init_csrf_middleware
from .password_policy import PasswordPolicy, validate_password, get_password_strength, get_policy_requirements
from .rate_limiter import (
    RateLimitConfig,
    RateLimiter,
    get_rate_limiter,
    init_rate_limiter,
    rate_limit
)

__all__ = [
    'KeyEncryption',
    'key_encryption',
    'decrypt_private_key',
    'encrypt_private_key',
    'encrypt_all_keys',
    'decrypt_all_keys',
    'has_encrypted_keys_in_db',
    'MASTER_KEY_PATH',
    'CSRFProtection',
    'csrf_protect',
    'init_csrf_middleware',
    'PasswordPolicy',
    'validate_password',
    'get_password_strength',
    'get_policy_requirements',
    'RateLimitConfig',
    'RateLimiter',
    'get_rate_limiter',
    'init_rate_limiter',
    'rate_limit'
]
