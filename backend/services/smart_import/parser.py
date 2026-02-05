"""
Smart Parser - Detect and extract cryptographic objects from any input

Supports:
- PEM format (certificates, keys, CSRs)
- DER format (binary)
- PKCS#12/PFX bundles
- PKCS#7/CMS chains
- Mixed content (multiple objects in one input)
"""

import re
import base64
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import pkcs12, pkcs7
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID


class ObjectType(Enum):
    CERTIFICATE = "certificate"
    PRIVATE_KEY = "private_key"
    CSR = "csr"
    PUBLIC_KEY = "public_key"
    UNKNOWN = "unknown"


@dataclass
class ParsedObject:
    """Represents a detected cryptographic object"""
    type: ObjectType
    raw_pem: str = ""
    raw_der: bytes = b""
    index: int = 0  # Position in input
    
    # Certificate-specific
    subject: str = ""
    issuer: str = ""
    serial_number: str = ""
    not_before: Optional[str] = None
    not_after: Optional[str] = None
    is_ca: bool = False
    is_self_signed: bool = False
    san_dns: List[str] = field(default_factory=list)
    san_ip: List[str] = field(default_factory=list)
    
    # Key-specific
    key_algorithm: str = ""
    key_size: int = 0
    is_encrypted: bool = False
    
    # Matching info (filled by matcher)
    matched_cert_index: Optional[int] = None
    matched_key_index: Optional[int] = None
    
    # Chain info (filled by chain_builder)
    chain_position: str = ""  # "leaf", "intermediate", "root"
    chain_depth: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type.value,
            "index": self.index,
            "subject": self.subject,
            "issuer": self.issuer,
            "serial_number": self.serial_number,
            "not_before": self.not_before,
            "not_after": self.not_after,
            "is_ca": self.is_ca,
            "is_self_signed": self.is_self_signed,
            "san_dns": self.san_dns,
            "san_ip": self.san_ip,
            "key_algorithm": self.key_algorithm,
            "key_size": self.key_size,
            "is_encrypted": self.is_encrypted,
            "matched_cert_index": self.matched_cert_index,
            "matched_key_index": self.matched_key_index,
            "chain_position": self.chain_position,
            "chain_depth": self.chain_depth,
        }


class SmartParser:
    """
    Intelligent parser that detects and extracts cryptographic objects
    from any input format.
    """
    
    # PEM patterns
    PEM_CERT_PATTERN = re.compile(
        r'-----BEGIN\s+CERTIFICATE-----\s*\n'
        r'([A-Za-z0-9+/=\s]+)'
        r'-----END\s+CERTIFICATE-----',
        re.MULTILINE
    )
    
    PEM_KEY_PATTERNS = [
        re.compile(r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+(?:RSA\s+)?PRIVATE\s+KEY-----', re.MULTILINE),
        re.compile(r'-----BEGIN\s+EC\s+PRIVATE\s+KEY-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+EC\s+PRIVATE\s+KEY-----', re.MULTILINE),
        re.compile(r'-----BEGIN\s+ENCRYPTED\s+PRIVATE\s+KEY-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+ENCRYPTED\s+PRIVATE\s+KEY-----', re.MULTILINE),
        re.compile(r'-----BEGIN\s+PRIVATE\s+KEY-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+PRIVATE\s+KEY-----', re.MULTILINE),
    ]
    
    PEM_CSR_PATTERNS = [
        re.compile(r'-----BEGIN\s+CERTIFICATE\s+REQUEST-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+CERTIFICATE\s+REQUEST-----', re.MULTILINE),
        re.compile(r'-----BEGIN\s+NEW\s+CERTIFICATE\s+REQUEST-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+NEW\s+CERTIFICATE\s+REQUEST-----', re.MULTILINE),
    ]
    
    PEM_PKCS7_PATTERN = re.compile(
        r'-----BEGIN\s+PKCS7-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+PKCS7-----',
        re.MULTILINE
    )
    
    def parse(self, content: str | bytes, password: Optional[str] = None) -> List[ParsedObject]:
        """
        Parse any input and return list of detected objects.
        
        Args:
            content: PEM string, DER bytes, or base64-encoded data
            password: Optional password for encrypted keys/PKCS12
            
        Returns:
            List of ParsedObject instances
        """
        objects: List[ParsedObject] = []
        
        # Convert bytes to string if needed (for PEM detection)
        if isinstance(content, bytes):
            # Try to decode as UTF-8 for PEM, otherwise treat as DER
            try:
                content_str = content.decode('utf-8')
            except UnicodeDecodeError:
                # Binary data - try DER/PKCS12
                return self._parse_binary(content, password)
        else:
            content_str = content
        
        # Check for pseudo-PEM wrappers for binary data (from frontend)
        objects.extend(self._parse_pseudo_pem_binary(content_str, password))
        
        # Check if it's base64-encoded binary
        if self._looks_like_base64(content_str) and '-----BEGIN' not in content_str:
            try:
                decoded = base64.b64decode(content_str)
                return self._parse_binary(decoded, password)
            except Exception:
                pass
        
        # Parse PEM content
        objects.extend(self._parse_pem_certificates(content_str))
        objects.extend(self._parse_pem_keys(content_str, password))
        objects.extend(self._parse_pem_csrs(content_str))
        objects.extend(self._parse_pem_pkcs7(content_str))
        
        # Re-index objects by their position in the original content
        objects.sort(key=lambda o: o.index)
        for i, obj in enumerate(objects):
            obj.index = i
            
        return objects
    
    def _parse_pseudo_pem_binary(self, content: str, password: Optional[str] = None) -> List[ParsedObject]:
        """Parse pseudo-PEM wrapped binary data (PKCS12, DER) from frontend uploads"""
        objects: List[ParsedObject] = []
        
        # PKCS12 pattern
        pkcs12_pattern = re.compile(
            r'-----BEGIN\s+PKCS12-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+PKCS12-----',
            re.MULTILINE
        )
        for match in pkcs12_pattern.finditer(content):
            try:
                b64_data = match.group(1).replace('\n', '').replace('\r', '').replace(' ', '')
                binary_data = base64.b64decode(b64_data)
                objs = self._parse_pkcs12(binary_data, password)
                objects.extend(objs)
            except Exception:
                pass
        
        # DER certificate pattern
        der_cert_pattern = re.compile(
            r'-----BEGIN\s+DER\s+CERTIFICATE-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+DER\s+CERTIFICATE-----',
            re.MULTILINE
        )
        for match in der_cert_pattern.finditer(content):
            try:
                b64_data = match.group(1).replace('\n', '').replace('\r', '').replace(' ', '')
                binary_data = base64.b64decode(b64_data)
                obj = self._parse_der_cert(binary_data)
                if obj:
                    objects.append(obj)
            except Exception:
                pass
        
        # DER key pattern
        der_key_pattern = re.compile(
            r'-----BEGIN\s+DER\s+KEY-----\s*\n([A-Za-z0-9+/=\s]+)-----END\s+DER\s+KEY-----',
            re.MULTILINE
        )
        for match in der_key_pattern.finditer(content):
            try:
                b64_data = match.group(1).replace('\n', '').replace('\r', '').replace(' ', '')
                binary_data = base64.b64decode(b64_data)
                obj = self._parse_der_key(binary_data, password)
                if obj:
                    objects.append(obj)
            except Exception:
                pass
        
        return objects
    
    def _looks_like_base64(self, content: str) -> bool:
        """Check if content looks like base64-encoded data"""
        clean = content.strip().replace('\n', '').replace('\r', '')
        if len(clean) < 20:
            return False
        # Base64 pattern: only alphanumeric, +, /, = and length multiple of 4
        if re.match(r'^[A-Za-z0-9+/]+={0,2}$', clean):
            return len(clean) % 4 == 0
        return False
    
    def _parse_binary(self, data: bytes, password: Optional[str] = None) -> List[ParsedObject]:
        """Parse binary data (DER, PKCS12, PKCS7)"""
        objects: List[ParsedObject] = []
        
        # Try PKCS12 first (most common binary format)
        try:
            pwd = password.encode() if password else None
            private_key, cert, additional_certs = pkcs12.load_key_and_certificates(data, pwd)
            
            idx = 0
            if cert:
                obj = self._parse_x509_cert(cert)
                obj.index = idx
                objects.append(obj)
                idx += 1
                
            if private_key:
                obj = self._parse_private_key(private_key)
                obj.index = idx
                objects.append(obj)
                idx += 1
                
            if additional_certs:
                for add_cert in additional_certs:
                    obj = self._parse_x509_cert(add_cert)
                    obj.index = idx
                    objects.append(obj)
                    idx += 1
                    
            if objects:
                return objects
        except Exception:
            pass
        
        # Try DER certificate
        try:
            cert = x509.load_der_x509_certificate(data, default_backend())
            obj = self._parse_x509_cert(cert)
            obj.raw_der = data
            return [obj]
        except Exception:
            pass
        
        # Try DER private key
        try:
            key = serialization.load_der_private_key(data, password=password.encode() if password else None)
            obj = self._parse_private_key(key)
            obj.raw_der = data
            return [obj]
        except Exception:
            pass
        
        # Try PKCS7
        try:
            certs = pkcs7.load_der_pkcs7_certificates(data)
            for i, cert in enumerate(certs):
                obj = self._parse_x509_cert(cert)
                obj.index = i
                objects.append(obj)
            if objects:
                return objects
        except Exception:
            pass
        
        return objects
    
    def _parse_pem_certificates(self, content: str) -> List[ParsedObject]:
        """Extract all PEM certificates"""
        objects = []
        for match in self.PEM_CERT_PATTERN.finditer(content):
            pem_block = match.group(0)
            try:
                cert = x509.load_pem_x509_certificate(pem_block.encode(), default_backend())
                obj = self._parse_x509_cert(cert)
                obj.raw_pem = pem_block
                obj.index = match.start()
                objects.append(obj)
            except Exception:
                continue
        return objects
    
    def _parse_pem_keys(self, content: str, password: Optional[str] = None) -> List[ParsedObject]:
        """Extract all PEM private keys"""
        objects = []
        seen_positions = set()  # Deduplicate by position
        pwd = password.encode() if password else None
        
        for pattern in self.PEM_KEY_PATTERNS:
            for match in pattern.finditer(content):
                # Skip if we already processed a key at this position
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())
                
                pem_block = match.group(0)
                is_encrypted = 'ENCRYPTED' in pem_block
                
                try:
                    key = serialization.load_pem_private_key(
                        pem_block.encode(),
                        password=pwd,
                        backend=default_backend()
                    )
                    obj = self._parse_private_key(key)
                    obj.raw_pem = pem_block
                    obj.index = match.start()
                    obj.is_encrypted = is_encrypted
                    objects.append(obj)
                except Exception:
                    # Key might be encrypted without password
                    obj = ParsedObject(
                        type=ObjectType.PRIVATE_KEY,
                        raw_pem=pem_block,
                        index=match.start(),
                        is_encrypted=True,
                        key_algorithm="unknown (encrypted)"
                    )
                    objects.append(obj)
                    
        return objects
    
    def _parse_pem_csrs(self, content: str) -> List[ParsedObject]:
        """Extract all PEM CSRs"""
        objects = []
        
        for pattern in self.PEM_CSR_PATTERNS:
            for match in pattern.finditer(content):
                pem_block = match.group(0)
                try:
                    csr = x509.load_pem_x509_csr(pem_block.encode(), default_backend())
                    obj = ParsedObject(
                        type=ObjectType.CSR,
                        raw_pem=pem_block,
                        index=match.start(),
                        subject=csr.subject.rfc4514_string(),
                    )
                    
                    # Extract key info from CSR
                    pub_key = csr.public_key()
                    obj.key_algorithm, obj.key_size = self._get_key_info(pub_key)
                    
                    # Extract SANs if present
                    try:
                        san_ext = csr.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                        for name in san_ext.value:
                            if isinstance(name, x509.DNSName):
                                obj.san_dns.append(name.value)
                            elif isinstance(name, x509.IPAddress):
                                obj.san_ip.append(str(name.value))
                    except x509.ExtensionNotFound:
                        pass
                        
                    objects.append(obj)
                except Exception:
                    continue
                    
        return objects
    
    def _parse_pem_pkcs7(self, content: str) -> List[ParsedObject]:
        """Extract certificates from PKCS7 PEM blocks"""
        objects = []
        
        for match in self.PEM_PKCS7_PATTERN.finditer(content):
            pem_block = match.group(0)
            try:
                certs = pkcs7.load_pem_pkcs7_certificates(pem_block.encode())
                for cert in certs:
                    obj = self._parse_x509_cert(cert)
                    obj.index = match.start()
                    objects.append(obj)
            except Exception:
                continue
                
        return objects
    
    def _parse_x509_cert(self, cert: x509.Certificate) -> ParsedObject:
        """Convert x509.Certificate to ParsedObject"""
        obj = ParsedObject(type=ObjectType.CERTIFICATE)
        
        obj.subject = cert.subject.rfc4514_string()
        obj.issuer = cert.issuer.rfc4514_string()
        obj.serial_number = str(cert.serial_number)
        obj.not_before = cert.not_valid_before_utc.isoformat() if hasattr(cert, 'not_valid_before_utc') else cert.not_valid_before.isoformat()
        obj.not_after = cert.not_valid_after_utc.isoformat() if hasattr(cert, 'not_valid_after_utc') else cert.not_valid_after.isoformat()
        
        # Check if CA
        try:
            basic_constraints = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
            obj.is_ca = basic_constraints.value.ca
        except x509.ExtensionNotFound:
            obj.is_ca = False
        
        # Check if self-signed
        obj.is_self_signed = (obj.subject == obj.issuer)
        
        # Extract SANs
        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            for name in san_ext.value:
                if isinstance(name, x509.DNSName):
                    obj.san_dns.append(name.value)
                elif isinstance(name, x509.IPAddress):
                    obj.san_ip.append(str(name.value))
        except x509.ExtensionNotFound:
            pass
        
        # Key info
        obj.key_algorithm, obj.key_size = self._get_key_info(cert.public_key())
        
        # Store PEM
        obj.raw_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
        obj.raw_der = cert.public_bytes(serialization.Encoding.DER)
        
        return obj
    
    def _parse_private_key(self, key) -> ParsedObject:
        """Convert private key to ParsedObject"""
        obj = ParsedObject(type=ObjectType.PRIVATE_KEY)
        obj.key_algorithm, obj.key_size = self._get_key_info(key)
        
        # Store PEM (unencrypted for matching)
        obj.raw_pem = key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode()
        
        return obj
    
    def _parse_pkcs12(self, data: bytes, password: Optional[str] = None) -> List[ParsedObject]:
        """Parse PKCS12 binary data"""
        objects = []
        try:
            pwd = password.encode() if password else None
            private_key, cert, additional_certs = pkcs12.load_key_and_certificates(data, pwd)
            
            idx = 0
            if cert:
                obj = self._parse_x509_cert(cert)
                obj.index = idx
                objects.append(obj)
                idx += 1
                
            if private_key:
                obj = self._parse_private_key(private_key)
                obj.index = idx
                objects.append(obj)
                idx += 1
                
            if additional_certs:
                for add_cert in additional_certs:
                    obj = self._parse_x509_cert(add_cert)
                    obj.index = idx
                    objects.append(obj)
                    idx += 1
        except Exception:
            pass
        return objects
    
    def _parse_der_cert(self, data: bytes) -> Optional[ParsedObject]:
        """Parse DER certificate"""
        try:
            cert = x509.load_der_x509_certificate(data, default_backend())
            obj = self._parse_x509_cert(cert)
            obj.raw_der = data
            return obj
        except Exception:
            return None
    
    def _parse_der_key(self, data: bytes, password: Optional[str] = None) -> Optional[ParsedObject]:
        """Parse DER private key"""
        try:
            pwd = password.encode() if password else None
            key = serialization.load_der_private_key(data, password=pwd, backend=default_backend())
            obj = self._parse_private_key(key)
            obj.raw_der = data
            return obj
        except Exception:
            return None
    
    def _get_key_info(self, key) -> Tuple[str, int]:
        """Extract algorithm and size from any key type"""
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        
        if isinstance(key, (rsa.RSAPublicKey, rsa.RSAPrivateKey)):
            return "RSA", key.key_size
        elif isinstance(key, (ec.EllipticCurvePublicKey, ec.EllipticCurvePrivateKey)):
            return f"EC {key.curve.name}", key.key_size
        elif isinstance(key, (ed25519.Ed25519PublicKey, ed25519.Ed25519PrivateKey)):
            return "Ed25519", 256
        elif isinstance(key, (ed448.Ed448PublicKey, ed448.Ed448PrivateKey)):
            return "Ed448", 448
        else:
            return "Unknown", 0
