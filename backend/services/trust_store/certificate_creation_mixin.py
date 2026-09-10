"""
End-entity certificate creation mixin for TrustStoreService
"""
import ipaddress
from datetime import timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend

from utils.datetime_utils import utc_now, cert_not_before
from utils.eku_validation import add_ocsp_nocheck_if_responder
from utils.x509_aki import authority_key_identifier_from_issuer
from utils.leaf_key_usage import key_usage_for_key
from .constants import HASH_ALGORITHMS
from .constraints_mixin import ConstraintsMixin
from .key_operations_mixin import KeyOperationsMixin
from utils.key_codec import private_key_to_pem


from utils.signing_hash import signing_hash_for


class CertificateCreationMixin:
    """End-entity X.509 certificate creation mixin"""

    @staticmethod
    def create_certificate(
        subject: x509.Name,
        ca_cert: x509.Certificate,
        ca_private_key,
        cert_type: str = 'server_cert',
        validity_days: int = 397,
        digest: str = 'sha256',
        key_type: str = '2048',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        ocsp_uri: Optional[str] = None,
        ocsp_uris: Optional[List[str]] = None,
        cdp_url: Optional[str] = None,
        cdp_urls: Optional[List[str]] = None,
        aia_ca_issuers_url: Optional[str] = None,
        aia_ca_issuers_urls: Optional[List[str]] = None,
        cps_uri: Optional[str] = None,
        cps_oid: Optional[str] = None,
        ocsp_must_staple: bool = False,
    ) -> Tuple[bytes, bytes]:
        """Create a certificate signed by a CA."""
        from cryptography.hazmat.primitives import hashes

        # Generate private key for certificate
        private_key = KeyOperationsMixin.generate_private_key(key_type)

        # Same issuer-window rule as the CSR trunk (RFC 5280 §6.1)
        from utils.ca_signing_window import check_issuer_window, clamp_not_after
        check_issuer_window(ca_cert)

        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(private_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(cert_not_before())
        builder = builder.not_valid_after(
            clamp_not_after(utc_now() + timedelta(days=validity_days), ca_cert)
        )

        # Basic Constraints
        is_ca = (cert_type == 'ca_cert')
        builder = builder.add_extension(
            x509.BasicConstraints(ca=is_ca, path_length=None if not is_ca else 0),
            critical=True,
        )

        # Key Usage / Extended Key Usage based on cert type
        _leaf_bits = dict(
            key_cert_sign=False, crl_sign=False,
            encipher_only=False, decipher_only=False,
        )
        if cert_type == 'ca_cert':
            usage = x509.KeyUsage(
                digital_signature=True, key_encipherment=False,
                content_commitment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            )
            ekus = []
        elif cert_type == 'usr_cert' or cert_type == 'client_cert':
            usage = x509.KeyUsage(
                digital_signature=True, key_encipherment=True,
                content_commitment=True, data_encipherment=False,
                key_agreement=False, **_leaf_bits,
            )
            ekus = [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
        elif cert_type == 'combined_server_client' or cert_type == 'combined_cert':
            usage = x509.KeyUsage(
                digital_signature=True, key_encipherment=True,
                content_commitment=True, data_encipherment=False,
                key_agreement=False, **_leaf_bits,
            )
            ekus = [
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]
        else:
            cert_type = 'server_cert'
            usage = x509.KeyUsage(
                digital_signature=True, key_encipherment=True,
                content_commitment=False, data_encipherment=False,
                key_agreement=False, **_leaf_bits,
            )
            ekus = [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]
        if not is_ca:
            # Profiles above are RSA-shaped; clear what the generated key
            # cannot honour (keyEncipherment on EC), as on every leaf path (#327)
            usage = key_usage_for_key(private_key.public_key(), usage, ekus)
        builder = builder.add_extension(usage, critical=True)
        if ekus:
            builder = builder.add_extension(x509.ExtendedKeyUsage(ekus), critical=False)
        builder = add_ocsp_nocheck_if_responder(builder, ekus)

        # Subject Alternative Names
        san_list = []
        if san_dns:
            san_list.extend([x509.DNSName(dns) for dns in san_dns])
        if san_ip:
            san_list.extend([
                x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ip
            ])
        if san_uri:
            san_list.extend([x509.UniformResourceIdentifier(uri) for uri in san_uri])
        if san_email:
            san_list.extend([x509.RFC822Name(email) for email in san_email])

        if san_list:
            san_critical = not bool(list(subject))
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=san_critical,
            )

        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )

        # Authority Key Identifier (issuer SKI when present — RFC 5280 §4.2.1.1)
        builder = builder.add_extension(
            authority_key_identifier_from_issuer(ca_cert),
            critical=False,
        )

        # Authority Information Access
        all_ocsp = ocsp_uris or ([ocsp_uri] if ocsp_uri else [])
        all_aia = aia_ca_issuers_urls or ([aia_ca_issuers_url] if aia_ca_issuers_url else [])
        aia_descriptions = []
        for uri in all_ocsp:
            aia_descriptions.append(
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.OCSP,
                    x509.UniformResourceIdentifier(uri)
                )
            )
        for url in all_aia:
            aia_descriptions.append(
                x509.AccessDescription(
                    x509.oid.AuthorityInformationAccessOID.CA_ISSUERS,
                    x509.UniformResourceIdentifier(url)
                )
            )
        if aia_descriptions:
            builder = builder.add_extension(
                x509.AuthorityInformationAccess(aia_descriptions),
                critical=False,
            )

        # CRL Distribution Points
        all_cdp = cdp_urls or ([cdp_url] if cdp_url else [])
        if all_cdp:
            dist_points = [
                x509.DistributionPoint(
                    full_name=[x509.UniformResourceIdentifier(url)],
                    relative_name=None, reasons=None, crl_issuer=None
                )
                for url in all_cdp
            ]
            builder = builder.add_extension(
                x509.CRLDistributionPoints(dist_points),
                critical=False,
            )

        # Certificate Policies
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

        # OCSP Must-Staple
        if ocsp_must_staple:
            builder = builder.add_extension(
                x509.TLSFeature([x509.TLSFeatureType.status_request]),
                critical=False,
            )

        # NameConstraints enforcement
        san_names = []
        if san_dns:
            san_names.extend(x509.DNSName(d) for d in san_dns)
        if san_ip:
            san_names.extend(x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ip)
        if san_email:
            san_names.extend(x509.RFC822Name(e) for e in san_email)
        ConstraintsMixin._validate_name_constraints(ca_cert, subject, san_names or None)

        # Sign
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=ca_private_key,
            algorithm=signing_hash_for(ca_private_key, hash_algo),
            backend=default_backend()
        )

        # Serialize
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key_to_pem(private_key)

        return cert_pem, key_pem
