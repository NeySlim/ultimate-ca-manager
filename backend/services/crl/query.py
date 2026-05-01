import logging
from typing import List, Optional
from models import db, CA, Certificate
from models.crl import CRLMetadata

logger = logging.getLogger(__name__)


class CRLQueryMixin:

    @staticmethod
    def get_revoked_certificates(ca_id: int) -> List[Certificate]:
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError(f"CA with id {ca_id} not found")

        return Certificate.query.filter_by(
            caref=ca.refid,
            revoked=True
        ).all()

    @staticmethod
    def get_latest_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_crl_by_refid(ca_refid: str) -> Optional[CRLMetadata]:
        ca = CA.query.filter_by(refid=ca_refid).first()
        if not ca:
            return None
        return CRLQueryMixin.get_latest_crl(ca.id)

    @staticmethod
    def get_crl_pem(ca_refid: str) -> Optional[str]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_pem if crl else None

    @staticmethod
    def get_crl_der(ca_refid: str) -> Optional[bytes]:
        crl = CRLQueryMixin.get_latest_crl_by_refid(ca_refid)
        return crl.crl_der if crl else None

    @staticmethod
    def get_latest_delta_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=True
        ).order_by(CRLMetadata.crl_number.desc()).first()

    @staticmethod
    def get_latest_base_crl(ca_id: int) -> Optional[CRLMetadata]:
        return CRLMetadata.query.filter_by(
            ca_id=ca_id, is_delta=False
        ).order_by(CRLMetadata.crl_number.desc()).first()
