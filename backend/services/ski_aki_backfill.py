"""
SKI/AKI Backfill Task - Populate missing Subject/Authority Key Identifiers

Runs once at startup to extract SKI/AKI from stored certificates.
Handles migration from older versions that didn't store these fields.
After backfill completes, subsequent runs are no-ops (fast check).
"""
import base64
import logging
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

logger = logging.getLogger(__name__)


def backfill_ski_aki():
    """Extract and store SKI/AKI for all certs/CAs missing them."""
    from models import db, CA, Certificate

    updated_cas = 0
    updated_certs = 0

    # --- CAs: populate SKI ---
    cas = CA.query.filter(
        CA.crt.isnot(None),
        CA.ski.is_(None)
    ).all()

    for ca in cas:
        try:
            pem = base64.b64decode(ca.crt)
            if isinstance(pem, bytes):
                pem_str = pem.decode('utf-8')
            else:
                pem_str = pem
            cert_obj = x509.load_pem_x509_certificate(pem_str.encode(), default_backend())
            ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            ca.ski = ext.value.key_identifier.hex(':').upper()
            updated_cas += 1
        except Exception:
            pass  # Cert may not have SKI extension

    # --- Certificates: populate AKI + SKI ---
    certs = Certificate.query.filter(
        Certificate.crt.isnot(None),
        Certificate.aki.is_(None)
    ).all()

    for cert in certs:
        try:
            pem = base64.b64decode(cert.crt)
            if isinstance(pem, bytes):
                pem_str = pem.decode('utf-8')
            else:
                pem_str = pem
            cert_obj = x509.load_pem_x509_certificate(pem_str.encode(), default_backend())

            try:
                ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
                if ext.value.key_identifier:
                    cert.aki = ext.value.key_identifier.hex(':').upper()
            except Exception:
                pass

            try:
                ext = cert_obj.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                cert.ski = ext.value.key_identifier.hex(':').upper()
            except Exception:
                pass

            updated_certs += 1
        except Exception:
            pass

    if updated_cas or updated_certs:
        db.session.commit()
        logger.info(f"SKI/AKI backfill: updated {updated_cas} CAs, {updated_certs} certificates")
    else:
        logger.debug("SKI/AKI backfill: all records up to date")
