"""
ACME Protocol Service Layer
Implements RFC 8555 - Automatic Certificate Management Environment (ACME)
"""
import logging
from typing import Dict

from .mixins.nonce import NonceMixin
from .mixins.account import AccountMixin
from .mixins.order import OrderMixin
from .mixins.challenge import ChallengeMixin
from .mixins.issuance import IssuanceMixin
from .mixins.crypto import CryptoMixin
from .mixins.eab import EabMixin

logger = logging.getLogger(__name__)


class AcmeService(NonceMixin, AccountMixin, OrderMixin, ChallengeMixin, IssuanceMixin, CryptoMixin, EabMixin):
    """ACME Protocol Service implementing RFC 8555"""

    DIRECTORY_URLS = {
        "newNonce": "/acme/new-nonce",
        "newAccount": "/acme/new-account",
        "newOrder": "/acme/new-order",
        "newAuthz": "/acme/new-authz",
        "revokeCert": "/acme/revoke-cert",
        "keyChange": "/acme/key-change",
    }

    SUPPORTED_CHALLENGES = ["http-01", "dns-01", "tls-alpn-01"]

    def __init__(self, base_url: str = "https://localhost:8443"):
        """Initialize ACME service

        Args:
            base_url: Base URL for ACME endpoints (e.g., https://ucm.local:8443)
        """
        self.base_url = base_url.rstrip('/')

    def get_directory(self) -> Dict[str, str]:
        """Get ACME directory (RFC 8555 Section 7.1.1)

        Returns:
            Dictionary of ACME endpoints
        """
        return {
            key: f"{self.base_url}{path}"
            for key, path in self.DIRECTORY_URLS.items()
        }
