"""
Fingerprint operations mixin for TrustStoreService
"""
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from typing import Dict


class FingerprintMixin:
    """Certificate fingerprint calculation mixin"""

    @staticmethod
    def get_certificate_fingerprints(cert_pem: bytes) -> Dict[str, str]:
        """Calculate certificate fingerprints."""
        cert = x509.load_pem_x509_certificate(cert_pem, serialization.DefaultBackend())

        sha256_hash = cert.fingerprint(hashes.SHA256()).hex().upper()
        sha1_hash = cert.fingerprint(hashes.SHA1()).hex().upper()
        md5_hash = cert.fingerprint(hashes.MD5()).hex().upper()

        sha256_formatted = ':'.join(sha256_hash[i:i+2] for i in range(0, len(sha256_hash), 2))
        sha1_formatted = ':'.join(sha1_hash[i:i+2] for i in range(0, len(sha1_hash), 2))
        md5_formatted = ':'.join(md5_hash[i:i+2] for i in range(0, len(md5_hash), 2))

        return {
            'sha256': sha256_formatted,
            'sha1': sha1_formatted,
            'md5': md5_formatted
        }
