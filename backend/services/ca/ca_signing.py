"""
CA CSR signing operations
"""
import base64
import json
import logging
import uuid
from typing import Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA, Certificate, db
from services.audit_service import AuditService
from services.trust_store import TrustStoreService
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAOfflineError(Exception):
    """Raised when an operation is attempted on an offline CA."""
    pass


class CASigningMixin:
    """CA CSR signing operations"""

    @staticmethod
    def _check_ca_offline(ca: CA) -> None:
        """Raise CAOfflineError if the CA is offline."""
        if ca.offline:
            raise CAOfflineError(
                f"CA '{ca.descr}' is offline: {ca.offline_reason or 'no reason provided'}"
            )

    @staticmethod
    def sign_csr_from_crypto(
        ca: CA,
        csr: x509.CertificateSigningRequest,
        validity_days: int = 365,
        source: str = 'manual',
        renewal_of: x509.Certificate = None,
    ) -> Tuple[str, str]:
        """
        Sign a CSR (x509 object) using a CA.
        Bridge between EST/auto-renewal and TrustStoreService.sign_csr().

        Args:
            ca: CA model instance
            csr: x509 CertificateSigningRequest object
            validity_days: Certificate validity in days
            source: Origin of the request (est, auto-renewal, etc.)

        Returns:
            Tuple of (cert_pem_string, serial_number_string)
        """
        CASigningMixin._check_ca_offline(ca)

        # Convert CSR object to PEM bytes
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        # Load CA cert and key (local or HSM-backed)
        ca_cert_pem = get_ca_cert_pem(ca)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        # Resolve CDP/OCSP/AIA URLs
        cdp_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_cdp_urls()] if ca.cdp_enabled else None
        ocsp_urls = ca.get_ocsp_urls() if ca.ocsp_enabled else None
        aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.url_ref) for url in ca.get_aia_urls()] if ca.aia_ca_issuers_enabled else None
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None

        # Sign via TrustStoreService
        cert_pem_bytes = TrustStoreService.sign_csr(
            csr_pem=csr_pem,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            validity_days=validity_days,
            digest='sha256',
            cdp_urls=cdp_urls,
            ocsp_urls=ocsp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            renewal_of=renewal_of,
        )

        # Extract serial number
        cert_obj = x509.load_pem_x509_certificate(
            cert_pem_bytes if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes.encode(),
            default_backend()
        )
        serial = format(cert_obj.serial_number, 'X')  # legacy hex form, kept for return tuple
        serial_decimal = str(cert_obj.serial_number)  # canonical DB form

        # Store certificate in database
        cert_pem_str = cert_pem_bytes.decode('utf-8') if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes

        # Extract CN
        cn = ''
        try:
            cn = csr.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        except (IndexError, Exception):
            cn = csr.subject.rfc4514_string()

        cert_pem_raw = cert_pem_bytes if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes.encode()

        # Extract AKI/SKI
        cert_aki = ''
        cert_ski = ''
        try:
            aki_ext = cert_obj.extensions.get_extension_for_oid(x509.oid.ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if aki_ext.value.key_identifier:
                cert_aki = ':'.join(f'{b:02x}' for b in aki_ext.value.key_identifier)
        except x509.ExtensionNotFound:
            pass
        try:
            ski_ext = cert_obj.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            if ski_ext.value.digest:
                cert_ski = ':'.join(f'{b:02x}' for b in ski_ext.value.digest)
        except x509.ExtensionNotFound:
            pass

        # Extract SANs
        san_dns, san_ip, san_email = [], [], []
        try:
            san_ext = cert_obj.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            san_dns = list(san_ext.value.get_values_for_type(x509.DNSName))
            san_ip = [str(n) for n in san_ext.value.get_values_for_type(x509.IPAddress)]
            san_email = list(san_ext.value.get_values_for_type(x509.RFC822Name))
        except x509.ExtensionNotFound:
            pass

        not_before = cert_obj.not_valid_before_utc if hasattr(cert_obj, 'not_valid_before_utc') else cert_obj.not_valid_before
        not_after = cert_obj.not_valid_after_utc if hasattr(cert_obj, 'not_valid_after_utc') else cert_obj.not_valid_after

        new_cert = Certificate(
            refid=str(uuid.uuid4())[:8],
            descr=cn,
            caref=ca.refid,
            crt=base64.b64encode(cert_pem_raw).decode(),
            csr=base64.b64encode(csr_pem).decode(),
            cert_type='server',
            subject=cert_obj.subject.rfc4514_string(),
            subject_cn=cn,
            issuer=cert_obj.issuer.rfc4514_string(),
            serial_number=serial_decimal,
            aki=cert_aki,
            ski=cert_ski,
            valid_from=not_before,
            valid_to=not_after,
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            source=source,
        )
        db.session.add(new_cert)

        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ca/ca_signing.py:168: {_commit_err}", exc_info=True)
            raise

        logger.info(f"Signed CSR via {source}: CN={cn}, serial={serial}, CA={ca.descr}")

        # Renewal flows pass source like '<orig>-renewal'; everything else
        # (EST enrollment, etc.) is a fresh issuance.
        from services.webhook_service import emit_cert_renewed, emit_cert_issued
        if 'renewal' in (source or ''):
            emit_cert_renewed(new_cert.to_dict(), ca_refid=ca.refid)
        else:
            emit_cert_issued(new_cert.to_dict(), ca_refid=ca.refid)

        return cert_pem_str, serial
