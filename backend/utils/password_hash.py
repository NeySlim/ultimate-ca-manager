"""Password and secret hashing on PBKDF2-HMAC-SHA256, the KDF a FIPS
module approves; scrypt hashes from earlier versions still verify where
the crypto library allows it, and are replaced on the next successful check."""
import logging

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

PASSWORD_METHOD = 'pbkdf2:sha256:600000'
HASH_PREFIXES = ('scrypt:', 'pbkdf2:')


def hash_password(secret: str) -> str:
    # 22 salt characters give the 128 bits SP 800-132 asks for (16 give ~95)
    return generate_password_hash(secret, method=PASSWORD_METHOD, salt_length=22)


def verify_password(stored: str, secret: str) -> bool:
    """False, never an exception, when the hash cannot be checked: a FIPS
    provider refuses scrypt, and a malformed hash names no method."""
    if not stored or not isinstance(secret, str):
        return False
    try:
        return check_password_hash(stored, secret)
    except (ValueError, TypeError) as e:
        logger.warning("Password hash (%s) cannot be verified: %s; the password must be "
                       "reset", stored.split('$', 1)[0], e)
        return False


def needs_rehash(stored: str) -> bool:
    return not (stored or '').startswith(PASSWORD_METHOD + '$')
