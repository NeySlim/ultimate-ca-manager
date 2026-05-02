"""Certificate import and export mixin"""
import base64
import json
import logging
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import db, CA, Certificate
from services.trust_store import TrustStoreService
from utils.file_naming import cert_cert_path, cert_key_path

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


class ImportExportMixin:

    @staticmethod
    def import_certificate(
        descr: str,
        cert_pem: str,
        key_pem: Optional[str] = None,
        username: str = 'system',
        source: str = None,
        chain_pem: str = None
    ) -> Certificate:
        """
        Import an existing certificate

        Args:
            descr: Description
            cert_pem: Certificate PEM
            key_pem: Optional private key PEM
            username: User importing
            source: Import source identifier
            chain_pem: Optional CA chain PEM to append

        Returns:
            Certificate instance
        """
        # Parse certificate
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode() if isinstance(cert_pem, str) else cert_pem,
            default_backend()
        )

        # Extract key algorithm info
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        pub_key = cert.public_key()
        if isinstance(pub_key, rsa.RSAPublicKey):
            key_algo = f"RSA {pub_key.key_size}"
        elif isinstance(pub_key, ec.EllipticCurvePublicKey):
            key_algo = f"EC {pub_key.curve.name}"
        elif isinstance(pub_key, (ed25519.Ed25519PublicKey, ed448.Ed448PublicKey)):
            key_algo = "EdDSA"
        else:
            key_algo = "Unknown"

        # Extract signature algorithm
        sig_algo = cert.signature_algorithm_oid._name if hasattr(cert.signature_algorithm_oid, '_name') else str(cert.signature_algorithm_oid.dotted_string)

        # Extract SANs from certificate
        san_dns_list = []
        san_ip_list = []
        san_email_list = []
        san_uri_list = []

        try:
            ext = cert.extensions.get_extension_for_oid(x509.oid.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in ext.value:
                if isinstance(name, x509.DNSName):
                    san_dns_list.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    san_ip_list.append(str(name.value))
                elif isinstance(name, x509.RFC822Name):
                    san_email_list.append(name.value)
                elif isinstance(name, x509.UniformResourceIdentifier):
                    san_uri_list.append(name.value)
        except x509.ExtensionNotFound:
            pass  # No SAN extension

        # Extract CN for subject_cn
        cn_attrs = cert.subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        subject_cn = cn_attrs[0].value if cn_attrs else None

        # Create certificate record - include chain in crt if provided
        full_cert = cert_pem
        if chain_pem:
            full_cert = cert_pem.strip() + '\n' + chain_pem.strip()

        certificate = Certificate(
            refid=__import__('uuid').uuid4().__str__(),
            descr=descr,
            crt=base64.b64encode(full_cert.encode() if isinstance(full_cert, str) else full_cert).decode('utf-8'),
            prv=base64.b64encode(key_pem.encode()).decode('utf-8') if key_pem else None,
            subject=cert.subject.rfc4514_string(),
            subject_cn=subject_cn,
            issuer=cert.issuer.rfc4514_string(),
            serial_number=str(cert.serial_number),
            valid_from=cert.not_valid_before_utc,
            valid_to=cert.not_valid_after_utc,
            key_algo=key_algo,
            # Store extracted SANs
            san_dns=json.dumps(san_dns_list) if san_dns_list else None,
            san_ip=json.dumps(san_ip_list) if san_ip_list else None,
            san_email=json.dumps(san_email_list) if san_email_list else None,
            san_uri=json.dumps(san_uri_list) if san_uri_list else None,
            imported_from='manual' if not source else source,
            source=source,
            created_by=username
        )

        db.session.add(certificate)
        db.session.commit()

        # Audit log
        from services.audit_service import AuditService
        AuditService.log_certificate('cert_imported', certificate, f'Imported certificate: {descr}')

        # Save files
        cert_path = cert_cert_path(certificate)
        with open(cert_path, 'wb') as f:
            f.write(cert_pem.encode() if isinstance(cert_pem, str) else cert_pem)

        if key_pem:
            key_path = cert_key_path(certificate)
            with open(key_path, 'wb') as f:
                f.write(key_pem.encode() if isinstance(key_pem, str) else key_pem)
            key_path.chmod(0o600)

        return certificate

    @staticmethod
    def export_certificate(
        cert_id: int,
        format: str = 'pem',
        password: Optional[str] = None
    ) -> bytes:
        """
        Export certificate

        Args:
            cert_id: Certificate ID
            format: pem, der, or pkcs12
            password: Password for PKCS#12 (required if format=pkcs12)

        Returns:
            Certificate bytes
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.crt:
            raise ValueError("Certificate not yet signed")

        cert_pem = base64.b64decode(certificate.crt)

        if format == 'pem':
            return cert_pem
        elif format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        elif format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not certificate.prv:
                raise ValueError("Certificate has no private key")

            key_pem = base64.b64decode(decrypt_private_key(certificate.prv))
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, certificate.descr
            )
        else:
            raise ValueError(f"Unsupported format: {format}")

    @staticmethod
    def export_certificate_with_options(
        cert_id: int,
        export_format: str = 'pem',
        include_key: bool = False,
        include_chain: bool = False,
        password: Optional[str] = None
    ) -> bytes:
        """
        Export certificate with multiple format options

        Args:
            cert_id: Certificate ID
            export_format: pem, der, pkcs12
            include_key: Include private key (PEM only)
            include_chain: Include CA chain (PEM only)
            password: Password for PKCS#12

        Returns:
            Export bytes
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.crt:
            raise ValueError("Certificate not yet signed")

        cert_pem = base64.b64decode(certificate.crt)

        if export_format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not certificate.prv:
                raise ValueError("Certificate has no private key")

            key_pem = base64.b64decode(decrypt_private_key(certificate.prv))
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, certificate.descr
            )

        elif export_format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)

        elif export_format == 'pem':
            result = cert_pem

            if include_key and certificate.prv:
                key_pem = base64.b64decode(decrypt_private_key(certificate.prv))
                # Ensure proper newline separation
                if not result.endswith(b'\n'):
                    result += b'\n'
                result += key_pem

            if include_chain and certificate.caref:
                # Get CA chain
                ca = CA.query.filter_by(refid=certificate.caref).first()
                if ca:
                    from services.ca_service import CAService
                    chain = CAService.get_ca_chain(ca.id)
                    for chain_cert in chain:
                        # Ensure proper newline separation
                        if not result.endswith(b'\n'):
                            result += b'\n'
                        result += chain_cert

            return result

        else:
            raise ValueError(f"Unsupported format: {export_format}")
