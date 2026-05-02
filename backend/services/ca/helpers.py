"""
Common helpers for CA service
"""
import base64
import logging
from pathlib import Path

from config.settings import Config
from utils.file_naming import ca_cert_path, ca_key_path, cleanup_old_files

logger = logging.getLogger(__name__)


def save_ca_files(ca, cert_pem: bytes, key_pem: bytes = None) -> None:
    """
    Save CA certificate and private key to filesystem.

    Args:
        ca: CA model instance
        cert_pem: Certificate in PEM bytes
        key_pem: Optional private key in PEM bytes (None for HSM-backed CAs)
    """
    # Save certificate
    cert_path = ca_cert_path(ca)
    try:
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem)
    except Exception as e:
        logger.error(f"Failed to save CA certificate file: {e}")
        raise

    # Save private key (skip for HSM-backed CAs)
    if key_pem is not None:
        key_path = ca_key_path(ca)
        try:
            with open(key_path, 'wb') as f:
                f.write(key_pem)
            key_path.chmod(0o600)
        except Exception as e:
            logger.error(f"Failed to save CA private key file: {e}")
            raise


def delete_ca_files(ca) -> None:
    """
    Delete CA certificate and private key files from filesystem.
    Handles both old UUID-based and new refid-based naming.

    Args:
        ca: CA model instance
    """
    cleanup_old_files(ca=ca)

    cert_path = ca_cert_path(ca)
    key_path = ca_key_path(ca)

    if cert_path.exists():
        try:
            cert_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete CA cert file: {e}")

    if key_path.exists():
        try:
            key_path.unlink()
        except Exception as e:
            logger.warning(f"Failed to delete CA key file: {e}")


def get_ca_cert_pem(ca) -> bytes:
    """Get CA certificate as PEM bytes"""
    if ca.crt:
        return base64.b64decode(ca.crt)
    return b''


def get_ca_private_key_pem(ca, decrypted: bool = False) -> bytes:
    """
    Get CA private key as PEM bytes.

    Args:
        ca: CA model instance
        decrypted: If True, key is already decrypted

    Returns:
        Private key PEM bytes or None
    """
    if not ca.prv:
        return None

    key_data = ca.prv
    if not decrypted:
        from security.encryption import decrypt_private_key
        key_data = decrypt_private_key(key_data)

    return base64.b64decode(key_data)
