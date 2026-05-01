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
from .helpers import get_ca_cert_pem, get_ca_private_key_pem

logger = logging.getLogger(__name__)


class CASigningMixin:
    """CA CSR signing operations"""

    @staticmethod
    def sign_csr_from_crypto(
        ca: CA,
        csr: x509.CertificateSigningRequest,
        validity_days: int = 365,
        source: str = 'manual'
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
        from security.encryption import decrypt_private_key

        # Convert CSR object to PEM bytes
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)

        # Load CA cert and key
        ca_cert_pem = get_ca_cert_pem(ca)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        ca_prv_decrypted = decrypt_private_key(ca.prv)
        ca_key_pem = base64.b64decode(ca_prv_decrypted)
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem, password=None, backend=default_backend()
        )

        # Resolve CDP/OCSP/AIA URLs
        cdp_urls = [url.replace('{ca_refid}', ca.refid or '') for url in ca.get_cdp_urls()] if ca.cdp_enabled else None
        ocsp_urls = ca.get_ocsp_urls() if ca.ocsp_enabled else None
        aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.refid or '') for url in ca.get_aia_urls()] if ca.aia_ca_issuers_enabled else None
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
        )

        # Extract serial number
        cert_obj = x509.load_pem_x509_certificate(
            cert_pem_bytes if isinstance(cert_pem_bytes, bytes) else cert_pem_bytes.encode(),
            default_backend()
        )
        serial = format(cert_obj.serial_number, 'X')

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
            san_dns = [n.value for n in san_ext.value.get_values_for_type(x509.DNSName)]
            san_ip = [str(n) for n in san_ext.value.get_values_for_type(x509.IPAddress)]
            san_email = [n.value for n in san_ext.value.get_values_for_type(x509.RFC822Name)]
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
            serial_number=serial,
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
        db.session.commit()

        logger.info(f"Signed CSR via {source}: CN={cn}, serial={serial}, CA={ca.descr}")

        return cert_pem_str, serial
