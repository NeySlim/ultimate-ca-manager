"""
CA certificate operations (chain, serial, CRL)
"""
import base64
import logging
from typing import List

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from models import CA, db
from services.trust_store import TrustStoreService
from .helpers import get_ca_cert_pem, get_ca_private_key_pem

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
        db.session.commit()

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

    @staticmethod
    def generate_crl(ca_id: int, validity_days: int = 30) -> bytes:
        """
        Generate Certificate Revocation List for a CA.

        Args:
            ca_id: CA ID
            validity_days: CRL validity in days

        Returns:
            CRL in PEM format

        Raises:
            ValueError: If CA not found or has no private key
        """
        from security.encryption import decrypt_private_key

        ca = CA.query.get(ca_id)
        if not ca:
            raise ValueError("CA not found")

        if not ca.prv:
            raise ValueError("CA has no private key - cannot sign CRL")

        # Load CA certificate and private key
        ca_cert_pem = get_ca_cert_pem(ca)
        ca_cert = x509.load_pem_x509_certificate(ca_cert_pem, default_backend())

        # Decrypt CA private key
        ca_prv_decrypted = decrypt_private_key(ca.prv)
        ca_key_pem = base64.b64decode(ca_prv_decrypted)
        ca_private_key = serialization.load_pem_private_key(
            ca_key_pem, password=None, backend=default_backend()
        )

        # Get all revoked certificates signed by this CA
        from models import Certificate
        revoked_certs = Certificate.query.filter_by(
            caref=ca.refid,
            revoked=True
        ).all()

        # Build list of (serial, revocation_date) tuples
        revoked_list = []
        for cert in revoked_certs:
            # Use created_at as revocation date if revoked_at not available
            revocation_date = cert.revoked_at if cert.revoked_at else cert.created_at
            revoked_list.append((cert.serial, revocation_date))

        # Generate CRL
        crl_pem = TrustStoreService.generate_crl(
            ca_cert=ca_cert,
            ca_private_key=ca_private_key,
            revoked_certs=revoked_list,
            validity_days=validity_days,
            digest='sha256'
        )

        return crl_pem
