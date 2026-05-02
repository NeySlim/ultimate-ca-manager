"""Certificate query helpers mixin — simple DB lookups"""
import logging
from typing import List, Optional

from models import Certificate

logger = logging.getLogger(__name__)


class QueryMixin:

    @staticmethod
    def list_certificates(caref: Optional[str] = None) -> List[Certificate]:
        """List all certificates, optionally filtered by CA"""
        query = Certificate.query
        if caref:
            query = query.filter_by(caref=caref)
        return query.order_by(Certificate.created_at.desc()).all()

    @staticmethod
    def get_certificate(cert_id: int) -> Optional[Certificate]:
        """Get certificate by ID"""
        return Certificate.query.get(cert_id)
