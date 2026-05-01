"""
CA certificate creation mixin for TrustStoreService
"""
import ipaddress
from datetime import timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

from utils.datetime_utils import utc_now
from .constants import HASH_ALGORITHMS
from .constraints_mixin import ConstraintsMixin


class CACertificateCreationMixin:
    """CA X.509 certificate creation mixin"""

    @staticmethod
    def create_ca_certificate(
        subject: x509.Name,
        private_key,
        issuer: Optional[x509.Name] = None,
        issuer_private_key = None,
        validity_days: int = 825,
        digest: str = 'sha256',
        ocsp_uri: Optional[str] = None,
        ocsp_uris: Optional[List[str]] = None,
        cdp_url: Optional[str] = None,
        cdp_urls: Optional[List[str]] = None,
        cps_uri: Optional[str] = None,
        cps_oid: Optional[str] = None,
        serial: Optional[int] = None,
        path_length: Optional[int] = None,
        name_constraints_permitted: Optional[List[dict]] = None,
        name_constraints_excluded: Optional[List[dict]] = None,
        policy_constraints_require: Optional[int] = None,
        policy_constraints_inhibit: Optional[int] = None,
        inhibit_any_policy: Optional[int] = None,
        sia_urls: Optional[List[str]] = None,
    ) -> Tuple[bytes, bytes]:
        """Create a CA certificate."""
        # Normalize URL params: merge singular into list
        all_cdp_urls = cdp_urls or ([cdp_url] if cdp_url else [])
        all_ocsp_uris = ocsp_uris or ([ocsp_uri] if ocsp_uri else [])

        # For self-signed, issuer is subject
        if issuer is None:
            issuer = subject
            issuer_private_key = private_key

        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(issuer)
        builder = builder.public_key(private_key.public_key())
        builder = builder.serial_number(
            serial if serial else x509.random_serial_number()
        )
        builder = builder.not_valid_before(utc_now())
        builder = builder.not_valid_after(
            utc_now() + timedelta(days=validity_days)
        )

        # CA extensions — BasicConstraints with configurable pathLenConstraint
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=path_length),
            critical=True,
        )

        builder = builder.add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=False,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=True,
                crl_sign=True,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )

        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )

        # Authority Key Identifier (for intermediate CAs)
        if issuer != subject:
            builder = builder.add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(
                    issuer_private_key.public_key()
                ),
                critical=False,
            )

        # Authority Information Access — OCSP URIs
        if all_ocsp_uris:
            aia_descriptions = [
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.OCSP,
                    x509.UniformResourceIdentifier(uri)
                )
                for uri in all_ocsp_uris
            ]
            builder = builder.add_extension(
                x509.AuthorityInformationAccess(aia_descriptions),
                critical=False,
            )

        # CRL Distribution Points
        if all_cdp_urls:
            dist_points = [
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier(url)],
                    relative_name=None,
                    crl_issuer=None,
                    reasons=None,
                )
                for url in all_cdp_urls
            ]
            builder = builder.add_extension(
                x509.CRLDistributionPoints(dist_points),
                critical=False,
            )

        # Certificate Policies / CPS
        if cps_uri:
            policy_oid = x509.ObjectIdentifier(cps_oid or '2.5.29.32.0')
            builder = builder.add_extension(
                x509.CertificatePolicies([
                    x509.PolicyInformation(
                        policy_identifier=policy_oid,
                        policy_qualifiers=[cps_uri]
                    )
                ]),
                critical=False,
            )

        # NameConstraints
        nc_permitted = ConstraintsMixin._build_general_subtrees(name_constraints_permitted)
        nc_excluded = ConstraintsMixin._build_general_subtrees(name_constraints_excluded)
        if nc_permitted or nc_excluded:
            builder = builder.add_extension(
                x509.NameConstraints(
                    permitted_subtrees=nc_permitted or None,
                    excluded_subtrees=nc_excluded or None,
                ),
                critical=True,
            )

        # PolicyConstraints
        if policy_constraints_require is not None or policy_constraints_inhibit is not None:
            builder = builder.add_extension(
                x509.PolicyConstraints(
                    require_explicit_policy=policy_constraints_require,
                    inhibit_policy_mapping=policy_constraints_inhibit,
                ),
                critical=True,
            )

        # InhibitAnyPolicy
        if inhibit_any_policy is not None:
            builder = builder.add_extension(
                x509.InhibitAnyPolicy(skip_certs=inhibit_any_policy),
                critical=True,
            )

        # Subject Information Access — caRepository
        if sia_urls:
            sia_descriptions = [
                x509.AccessDescription(
                    x509.oid.SubjectInformationAccessOID.CA_REPOSITORY,
                    x509.UniformResourceIdentifier(url)
                )
                for url in sia_urls
            ]
            builder = builder.add_extension(
                x509.SubjectInformationAccess(sia_descriptions),
                critical=False,
            )

        # Sign certificate
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=issuer_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )

        # Serialize certificate
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)

        # Serialize private key — HSM-backed keys cannot be exported
        try:
            from services.hsm.hsm_private_key import is_hsm_private_key
        except ImportError:
            is_hsm_private_key = lambda _k: False  # noqa: E731

        if is_hsm_private_key(private_key):
            key_pem = None
        else:
            key_pem = private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )

        return cert_pem, key_pem
