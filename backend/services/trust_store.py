"""
Trust Store Service - OpenSSL Operations Wrapper
Core cryptographic operations for CA and Certificate management
"""
import base64
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union
from pathlib import Path

from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.serialization import pkcs12
import ipaddress


class TrustStoreService:
    """Service for all cryptographic operations"""
    
    # Supported key types
    KEY_TYPES = {
        '512': ('rsa', 512),
        '1024': ('rsa', 1024),
        '2048': ('rsa', 2048),
        '3072': ('rsa', 3072),
        '4096': ('rsa', 4096),
        '8192': ('rsa', 8192),
        'prime256v1': ('ec', ec.SECP256R1()),
        'secp384r1': ('ec', ec.SECP384R1()),
        'secp521r1': ('ec', ec.SECP521R1()),
    }
    
    # Supported hash algorithms
    HASH_ALGORITHMS = {
        'sha1': hashes.SHA1(),
        'sha224': hashes.SHA224(),
        'sha256': hashes.SHA256(),
        'sha384': hashes.SHA384(),
        'sha512': hashes.SHA512(),
    }
    
    @staticmethod
    def generate_private_key(key_type: str):
        """
        Generate a private key
        
        Args:
            key_type: Key type (512, 1024, 2048, etc. or prime256v1, etc.)
            
        Returns:
            Private key object
        """
        if key_type not in TrustStoreService.KEY_TYPES:
            raise ValueError(f"Unsupported key type: {key_type}")
        
        algo, param = TrustStoreService.KEY_TYPES[key_type]
        
        if algo == 'rsa':
            return rsa.generate_private_key(
                public_exponent=65537,
                key_size=param,
                backend=default_backend()
            )
        elif algo == 'ec':
            return ec.generate_private_key(param, default_backend())
        
        raise ValueError(f"Unknown algorithm: {algo}")
    
    @staticmethod
    def build_subject(dn_dict: Dict[str, str]) -> x509.Name:
        """
        Build X.509 subject/issuer name from dictionary
        
        Args:
            dn_dict: Dictionary with DN components (CN, O, OU, C, ST, L, email)
            
        Returns:
            x509.Name object
        """
        attributes = []
        
        # Map of field names to OIDs
        oid_map = {
            'C': NameOID.COUNTRY_NAME,
            'ST': NameOID.STATE_OR_PROVINCE_NAME,
            'L': NameOID.LOCALITY_NAME,
            'O': NameOID.ORGANIZATION_NAME,
            'OU': NameOID.ORGANIZATIONAL_UNIT_NAME,
            'CN': NameOID.COMMON_NAME,
            'email': NameOID.EMAIL_ADDRESS,
        }
        
        # Order matters for DN
        order = ['C', 'ST', 'L', 'O', 'OU', 'CN', 'email']
        
        for field in order:
            if field in dn_dict and dn_dict[field]:
                attributes.append(
                    x509.NameAttribute(oid_map[field], str(dn_dict[field]))
                )
        
        return x509.Name(attributes)
    
    @staticmethod
    def create_ca_certificate(
        subject: x509.Name,
        private_key,
        issuer: Optional[x509.Name] = None,
        issuer_private_key = None,
        validity_days: int = 825,
        digest: str = 'sha256',
        ocsp_uri: Optional[str] = None,
        serial: Optional[int] = None
    ) -> Tuple[bytes, bytes]:
        """
        Create a CA certificate
        
        Args:
            subject: Subject name
            private_key: Private key for the CA
            issuer: Issuer name (None for self-signed)
            issuer_private_key: Issuer's private key (None for self-signed)
            validity_days: Certificate validity in days
            digest: Hash algorithm
            ocsp_uri: Optional OCSP URI
            serial: Optional serial number
            
        Returns:
            Tuple of (certificate PEM bytes, private key PEM bytes)
        """
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
        builder = builder.not_valid_before(datetime.utcnow())
        builder = builder.not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # CA extensions
        builder = builder.add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
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
        
        # OCSP URI if provided
        if ocsp_uri:
            builder = builder.add_extension(
                x509.AuthorityInformationAccess([
                    x509.AccessDescription(
                        x509.oid.AuthorityInformationAccessOID.OCSP,
                        x509.UniformResourceIdentifier(ocsp_uri)
                    )
                ]),
                critical=False,
            )
        
        # Sign certificate
        hash_algo = TrustStoreService.HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=issuer_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )
        
        # Serialize certificate
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        
        # Serialize private key
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        return cert_pem, key_pem
    
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
    ) -> Tuple[bytes, bytes]:
        """
        Create a certificate signed by a CA
        
        Args:
            subject: Subject name
            ca_cert: CA certificate object
            ca_private_key: CA private key
            cert_type: Certificate type (usr_cert, server_cert, combined_server_client)
            validity_days: Validity in days
            digest: Hash algorithm
            key_type: Key type for new certificate
            san_dns: List of DNS SANs
            san_ip: List of IP SANs
            san_uri: List of URI SANs
            san_email: List of email SANs
            
        Returns:
            Tuple of (certificate PEM, private key PEM)
        """
        # Generate private key for certificate
        private_key = TrustStoreService.generate_private_key(key_type)
        
        # Build certificate
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(private_key.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(datetime.utcnow())
        builder = builder.not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # Basic Constraints - not a CA
        builder = builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        
        # Key Usage based on cert type
        if cert_type == 'usr_cert':
            # Client certificate
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
        elif cert_type == 'server_cert':
            # Server certificate
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=False,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                ]),
                critical=False,
            )
        elif cert_type == 'combined_server_client':
            # Combined
            builder = builder.add_extension(
                x509.KeyUsage(
                    digital_signature=True,
                    key_encipherment=True,
                    content_commitment=True,
                    data_encipherment=False,
                    key_agreement=False,
                    key_cert_sign=False,
                    crl_sign=False,
                    encipher_only=False,
                    decipher_only=False,
                ),
                critical=True,
            )
            builder = builder.add_extension(
                x509.ExtendedKeyUsage([
                    x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
                    x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
                ]),
                critical=False,
            )
        
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
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )
        
        # Subject Key Identifier
        builder = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
        
        # Authority Key Identifier
        builder = builder.add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_private_key.public_key()
            ),
            critical=False,
        )
        
        # Sign
        hash_algo = TrustStoreService.HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=ca_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )
        
        # Serialize
        cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption()
        )
        
        return cert_pem, key_pem
    
    @staticmethod
    def generate_csr(
        subject: x509.Name,
        key_type: str = '2048',
        digest: str = 'sha256',
        san_dns: Optional[List[str]] = None,
        san_ip: Optional[List[str]] = None,
    ) -> Tuple[bytes, bytes]:
        """
        Generate a Certificate Signing Request
        
        Args:
            subject: Subject name
            key_type: Key type
            digest: Hash algorithm
            san_dns: List of DNS SANs
            san_ip: List of IP SANs
            
        Returns:
            Tuple of (CSR PEM, private key PEM)
        """
        # Generate private key
        private_key = TrustStoreService.generate_private_key(key_type)
        
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
        
        if san_list:
            builder = builder.add_extension(
                x509.SubjectAlternativeName(san_list),
                critical=False,
            )
        
        # Sign CSR
        hash_algo = TrustStoreService.HASH_ALGORITHMS.get(digest, hashes.SHA256())
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
        cert_type: str = 'server_cert'
    ) -> bytes:
        """
        Sign a CSR with a CA
        
        Args:
            csr_pem: CSR in PEM format
            ca_cert: CA certificate
            ca_private_key: CA private key
            validity_days: Validity in days
            digest: Hash algorithm
            cert_type: Certificate type
            
        Returns:
            Signed certificate PEM
        """
        # Load CSR
        csr = x509.load_pem_x509_csr(csr_pem, default_backend())
        
        # Build certificate from CSR
        builder = x509.CertificateBuilder()
        builder = builder.subject_name(csr.subject)
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.public_key(csr.public_key())
        builder = builder.serial_number(x509.random_serial_number())
        builder = builder.not_valid_before(datetime.utcnow())
        builder = builder.not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # Copy extensions from CSR
        for extension in csr.extensions:
            builder = builder.add_extension(extension.value, extension.critical)
        
        # Add basic extensions if not in CSR
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
        except x509.ExtensionNotFound:
            builder = builder.add_extension(
                x509.BasicConstraints(ca=False, path_length=None),
                critical=True,
            )
        
        # Add key usage based on cert type
        try:
            csr.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
        except x509.ExtensionNotFound:
            if cert_type == 'server_cert':
                builder = builder.add_extension(
                    x509.KeyUsage(
                        digital_signature=True,
                        key_encipherment=True,
                        content_commitment=False,
                        data_encipherment=False,
                        key_agreement=False,
                        key_cert_sign=False,
                        crl_sign=False,
                        encipher_only=False,
                        decipher_only=False,
                    ),
                    critical=True,
                )
        
        # Sign
        hash_algo = TrustStoreService.HASH_ALGORITHMS.get(digest, hashes.SHA256())
        certificate = builder.sign(
            private_key=ca_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )
        
        return certificate.public_bytes(serialization.Encoding.PEM)
    
    @staticmethod
    def parse_certificate(cert_pem: bytes) -> Dict:
        """
        Parse a certificate and extract information
        
        Args:
            cert_pem: Certificate in PEM format
            
        Returns:
            Dictionary with certificate details
        """
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        
        return {
            'subject': cert.subject.rfc4514_string(),
            'issuer': cert.issuer.rfc4514_string(),
            'serial_number': str(cert.serial_number),
            'not_valid_before': cert.not_valid_before,
            'not_valid_after': cert.not_valid_after,
            'is_ca': False,  # Will be updated if extension found
            'key_usage': [],
            'extended_key_usage': [],
            'san': [],
        }
    
    @staticmethod
    def export_pkcs12(
        cert_pem: bytes,
        key_pem: bytes,
        password: str,
        friendly_name: str = "Certificate"
    ) -> bytes:
        """
        Export certificate and key as PKCS#12
        
        Args:
            cert_pem: Certificate PEM
            key_pem: Private key PEM
            password: Password for PKCS#12
            friendly_name: Friendly name
            
        Returns:
            PKCS#12 bytes
        """
        cert = x509.load_pem_x509_certificate(cert_pem, default_backend())
        key = serialization.load_pem_private_key(
            key_pem, password=None, backend=default_backend()
        )
        
        p12 = pkcs12.serialize_key_and_certificates(
            friendly_name.encode(),
            key,
            cert,
            None,  # No CA certs
            serialization.BestAvailableEncryption(password.encode())
        )
        
        return p12
    
    @staticmethod
    def generate_crl(
        ca_cert: x509.Certificate,
        ca_private_key,
        revoked_certs: List[Tuple[int, datetime]],
        validity_days: int = 30,
        digest: str = 'sha256'
    ) -> bytes:
        """
        Generate a Certificate Revocation List
        
        Args:
            ca_cert: CA certificate
            ca_private_key: CA private key
            revoked_certs: List of (serial_number, revocation_date) tuples
            validity_days: CRL validity in days
            digest: Hash algorithm
            
        Returns:
            CRL in PEM format
        """
        builder = x509.CertificateRevocationListBuilder()
        builder = builder.issuer_name(ca_cert.subject)
        builder = builder.last_update(datetime.utcnow())
        builder = builder.next_update(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # Add revoked certificates
        for serial, revoke_date in revoked_certs:
            revoked_cert = x509.RevokedCertificateBuilder()
            revoked_cert = revoked_cert.serial_number(serial)
            revoked_cert = revoked_cert.revocation_date(revoke_date)
            builder = builder.add_revoked_certificate(revoked_cert.build(default_backend()))
        
        # Sign CRL
        hash_algo = TrustStoreService.HASH_ALGORITHMS.get(digest, hashes.SHA256())
        crl = builder.sign(
            private_key=ca_private_key,
            algorithm=hash_algo,
            backend=default_backend()
        )
        
        return crl.public_bytes(serialization.Encoding.PEM)
