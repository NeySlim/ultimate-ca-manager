"""
CA CRUD operations
"""
import logging
from typing import List, Optional

from models import CA, Certificate, db
from services.audit_service import AuditService
from .helpers import delete_ca_files

logger = logging.getLogger(__name__)


class CAcrudMixin:
    """CA Create, Read, Update, Delete operations"""

    @staticmethod
    def get_ca(ca_id: int) -> Optional[CA]:
        """Get CA by ID"""
        return CA.query.get(ca_id)

    @staticmethod
    def get_ca_by_refid(refid: str) -> Optional[CA]:
        """Get CA by refid"""
        return CA.query.filter_by(refid=refid).first()

    @staticmethod
    def list_cas() -> List[CA]:
        """List all CAs, ordered by creation date descending"""
        return CA.query.order_by(CA.created_at.desc()).all()

    @staticmethod
    def delete_ca(ca_id: int, username: str = 'system') -> bool:
        """
        Delete a CA and its associated files.

        Args:
            ca_id: CA ID
            username: User deleting

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If CA is used by certificates or is parent of other CAs
        """
        ca = CA.query.get(ca_id)
        if not ca:
            return False

        # Check if CA is used by certificates
        cert_count = Certificate.query.filter_by(caref=ca.refid).count()
        if cert_count > 0:
            raise ValueError(f"CA is used by {cert_count} certificate(s)")

        # Check if CA is parent of other CAs
        child_ca_count = CA.query.filter_by(caref=ca.refid).count()
        if child_ca_count > 0:
            raise ValueError(f"CA is parent of {child_ca_count} intermediate CA(s)")

        # Delete files
        delete_ca_files(ca)

        # Audit log
        AuditService.log_ca('ca_deleted', ca, f'Deleted CA: {ca.descr}')

        # Delete from database
        db.session.delete(ca)
        db.session.commit()

        return True
