"""
CA export operations
"""
import base64
import logging
from typing import Dict

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA
from services.trust_store import TrustStoreService
from .ca_operations import CAOperationsMixin
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAExportMixin:
    """CA export operations"""

    @staticmethod
    def export_ca(ca_id: int, format: str = 'pem') -> bytes:
        """
        Export CA certificate.

        Args:
            ca_id: CA ID
            format: Export format (pem, der)

        Returns:
            Certificate bytes

        Raises:
            ValueError: If CA not found or unsupported format
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        cert_pem = get_ca_cert_pem(ca)

        if format == 'pem':
            return cert_pem
        elif format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)
        else:
            raise ValueError(f"Unsupported format: {format}")

    @staticmethod
    def export_ca_with_options(
        ca_id: int,
        export_format: str = 'pem',
        include_key: bool = False,
        include_chain: bool = False,
        password: str = None
    ) -> bytes:
        """
        Export CA with multiple format options.

        Args:
            ca_id: CA ID
            export_format: pem, der, pkcs12
            include_key: Include private key (PEM only)
            include_chain: Include certificate chain (PEM only)
            password: Password for PKCS#12

        Returns:
            Export bytes

        Raises:
            ValueError: If CA not found, no private key, or unsupported format
        """
        from security.encryption import decrypt_private_key

        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        cert_pem = get_ca_cert_pem(ca)

        if export_format == 'pkcs12':
            if not password:
                raise ValueError("Password required for PKCS#12 export")
            if not ca.prv:
                raise ValueError("CA has no private key")

            # Decrypt private key
            prv_decrypted = decrypt_private_key(ca.prv)
            key_pem = base64.b64decode(prv_decrypted)
            return TrustStoreService.export_pkcs12(
                cert_pem, key_pem, password, ca.descr
            )

        elif export_format == 'der':
            cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
            return cert.public_bytes(serialization.Encoding.DER)

        elif export_format == 'pem':
            result = cert_pem

            if include_key and ca.prv:
                # Decrypt private key
                prv_decrypted = decrypt_private_key(ca.prv)
                key_pem = base64.b64decode(prv_decrypted)
                result += b'\n' + key_pem

            if include_chain:
                chain = CAOperationsMixin.get_ca_chain(ca_id)
                # Skip first cert (already included)
                for chain_cert in chain[1:]:
                    result += b'\n' + chain_cert

            return result

        else:
            raise ValueError(f"Unsupported format: {export_format}")

    @staticmethod
    def get_ca_fingerprints(ca_id: int) -> Dict[str, str]:
        """
        Get CA certificate fingerprints.

        Args:
            ca_id: CA ID

        Returns:
            Dictionary with sha256, sha1, md5 fingerprints

        Raises:
            ValueError: If CA not found
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        cert_pem = get_ca_cert_pem(ca)
        return TrustStoreService.get_certificate_fingerprints(cert_pem)

    @staticmethod
    def get_ca_details(ca_id: int) -> Dict:
        """
        Get detailed CA certificate information.

        Args:
            ca_id: CA ID

        Returns:
            Detailed certificate information

        Raises:
            ValueError: If CA not found
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        cert_pem = get_ca_cert_pem(ca)
        details = TrustStoreService.parse_certificate_details(cert_pem)
        details['fingerprints'] = TrustStoreService.get_certificate_fingerprints(cert_pem)
        details['has_private_key'] = bool(ca.prv and len(ca.prv) > 0)

        return details
