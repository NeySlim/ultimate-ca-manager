"""
Export operations mixin for TrustStoreService
"""
from typing import Optional

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.hazmat.backends import default_backend


class ExportOperationsMixin:
    """Certificate export operations mixin"""

    @staticmethod
    def export_pkcs12(
        cert_pem: bytes,
        key_pem: bytes,
        password: str,
        friendly_name: str = "Certificate"
    ) -> bytes:
        """Export certificate and key as PKCS#12."""
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        key = serialization.load_pem_private_key(
            key_pem, password=None, backend=default_backend()
        )

        p12 = pkcs12.serialize_key_and_certificates(
            friendly_name.encode(),
            key,
            cert,
            None,
            serialization.BestAvailableEncryption(password.encode())
        )

        return p12
