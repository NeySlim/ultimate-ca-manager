"""CSR generation and signing mixin"""
import base64
import uuid
import json
import logging
from typing import Dict, List, Optional

from cryptography import x509
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate
from services.trust_store import TrustStoreService
from utils.file_naming import cert_cert_path, cert_key_path, cert_csr_path, ca_cert_path, ca_key_path

logger = logging.getLogger(__name__)

try:
    from security.encryption import decrypt_private_key, encrypt_private_key
    HAS_ENCRYPTION = True
except ImportError:
    HAS_ENCRYPTION = False

    def decrypt_private_key(data):
        return data

    def encrypt_private_key(data):
        return data


class CSRMixin:

    @staticmethod
    def generate_csr(
        descr: str,
        dn: Dict[str, str],
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        username: str = 'system'
    ) -> Certificate:
        """
        Generate a Certificate Signing Request

        Args:
            descr: Description
            dn: Distinguished Name
            key_type: Key type
            digest: Hash algorithm
            san_dns: DNS SANs
            san_ip: IP SANs
            san_email: Email SANs
            san_uri: URI SANs
            username: User generating CSR

        Returns:
            Certificate record with CSR
        """
        # Build subject
        subject = TrustStoreService.build_subject(dn)

        # Generate CSR
        csr_pem, key_pem = TrustStoreService.generate_csr(
            subject=subject,
            key_type=key_type,
            digest=digest,
            san_dns=san_dns,
            san_ip=san_ip,
            san_email=san_email,
            san_uri=san_uri
        )

        # Parse CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())

        # Create certificate record (CSR only, no cert yet)
        certificate = Certificate(
            refid=str(uuid.uuid4()),
            descr=descr,
            caref=None,  # Not signed yet
            csr=base64.b64encode(csr_pem).decode('utf-8'),
            prv=base64.b64encode(key_pem).decode('utf-8'),
            subject=csr.subject.rfc4514_string(),
            san_dns=json.dumps(san_dns) if san_dns else None,
            san_ip=json.dumps(san_ip) if san_ip else None,
            san_email=json.dumps(san_email) if san_email else None,
            san_uri=json.dumps(san_uri) if san_uri else None,
            imported_from='csr_generated',
            created_by=username
        )

        db.session.add(certificate)
        db.session.commit()

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_csr('csr_generated', certificate, f'Generated CSR: {descr}')

        # Save files
        csr_path = cert_csr_path(certificate)
        with open(csr_path, 'wb') as f:
            f.write(csr_pem)

        key_path = cert_key_path(certificate)
        with open(key_path, 'wb') as f:
            f.write(key_pem)
        key_path.chmod(0o600)

        return certificate

    @staticmethod
    def sign_csr(
        cert_id: int,
        caref: str,
        cert_type: str = 'server_cert',
        validity_days: int = 397,
        digest: str = 'sha256',
        username: str = 'system',
        extra_ekus: list = None,
    ) -> Certificate:
        """
        Sign a CSR with a CA

        Args:
            cert_id: Certificate ID (with CSR)
            caref: CA refid to sign with
            cert_type: Certificate type
            validity_days: Validity in days
            digest: Hash algorithm
            username: User signing
            extra_ekus: Additional EKU OIDs

        Returns:
            Updated Certificate with signed cert (or new CA record for intermediate_ca)
        """
        # Get certificate with CSR
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.csr:
            raise ValueError("Certificate has no CSR")

        if certificate.crt:
            raise ValueError("Certificate already signed")

        # Get CA
        ca = CA.query.filter_by(refid=caref).first()
        if not ca:
            raise ValueError(f"CA not found: {caref}")

        if not ca.has_private_key:
            raise ValueError("CA has no private key")

        # Load CA cert and key
        ca_cert_pem = base64.b64decode(ca.crt)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        from services.hsm.ca_key_loader import get_ca_signing_key
        ca_private_key = get_ca_signing_key(ca)

        # Load CSR - handle both raw PEM and base64-encoded PEM
        csr_data = certificate.csr
        if csr_data.startswith('-----BEGIN'):
            csr_pem = csr_data.encode('utf-8')
        else:
            csr_pem = base64.b64decode(csr_data)

        # Sign CSR
        cdp_urls = [url.replace('{ca_refid}', ca.refid) for url in ca.get_cdp_urls()] if ca.cdp_enabled else None
        ocsp_urls = ca.get_ocsp_urls() if ca.ocsp_enabled else None
        aia_ca_issuers_urls = [url.replace('{ca_refid}', ca.refid) for url in ca.get_aia_urls()] if ca.aia_ca_issuers_enabled else None
        cps_uri = ca.cps_uri if ca.cps_enabled and ca.cps_uri else None
        cps_oid = ca.cps_oid if cps_uri else None
        cert_pem = TrustStoreService.sign_csr(
            csr_pem=csr_pem,
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            validity_days=validity_days,
            digest=digest,
            cert_type=cert_type,
            cdp_urls=cdp_urls,
            ocsp_urls=ocsp_urls,
            aia_ca_issuers_urls=aia_ca_issuers_urls,
            cps_uri=cps_uri,
            cps_oid=cps_oid,
            ocsp_must_staple=getattr(certificate, 'ocsp_must_staple', False) or False,
            extra_ekus=extra_ekus,
        )

        # Parse signed certificate
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())

        # Extract subject and SANs
        subject_str = cert.subject.rfc4514_string() if cert.subject else None

        # Extract CN from subject
        cn_value = None
        if subject_str:
            for part in subject_str.split(','):
                if part.strip().upper().startswith('CN='):
                    cn_value = part.strip()[3:]
                    break

        # Extract SANs
        san_dns_list = []
        san_ip_list = []
        san_email_list = []
        try:
            san_ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    san_dns_list.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    san_ip_list.append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    san_email_list.append(name.value)
        except x509.ExtensionNotFound:
            pass

        # Fallback: use first SAN DNS as CN for sorting if no CN in subject
        if not cn_value and san_dns_list:
            cn_value = san_dns_list[0]
        if not cn_value and certificate.descr:
            cn_value = certificate.descr

        # Update certificate record
        certificate.caref = caref
        certificate.crt = base64.b64encode(cert_pem).decode('utf-8')
        certificate.cert_type = cert_type
        certificate.subject = subject_str if subject_str else None
        certificate.subject_cn = cn_value
        certificate.issuer = cert.issuer.rfc4514_string()
        certificate.serial_number = str(cert.serial_number)
        certificate.valid_from = cert.not_valid_before
        certificate.valid_to = cert.not_valid_after

        # Store SANs
        if san_dns_list:
            certificate.san_dns = json.dumps(san_dns_list)
        if san_ip_list:
            certificate.san_ip = json.dumps(san_ip_list)
        if san_email_list:
            certificate.san_email = json.dumps(san_email_list)

        # Increment CA serial
        ca.serial = (ca.serial or 0) + 1

        # If signing as intermediate CA, create a CA record
        new_ca = None
        if cert_type == 'intermediate_ca':
            # Get private key from the CSR certificate record (if it was generated in UCM)
            prv = certificate.prv if certificate.prv else None

            # Extract SKI from signed cert
            ski_hex = None
            try:
                ski_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_KEY_IDENTIFIER)
                ski_hex = ski_ext.value.digest.hex(':')
            except x509.ExtensionNotFound:
                pass

            # Extract pathLength from BasicConstraints
            path_length = None
            try:
                bc_ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.BASIC_CONSTRAINTS)
                path_length = bc_ext.value.path_length
            except x509.ExtensionNotFound:
                pass

            new_ca = CA(
                refid=str(uuid.uuid4()),
                descr=certificate.descr or cn_value or 'Intermediate CA',
                crt=base64.b64encode(cert_pem).decode('utf-8'),
                prv=prv,
                serial=0,
                caref=caref,
                subject=subject_str,
                issuer=cert.issuer.rfc4514_string(),
                serial_number=str(cert.serial_number),
                ski=ski_hex,
                valid_from=cert.not_valid_before,
                valid_to=cert.not_valid_after,
                path_length=path_length,
                imported_from='csr_signed',
                created_by=username,
            )
            db.session.add(new_ca)

            # Remove the certificate record — it's now a CA
            db.session.delete(certificate)

        db.session.commit()

        # Audit log with centralized service
        from services.audit_service import AuditService
        if new_ca:
            AuditService.log_ca('ca_created', new_ca, f'Intermediate CA created from signed CSR: {new_ca.descr}')
            # Save CA cert file
            ca_path = ca_cert_path(new_ca)
            with open(ca_path, 'wb') as f:
                f.write(cert_pem)
            if new_ca.prv:
                key_path = ca_key_path(new_ca)
                key_data = base64.b64decode(decrypt_private_key(new_ca.prv))
                with open(key_path, 'wb') as f:
                    f.write(key_data)
                key_path.chmod(0o600)
            return new_ca
        else:
            AuditService.log_certificate('csr_signed', certificate, f'Signed CSR: {certificate.descr}')
            # Save signed certificate
            cert_path = cert_cert_path(certificate)
            with open(cert_path, 'wb') as f:
                f.write(cert_pem)
            return certificate
