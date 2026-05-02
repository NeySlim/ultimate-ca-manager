"""Certificate inspection mixin — fingerprints, details, email validation"""
import re
import base64
import logging
from typing import Dict

from cryptography.hazmat.backends import default_backend

from models import Certificate
from services.trust_store import TrustStoreService

logger = logging.getLogger(__name__)

# RFC 5322 simplified email validation regex
EMAIL_REGEX = re.compile(
    r'^[a-zA-Z0-9.!#$%&\'*+\/=?^_`{|}~-]+'
    r'@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?'
    r'(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$'
)


class InspectionMixin:

    @staticmethod
    def validate_email(email: str) -> bool:
        """Validate email address against RFC 5322 (simplified)"""
        if not email or not isinstance(email, str):
            return False
        return bool(EMAIL_REGEX.match(email.strip()))

    @staticmethod
    def get_certificate_fingerprints(cert_id: int) -> Dict[str, str]:
        """
        Get certificate fingerprints

        Args:
            cert_id: Certificate ID

        Returns:
            Dictionary with sha256, sha1, md5 fingerprints
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.crt:
            raise ValueError("Certificate not yet signed")

        cert_pem = base64.b64decode(certificate.crt)
        return TrustStoreService.get_certificate_fingerprints(cert_pem)

    @staticmethod
    def get_certificate_details(cert_id: int) -> Dict:
        """
        Get detailed certificate information

        Args:
            cert_id: Certificate ID

        Returns:
            Detailed certificate information
        """
        certificate = Certificate.query.get(cert_id)
        if not certificate:
            raise ValueError("Certificate not found")

        if not certificate.crt:
            raise ValueError("Certificate not yet signed")

        cert_pem = base64.b64decode(certificate.crt)
        details = TrustStoreService.parse_certificate_details(cert_pem)
        details['fingerprints'] = TrustStoreService.get_certificate_fingerprints(cert_pem)
        details['has_private_key'] = bool(certificate.prv and len(certificate.prv) > 0)
        details['revoked'] = certificate.revoked

        return details
