"""
CSR operations mixin for TrustStoreService
"""
import ipaddress
from datetime import timedelta
from typing import List, Optional, Tuple

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.backends import default_backend

from utils.datetime_utils import utc_now
from .constants import HASH_ALGORITHMS
from .key_operations_mixin import KeyOperationsMixin
from .constraints_mixin import ConstraintsMixin


class CSROperationsMixin:
    """CSR generation and signing operations mixin"""
    
    @staticmethod
    def generate_csr(
        subject: x509.Name,
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
        san_email: Optional[List[str]] = None,
        san_uri: Optional[List[str]] = None,
    ) -> Tuple[bytes, bytes]:
        """Generate a Certificate Signing Request."""
        # Generate private key
        private_key = KeyOperationsMixin.generate_private_key(key_type)
        
        # Build CSR
        builder = x509.CertificateSigningRequestBuilder()
        builder = builder.subject_name(subject)
        
        # Add SANs if provided
        san_list = []
        if san_dns:
            san_list.extend([x509.DNSName(dns) for dns in san_dns])
        if san_ip:
            san_list.extend([
                x509.IPAddress(ipaddress.ip_address(ip)) for ip in san_ip
            ])
        if san_email:
            san_list.extend([x509.RFC822Name(email) for email in san_email])
        if san_uri:
            san_list.extend([x509.UniformResourceIdentifier(uri) for uri in san_uri])
        
        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )
        
        # Sign CSR
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        csr = builder.sign(private_key, hash_algo, default_backend())
        
        # Serialize
        csr_pem = csr.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        return csr_pem, key_pem
    
    @staticmethod
    def sign_csr(
        csr_pem: bytes,
        ca_cert: x509.Certificate,
        ca_private_key,
        validity_days: int = 397,
        digest: str = 'sha256',
        cert_type: str = 'server_cert',
        cdp_url: str = None,
        cdp_urls: Optional[List[str]] = None,
        ocsp_url: str = None,
        ocsp_urls: Optional[List[str]] = None,
        aia_ca_issuers_url: str = None,
        aia_ca_issuers_urls: Optional[List[str]] = None,
        cps_uri: Optional[str] = None,
        cps_oid: Optional[str] = None,
        ocsp_must_staple: bool = False,
        extra_ekus: Optional[List[str]] = None,
    ) -> bytes:
        """Sign a CSR with a CA."""
        from utils.eku_validation import normalize_extra_ekus, to_object_identifiers, merge_eku_lists
        
        # Load CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        if not csr.is_signature_valid:
            raise ValueError("CSR has invalid signature")
        
        # NameConstraints enforcement
        csr_sans = None
        try:
            san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            csr_sans = list(san_ext.value)
        except x509.ExtensionNotFound:
            pass
        ConstraintsMixin._validate_name_constraints(ca_cert, csr.subject, csr_sans)
        
        # If CSR has empty subject, populate CN from first SAN DNS name
        subject = csr.subject
        if not list(subject):
            try:
                san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                for name in san_ext.value:
                    if isinstance(name, x509.DNSName):
                        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name.value)])
                        break
            except x509.ExtensionNotFound:
                pass
        
        # Build certificate from CSR
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(csr.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(utc_now())
        builder = builder.not_valid_after(
            utc_now() + timedelta(days=validity_days)
        )
        
        # Copy extensions from CSR
        for extension in csr.extensions:
            builder = builder.add_extension(extension.value, extension.critical)
        
        # Auto-add SAN from CN if CSR has no SAN extension
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
        except x509.ExtensionNotFound:
            san_names = []
            for attr in subject:
                if attr.oid == NameOID.COMMON_NAME:
                    cn_val = attr.value
                    try:
                        ip = ipaddress.ip_address(cn_val)
                        san_names.append(x509.IPAddress(ip))
                    except ValueError:
                        if '@' in cn_val:
                            san_names.append(x509.RFC822Name(cn_val))
                        else:
                            san_names.append(x509.DNSName(cn_val))
                    break
            for attr in subject:
                if attr.oid == NameOID.EMAIL_ADDRESS:
                    email_val = attr.value
                    if not any(isinstance(n, x509.RFC822Name) and n.value == email_val for n in san_names):
                        san_names.append(x509.RFC822Name(email_val))
            if san_names:
                builder = builder.add_extension(
                    x509.SubjectAlternativeName(san_names),
                    critical=False,
                )
        
        # Add basic extensions if not in CSR
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        except x509.ExtensionNotFound:
            if cert_type == 'intermediate_ca':
                builder = builder.add_extension(
                    x509.BasicConstraints(ca=True, path_length=0),
                    critical=True,
                )
            else:
                builder = builder.add_extension(
                    x509.BasicConstraints(ca=False, path_length=None),
                    critical=True,
                )
        
        # Add key usage based on cert type
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        except x509.ExtensionNotFound:
            if cert_type == 'intermediate_ca':
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True, key_encipherment=False,
                        content_commitment=False, data_encipherment=False,
                        key_agreement=False, key_cert_sign=True, crl_sign=True,
                        encipher_only=False, decipher_only=False,
                    ),
                    critical=True,
                )
            elif cert_type == 'server_cert':
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True, key_encipherment=True,
                        content_commitment=False, data_encipherment=False,
                        key_agreement=False, key_cert_sign=False, crl_sign=False,
                        encipher_only=False, decipher_only=False,
                    ),
                    critical=True,
                )
        
        # Add Extended Key Usage if not in CSR
        extra_oid_strs, extra_err = normalize_extra_ekus(extra_ekus)
        if extra_err:
            raise ValueError(f'Invalid extra_ekus: {extra_err}')
        extra_oids = to_object_identifiers(extra_oid_strs)
        
        try:
            existing_eku = csr.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)
            csr_has_eku = True
        except x509.ExtensionNotFound:
            existing_eku = None
            csr_has_eku = False
        
        if not csr_has_eku:
            base_eku = []
            if cert_type == 'server_cert':
                base_eku = [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]
            elif cert_type in ('usr_cert', 'client_cert'):
                base_eku = [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
            elif cert_type in ('combined_server_client', 'combined_cert'):
                base_eku = [
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH
                ]
            merged = merge_eku_lists(base_eku, extra_oids)
            if merged:
                builder = builder.add_extension(
                    x509.ExtendedKeyUsage(merged),
                    critical=False,
                )
        elif extra_oids:
            merged = merge_eku_lists(list(existing_eku.value), extra_oids)
            new_builder = x509.CertificateBuilder()
            new_builder = new_builder.subject_name(builder._subject_name)
            new_builder = new_builder.issuer_name(builder._issuer_name)
            new_builder = new_builder.public_key(builder._public_key)
            new_builder = new_builder.serial_number(builder._serial_number)
            new_builder = new_builder.not_valid_before(builder._not_valid_before)
            new_builder = new_builder.not_valid_after(builder._not_valid_after)
            for ext in builder._extensions:
                if ext.oid == ExtensionOID.EXTENDED_KEY_USAGE:
                    continue
                new_builder = new_builder.add_extension(ext.value, ext.critical)
            new_builder = new_builder.add_extension(
                x509.ExtendedKeyUsage(merged), critical=existing_eku.critical
            )
            builder = new_builder
        
        # CRL Distribution Points
        all_cdp = cdp_urls or ([cdp_url] if cdp_url else [])
        if all_cdp:
            try:
                csr.extensions.get_extension_for_oid(ExtensionOID.CRL_DISTRIBUTION_POINTS)
            except x509.ExtensionNotFound:
                dist_points = [
                    x509.DistributionPoint(
                        full_name=[x509.UniformResourceIdentifier(url)],
                        relative_name=None, reasons=None, crl_issuer=None
                    )
                    for url in all_cdp
                ]
                builder = builder.add_extension(
                    x509.CRLDistributionPoints(dist_points),
                    critical=False
                )
        
        # Authority Information Access
        all_ocsp = ocsp_urls or ([ocsp_url] if ocsp_url else [])
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
            try:
                csr.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_INFORMATION_ACCESS)
            except x509.ExtensionNotFound:
                builder = builder.add_extension(
                    x509.AuthorityInformationAccess(aia_descriptions),
                    critical=False
                )
        
        # Certificate Policies
        if cps_uri:
            try:
                csr.extensions.get_extension_for_oid(ExtensionOID.CERTIFICATE_POLICIES)
            except x509.ExtensionNotFound:
                policy_oid_obj = x509.ObjectIdentifier(cps_oid or '2.5.29.32.0')
                builder = builder.add_extension(
                    x509.CertificatePolicies([
                        x509.PolicyInformation(
                            policy_identifier=policy_oid_obj,
                            policy_qualifiers=[cps_uri]
                        )
                    ]),
                    critical=False
                )
        
        # SubjectKeyIdentifier
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
        except x509.ExtensionNotFound:
            builder = builder.add_extension(
                x509.SubjectKeyIdentifier.from_public_key(csr.public_key()),
                critical=False
            )
        
        # AuthorityKeyIdentifier
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
        except x509.ExtensionNotFound:
            builder = builder.add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_cert.public_key()),
                critical=False
            )
        
        # OCSP Must-Staple
        if ocsp_must_staple:
            builder = builder.add_extension(
                x509.TLSFeature([x509.TLSFeatureType.status_request]),
                critical=False,
            )
        
        # Sign
        hash_algo = HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=ca_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )
        
        return certificate.public_bytes(serialization.Encoding.PEM)
