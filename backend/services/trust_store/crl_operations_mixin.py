"""
CRL operations mixin for TrustStoreService
"""
from datetime import datetime, timedelta
from typing import List, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from utils.datetime_utils import utc_now
from .constants import hash_algorithm


from utils.signing_hash import signing_hash_for, rsa_padding_for


class CRLOperationsMixin:
    """CRL operations mixin"""

    @staticmethod
    def generate_crl(
        ca_cert: x509.Certificate,
        ca_private_key,
        revoked_certs: List[Tuple[int, datetime]],
        validity_days: int = 30,
        digest: str = 'sha256'
    ) -> bytes:
        """Generate a Certificate Revocation List."""
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.last_update(utc_now())
        builder = builder.next_update(
            utc_now() + timedelta(days=validity_days)
        )

        # Add revoked certificates
        for serial, revoke_date in revoked_certs:
            revoked_cert = x509.RevokedCertificateBuilder()
            revoked_cert = revoked_cert.serial_number(serial)
            revoked_cert = revoked_cert.revocation_date(revoke_date)
            builder = builder.add_revoked_certificate(revoked_cert.build(default_backend()))

        # Sign CRL
        sign_hash = signing_hash_for(ca_private_key, hash_algorithm(digest))
        crl = builder.sign(
            private_key=ca_private_key,
            algorithm=sign_hash,
            backend=default_backend(),
            rsa_padding=rsa_padding_for(ca_private_key, sign_hash),
        )

        return crl.public_bytes(serialization.Encoding.PEM)
