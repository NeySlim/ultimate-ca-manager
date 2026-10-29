"""
CA export operations
"""
import logging
from typing import Dict

from models import db, CA
from services.trust_store import TrustStoreService
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAExportMixin:
    """CA export operations"""

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
        ca = db.session.get(CA, ca_id)
        if not ca:
            raise ValueError("CA not found")

        cert_pem = get_ca_cert_pem(ca)
        details = TrustStoreService.parse_certificate_details(cert_pem)
        details['fingerprints'] = TrustStoreService.get_certificate_fingerprints(cert_pem)
        details['has_private_key'] = bool(ca.prv and len(ca.prv) > 0)

        return details
