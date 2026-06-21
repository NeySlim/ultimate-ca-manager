"""
CA certificate operations (chain, serial).

CRL generation lives in ``services/crl/generation.py`` (``CRLService``);
this mixin no longer carries a local CRL implementation.
"""
import logging
from typing import List

from models import CA, db
from .helpers import get_ca_cert_pem

logger = logging.getLogger(__name__)


class CAOperationsMixin:
    """CA certificate operations"""

    @staticmethod
    def increment_serial(ca_id: int) -> int:
        """
        Increment CA serial number.

        Args:
            ca_id: CA ID

        Returns:
            New serial number

        Raises:
            ValueError: If CA not found
        """
        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        ca.serial = (ca.serial or 0) + 1
        try:
            db.session.commit()
        except Exception as _commit_err:
            db.session.rollback()
            logger.error(f"Commit failed in services/ca/ca_operations.py:41: {_commit_err}", exc_info=True)
            raise

        return ca.serial

    @staticmethod
    def get_ca_chain(ca_id: int) -> List[bytes]:
        """
        Get CA certificate chain from leaf to root.

        Args:
            ca_id: CA ID

        Returns:
            List of certificate PEMs (leaf to root)
        """
        chain = []
        ca = CA.query.get(ca_id)

        while ca:
            cert_pem = get_ca_cert_pem(ca)
            if cert_pem:
                chain.append(cert_pem)

            # Get parent CA
            if ca.caref:
                ca = CA.query.filter_by(refid=ca.caref).first()
            else:
                break

        return chain

    @staticmethod
    def get_certificate_chain(refid: str) -> List[str]:
        """
        Get CA certificate chain by refid (wrapper returning strings).

        Args:
            refid: CA reference ID

        Returns:
            List of PEM strings (leaf to root)

        Raises:
            ValueError: If CA not found
        """
        ca = CA.query.filter_by(refid=refid).first()
        if not ca:
            raise ValueError(f"CA not found: {refid}")

        chain_bytes = CAOperationsMixin.get_ca_chain(ca.id)
        return [pem.decode('utf-8') if isinstance(pem, bytes) else pem
                for pem in chain_bytes]
