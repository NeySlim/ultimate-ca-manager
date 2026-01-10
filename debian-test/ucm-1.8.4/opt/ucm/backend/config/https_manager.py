"""
HTTPS Certificate Manager
Auto-generates self-signed certificates and manages HTTPS configuration
"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Tuple, Optional
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
import socket
import ipaddress


class HTTPSManager:
    """Manages HTTPS certificates for the application"""
    
    @staticmethod
    def generate_self_signed_cert(
        cert_path: Path,
        key_path: Path,
        common_name: Optional[str] = None,
        organization: str = "Ultimate CA Manager",
        validity_days: int = 825
    ) -> Tuple[Path, Path]:
        """
        Generate a self-signed certificate for HTTPS
        
        Args:
            cert_path: Path to save certificate
            key_path: Path to save private key
            common_name: CN for certificate (defaults to hostname)
            organization: Organization name
            validity_days: Certificate validity period
            
        Returns:
            Tuple of (cert_path, key_path)
        """
        # Generate private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )
        
        # Get hostname for CN
        if common_name is None:
            try:
                common_name = socket.getfqdn()
            except:
                common_name = "localhost"
        
        # Build subject
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, "NL"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, organization),
            x509.NameAttribute(NameOID.COMMON_NAME, common_name),
        ])
        
        # Build certificate
        cert_builder = x509.CertificateBuilder()
        cert_builder = cert_builder.subject_name(subject)
        cert_builder = cert_builder.issuer_name(issuer)
        cert_builder = cert_builder.public_key(private_key.public_key())
        cert_builder = cert_builder.serial_number(x509.random_serial_number())
        cert_builder = cert_builder.not_valid_before(datetime.utcnow())
        cert_builder = cert_builder.not_valid_after(
            datetime.utcnow() + timedelta(days=validity_days)
        )
        
        # Add extensions
        cert_builder = cert_builder.add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName(common_name),
                x509.DNSName("localhost"),
                x509.DNSName("*.localhost"),
                x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
                x509.IPAddress(ipaddress.IPv6Address("::1")),
            ]),
            critical=False,
        )
        
        cert_builder = cert_builder.add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        
        cert_builder = cert_builder.add_extension(
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
        
        cert_builder = cert_builder.add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.SERVER_AUTH,
            ]),
            critical=False,
        )
        
        # Sign certificate
        certificate = cert_builder.sign(
            private_key=private_key,
            algorithm=hashes.SHA256(),
            backend=default_backend()
        )
        
        # Write private key
        key_path.parent.mkdir(parents=True, exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            ))
        key_path.chmod(0o600)
        
        # Write certificate
        cert_path.parent.mkdir(parents=True, exist_ok=True)
        with open(cert_path, "wb") as f:
            f.write(certificate.public_bytes(
                encoding=serialization.Encoding.PEM
            ))
        
        return cert_path, key_path
    
    @staticmethod
    def verify_cert_files(cert_path: Path, key_path: Path) -> bool:
        """
        Verify that certificate and key files are valid
        
        Args:
            cert_path: Path to certificate
            key_path: Path to private key
            
        Returns:
            True if valid, False otherwise
        """
        try:
            # Check files exist
            if not cert_path.exists() or not key_path.exists():
                return False
            
            # Load certificate
            with open(cert_path, "rb") as f:
                cert_data = f.read()
                x509.load_pem_x509_certificate(cert_data, default_backend())
            
            # Load private key
            with open(key_path, "rb") as f:
                key_data = f.read()
                serialization.load_pem_private_key(
                    key_data, password=None, backend=default_backend()
                )
            
            return True
        except Exception:
            return False
    
    @staticmethod
    def get_cert_info(cert_path: Path) -> Optional[dict]:
        """
        Get information about a certificate
        
        Args:
            cert_path: Path to certificate
            
        Returns:
            Dictionary with certificate information or None
        """
        try:
            with open(cert_path, "rb") as f:
                cert = x509.load_pem_x509_certificate(f.read(), default_backend())
            
            return {
                "subject": cert.subject.rfc4514_string(),
                "issuer": cert.issuer.rfc4514_string(),
                "serial_number": cert.serial_number,
                "not_valid_before": cert.not_valid_before,
                "not_valid_after": cert.not_valid_after,
                "is_expired": cert.not_valid_after < datetime.utcnow(),
            }
        except Exception:
            return None
    
    @classmethod
    def ensure_https_cert(cls, cert_path: Path, key_path: Path, auto_generate: bool = True) -> bool:
        """
        Ensure HTTPS certificate exists, generate if needed
        
        Args:
            cert_path: Path to certificate
            key_path: Path to private key
            auto_generate: Whether to auto-generate if missing
            
        Returns:
            True if certificate is available, False otherwise
        """
        if cls.verify_cert_files(cert_path, key_path):
            return True
        
        if auto_generate:
            print(f"Generating self-signed HTTPS certificate...")
            cls.generate_self_signed_cert(cert_path, key_path)
            print(f"Certificate generated: {cert_path}")
            return True
        
        return False
