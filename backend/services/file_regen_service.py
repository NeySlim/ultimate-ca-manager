"""
File Regeneration Service
Regenerates certificate/key files on disk from database at startup.
Ensures filesystem is consistent with database state.
"""
import base64
import logging
from pathlib import Path
from config.settings import Config
from utils.file_naming import (
    ca_cert_path, ca_key_path,
    cert_cert_path, cert_key_path, cert_csr_path,
    cleanup_old_files
)

logger = logging.getLogger(__name__)


def regenerate_all_files():
    """
    Check and regenerate all certificate/key files from database.
    Called at startup to ensure filesystem consistency.
    """
    from models import CA, Certificate

    # Ensure directories exist
    for d in [Config.CA_DIR, Config.CERT_DIR, Config.PRIVATE_DIR, Config.CRL_DIR]:
        d.mkdir(parents=True, exist_ok=True)

    stats = {'ca_certs': 0, 'ca_keys': 0, 'certs': 0, 'cert_keys': 0, 'csrs': 0, 'cleaned': 0}

    # Regenerate CA files
    for ca in CA.query.all():
        # Clean old UUID-named files
        old_cert = Config.CA_DIR / f"{ca.refid}.crt"
        old_key = Config.PRIVATE_DIR / f"ca_{ca.refid}.key"

        new_cert = ca_cert_path(ca)
        new_key = ca_key_path(ca)

        # If old file exists but new doesn't, rename
        if old_cert.exists() and not new_cert.exists() and old_cert != new_cert:
            old_cert.rename(new_cert)
            stats['cleaned'] += 1
        if old_key.exists() and not new_key.exists() and old_key != new_key:
            old_key.rename(new_key)
            stats['cleaned'] += 1

        # Regenerate from DB if file missing
        if not new_cert.exists() and ca.crt:
            try:
                cert_pem = base64.b64decode(ca.crt)
                new_cert.write_bytes(cert_pem)
                stats['ca_certs'] += 1
            except Exception as e:
                logger.warning(f"Failed to regenerate CA cert {ca.descr}: {e}")

        if not new_key.exists() and ca.prv:
            try:
                from security.encryption import decrypt_private_key
                prv_decrypted = decrypt_private_key(ca.prv)
                key_pem = base64.b64decode(prv_decrypted)
                new_key.write_bytes(key_pem)
                new_key.chmod(0o600)
                stats['ca_keys'] += 1
            except Exception as e:
                logger.warning(f"Failed to regenerate CA key {ca.descr}: {e}")

    # Regenerate certificate files
    for cert in Certificate.query.all():
        old_cert = Config.CERT_DIR / f"{cert.refid}.crt"
        old_csr = Config.CERT_DIR / f"{cert.refid}.csr"
        old_key = Config.PRIVATE_DIR / f"cert_{cert.refid}.key"

        new_cert = cert_cert_path(cert)
        new_csr = cert_csr_path(cert)
        new_key = cert_key_path(cert)

        # Rename old to new if needed
        if old_cert.exists() and not new_cert.exists() and old_cert != new_cert:
            old_cert.rename(new_cert)
            stats['cleaned'] += 1
        if old_csr.exists() and not new_csr.exists() and old_csr != new_csr:
            old_csr.rename(new_csr)
            stats['cleaned'] += 1
        if old_key.exists() and not new_key.exists() and old_key != new_key:
            old_key.rename(new_key)
            stats['cleaned'] += 1

        # Regenerate from DB if missing
        if not new_cert.exists() and cert.crt:
            try:
                cert_pem = base64.b64decode(cert.crt)
                new_cert.write_bytes(cert_pem)
                stats['certs'] += 1
            except Exception as e:
                logger.warning(f"Failed to regenerate cert {cert.descr}: {e}")

        if not new_csr.exists() and cert.csr:
            try:
                csr_data = cert.csr
                if csr_data.startswith('-----BEGIN'):
                    csr_bytes = csr_data.encode('utf-8')
                else:
                    csr_bytes = base64.b64decode(csr_data)
                new_csr.write_bytes(csr_bytes)
                stats['csrs'] += 1
            except Exception as e:
                logger.warning(f"Failed to regenerate CSR {cert.descr}: {e}")

        if not new_key.exists() and cert.prv:
            try:
                from security.encryption import decrypt_private_key
                prv_decrypted = decrypt_private_key(cert.prv)
                key_pem = base64.b64decode(prv_decrypted)
                new_key.write_bytes(key_pem)
                new_key.chmod(0o600)
                stats['cert_keys'] += 1
            except Exception as e:
                logger.warning(f"Failed to regenerate cert key {cert.descr}: {e}")

    total = sum(stats.values())
    if total > 0:
        logger.info(f"File regeneration: {stats}")
    else:
        logger.info("File regeneration: all files up to date")

    return stats
