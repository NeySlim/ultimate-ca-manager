import logging
from typing import Optional

from models import CA
from models.crl import CRLMetadata
from .generation import CRLGenerationMixin

logger = logging.getLogger(__name__)


class CRLManagementMixin:

    @staticmethod
    def update_crl(ca_id: int, username: str = 'system') -> CRLMetadata:
        return CRLGenerationMixin.generate_crl(ca_id, username=username)

    @staticmethod
    def auto_generate_on_revocation(ca_id: int, username: str = 'system') -> Optional[CRLMetadata]:
        ca = CA.query.get(ca_id)
        if not ca:
            return None

        if not ca.cdp_enabled:
            return None

        return CRLGenerationMixin.generate_crl(ca_id, username=username)
