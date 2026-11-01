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
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import ExtensionOID

from fips_mode import FipsRestricted
from utils.csr_extensions import csr_extensions
from utils.key_codec import MalformedKey, load_private_key_any, normalize_private_key_pem
from utils import pkcs12_layers
from utils.pkcs12_import import load_key_and_certificates, looks_like_pkcs12, refuse_pkcs12_import

WRONG_PASSWORD = 'Private key could not be decrypted with any of the passwords given'
NOT_TRIED = 'Password not tried: this import already made too many password attempts'

# Key derivations one parse may run, whatever the number of passwords and encrypted objects
# (a PKCS#12 costs one per MAC, encryptedData layer and shrouded key, per password)
MAX_PASSWORD_ATTEMPTS = 64
# Far above what OpenSSL and pyca produce: a costlier derivation is refused, never run
MAX_KDF_ITERATIONS = 2_000_000
MAX_SCRYPT_N = 1 << 20
MAX_SCRYPT_WORK = MAX_SCRYPT_N * 8  # N * r * p

_PBES2 = '1.2.840.113549.1.5.13'
_PBKDF2 = '1.2.840.113549.1.5.12'
_PBMAC1 = '1.2.840.113549.1.5.14'
_SCRYPT = '1.3.6.1.4.1.11591.4.11'
# PBES1 (RFC 8018) and PKCS#12 PBE (RFC 7292) parameters: SEQUENCE { salt, iterations }
_SALT_ITERATIONS_ARCS = ('1.2.840.113549.1.5.', '1.2.840.113549.1.12.1.')
_SEALED_PEM = re.compile(rb'-----BEGIN\s+ENCRYPTED\s+PRIVATE\s+KEY-----([A-Za-z0-9+/=\s]+)-----END')


class PasswordNotTried(Exception):
    """An encrypted object no password was tried on; the message says why."""


class _Attempts:
    """The key derivations left to one parse."""

    def __init__(self, left: int = MAX_PASSWORD_ATTEMPTS):
        self.left = left

    def spend(self, count: int = 1) -> None:
        """Spend *count* derivations, or none and refuse when fewer are left."""
        if count > self.left:
            raise PasswordNotTried(NOT_TRIED)
        self.left -= count


def _is_wrong_password(exc: Exception) -> bool:
    """pyca's ValueError for an encrypted key the password does not open."""
    return 'password' in str(exc).lower()


def _sealed_algorithm(der: bytes) -> Optional[bytes]:
    """DER of the encryptionAlgorithm of an EncryptedPrivateKeyInfo (RFC 5958), None for anything else."""
    from pyasn1.codec.ber import decoder
    from pyasn1.codec.der import encoder
    from pyasn1_modules import rfc5958
    try:
        info, rest = decoder.decode(der, asn1Spec=rfc5958.EncryptedPrivateKeyInfo())
    except Exception:
        return None
    return None if rest else encoder.encode(info['encryptionAlgorithm'])


def _is_encrypted_pkcs8(der: bytes) -> bool:
    """Whether *der* is an EncryptedPrivateKeyInfo, as 'ENCRYPTED' tells a PEM block."""
    return _sealed_algorithm(der) is not None


def _sealed_key_algorithm(data) -> Optional[bytes]:
    """``_sealed_algorithm`` of an encrypted PKCS#8 given as PEM or DER."""
    raw = data.encode() if isinstance(data, str) else bytes(data)
    match = _SEALED_PEM.search(raw)
    if match:
        try:
            raw = base64.b64decode(b''.join(match.group(1).split()))
        except Exception:
            return None
    elif raw.lstrip().startswith(b'-----'):
        return None
    return _sealed_algorithm(raw)


def kdf_refusal(algorithm_der: bytes) -> Optional[str]:
    """Why the key derivation an AlgorithmIdentifier names is too costly to run, else None.
    Parameters this cannot read are left to pyca, which reads them before deriving."""
    from pyasn1.codec.ber import decoder
    from pyasn1.codec.der import encoder
    from pyasn1_modules import rfc5280, rfc7914, rfc8018
    try:
        alg, _ = decoder.decode(algorithm_der, asn1Spec=rfc5280.AlgorithmIdentifier())
        oid = str(alg['algorithm'])
        params = bytes(alg['parameters']) if alg['parameters'].isValue else b''
        if oid in (_PBES2, _PBMAC1):
            spec = rfc8018.PBES2_params() if oid == _PBES2 else rfc8018.PBMAC1_params()
            return kdf_refusal(encoder.encode(decoder.decode(params, asn1Spec=spec)[0]['keyDerivationFunc']))
        if oid == _SCRYPT:
            p = decoder.decode(params, asn1Spec=rfc7914.Scrypt_params())[0]
            n = int(p['costParameter'])
            if n > MAX_SCRYPT_N or n * int(p['blockSize']) * int(p['parallelizationParameter']) > MAX_SCRYPT_WORK:
                return f'Key derivation refused: scrypt with N={n} costs more than this instance runs'
            return None
        if oid == _PBKDF2:
            iterations = int(decoder.decode(params, asn1Spec=rfc8018.PBKDF2_params())[0]['iterationCount'])
        elif oid.startswith(_SALT_ITERATIONS_ARCS):
            iterations = int(decoder.decode(params)[0][1])
        else:
            return None
    except Exception:
        return None
    if iterations > MAX_KDF_ITERATIONS:
        return f'Key derivation refused: {iterations} iterations, at most {MAX_KDF_ITERATIONS} are run'
    return None


def pkcs12_kdf_refusal(data: bytes) -> Optional[str]:
    """``kdf_refusal`` for the MAC of a PKCS#12 and the encryptions readable without its password."""
    from asn1crypto import core
    from asn1crypto import pkcs12 as asn1_pkcs12
    try:
        pfx = asn1_pkcs12.Pfx.load(bytes(data))
        algorithms = []
        mac = pfx['mac_data']
        if not isinstance(mac, core.Void):
            iterations = mac['iterations'].native
            if iterations > MAX_KDF_ITERATIONS:
                return (f'Key derivation refused: a PKCS#12 MAC of {iterations} iterations, '
                        f'at most {MAX_KDF_ITERATIONS} are run')
            algorithms.append(mac['mac']['digest_algorithm'].dump())
        for info in pfx.authenticated_safe:
            kind = info['content_type'].native
            if kind == 'encrypted_data':
                algorithms.append(
                    info['content']['encrypted_content_info']['content_encryption_algorithm'].dump())
            elif kind == 'data':
                algorithms += pkcs12_layers.shrouded_algorithms(info['content'].native)
    except Exception:
        return None
    return next((r for r in map(kdf_refusal, algorithms) if r), None)


def _password_failed(exc: Exception, data: bytes) -> bool:
    """A wrong password can also unpad by chance: a decoding failure on an encrypted key is the password's."""
    return _is_wrong_password(exc) or _is_encrypted_pkcs8(data)


def _candidates(password) -> List[Optional[bytes]]:
    """The passwords to try in turn: one, or several (the import form's per-file ones); [None] for none."""
    values = [password] if password is None or isinstance(password, (str, bytes)) else list(password)
    out: List[Optional[bytes]] = []
    for value in values:
        raw = value.encode() if isinstance(value, str) else value
        if raw and raw not in out:
            out.append(raw)
    return out or [None]


def _load_key(data, password, attempts: _Attempts):
    """load_private_key_any with each candidate password; the last failure when none opens the key.
    Each password tried on an encrypted key spends an attempt; a key that is not encrypted, none."""
    sealed = _sealed_key_algorithm(data)
    if sealed is None:
        return load_private_key_any(data, password=None)
    candidates = _candidates(password)
    if candidates[0] is not None and (refusal := kdf_refusal(sealed)):
        raise PasswordNotTried(refusal)
    failure = None
    for pwd in candidates:
        if pwd is not None:
            attempts.spend()
        try:
            return load_private_key_any(data, password=pwd)
        except (FipsRestricted, MalformedKey):
            raise
        except (TypeError, ValueError) as e:
            failure = e
    raise failure


def _load_pkcs12(data: bytes, password, attempts: _Attempts):
    """load_key_and_certificates with each candidate password; the last failure when none opens it.
    The encryptedData layers are opened here first, so a shrouded key inside is costed before
    pyca derives it; every derivation, here or in pyca (MAC, layers, keys), spends an attempt."""
    from asn1crypto import pkcs12 as asn1_pkcs12
    if not looks_like_pkcs12(data):  # pyca would refuse it before deriving anything
        raise ValueError('Not a PKCS#12')
    refusal = pkcs12_kdf_refusal(data)
    if refusal:
        raise PasswordNotTried(refusal)
    try:
        pfx = asn1_pkcs12.Pfx.load(bytes(data))
        layers = pkcs12_layers.encrypted_layers(pfx)
        plain = [alg for contents in pkcs12_layers.plain_safe_contents(pfx)
                 for alg in pkcs12_layers.shrouded_algorithms(contents)]
    except pkcs12_layers.LayerUnsupported as e:
        raise PasswordNotTried(str(e)) from e
    except Exception as e:  # noqa: BLE001: bags that cannot be inspected are not handed on
        raise ValueError('Unreadable PKCS#12 bags') from e
    failure = None
    for pwd in _candidates(password):
        attempts.spend(len(layers))
        try:
            opened = [pkcs12_layers.open_layer(layer, pwd) for layer in layers]
            shrouded = plain + [alg for contents in opened
                                for alg in pkcs12_layers.shrouded_algorithms(contents)]
        except pkcs12_layers.LayerUnsupported as e:
            raise PasswordNotTried(str(e)) from e
        except pkcs12_layers.WrongPassword as e:
            failure = e
            continue
        refusal = next((r for r in map(kdf_refusal, shrouded) if r), None)
        if refusal:
            raise PasswordNotTried(refusal)
        attempts.spend(1 + len(layers) + len(shrouded))
        try:
            return load_key_and_certificates(data, pwd)
        except FipsRestricted:
            raise
        except Exception as e:  # noqa: BLE001: the next password may open it
            failure = e
    raise failure


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
    key_cert_sign: bool = False
    is_self_signed: bool = False
    san_dns: List[str] = field(default_factory=list)
    san_ip: List[str] = field(default_factory=list)
    san_email: List[str] = field(default_factory=list)
    san_uri: List[str] = field(default_factory=list)
    ski: Optional[str] = None  # Subject Key Identifier (hex)
    aki: Optional[str] = None  # Authority Key Identifier (hex)
    
    # Key-specific
    key_algorithm: str = ""
    key_size: Optional[int] = 0  # None for a post-quantum key
    is_encrypted: bool = False
    error: Optional[str] = None  # why a key that was read cannot be used
    
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
            "key_cert_sign": self.key_cert_sign,
            "is_self_signed": self.is_self_signed,
            "san_dns": self.san_dns,
            "san_ip": self.san_ip,
            "san_email": self.san_email,
            "san_uri": self.san_uri,
            "key_algorithm": self.key_algorithm,
            "key_size": self.key_size,
            "is_encrypted": self.is_encrypted,
            "error": self.error,
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

    def __init__(self, shared_budget: bool = False):
        # shared_budget: every parse() of this parser draws on one budget (one request, several parses)
        self._shared = shared_budget
        self._attempts = _Attempts()

    def parse(self, content: str | bytes, password=None) -> List[ParsedObject]:
        """
        Parse any input and return list of detected objects.

        Args:
            content: PEM string, DER bytes, or base64-encoded data
            password: Optional password for encrypted keys/PKCS12, or a list of them tried in turn;
                at most MAX_PASSWORD_ATTEMPTS tries on encrypted objects per call, or per parser
                built with ``shared_budget``

        Returns:
            List of ParsedObject instances
        """
        if not self._shared:
            self._attempts = _Attempts()
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
            except FipsRestricted:
                raise
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
    
    def _parse_pseudo_pem_binary(self, content: str, password=None) -> List[ParsedObject]:
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
            except FipsRestricted:
                raise
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
    
    def _parse_binary(self, data: bytes, password=None) -> List[ParsedObject]:
        """Parse binary data (DER, PKCS12, PKCS7)"""
        objects: List[ParsedObject] = []
        
        # Try PKCS12 first (most common binary format)
        refuse_pkcs12_import(data)
        try:
            private_key, cert, additional_certs = _load_pkcs12(data, password, self._attempts)
            
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
        except FipsRestricted:
            raise
        except PasswordNotTried as e:
            return [self._sealed_der_key(data, str(e))]
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
            key = _load_key(data, password, self._attempts)
            obj = self._parse_private_key(key)
            obj.raw_der = data
            return [obj]
        except FipsRestricted:
            raise
        except MalformedKey as e:
            return [self._malformed_der_key(data, e)]
        except PasswordNotTried as e:
            return [self._sealed_der_key(data, str(e))]
        except ValueError as e:
            if _candidates(password)[0] and _password_failed(e, data):
                return [self._sealed_der_key(data)]
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
    
    def _parse_pem_keys(self, content: str, password=None) -> List[ParsedObject]:
        """Extract all PEM private keys"""
        objects = []
        seen_positions = set()  # Deduplicate by position
        pwd = _candidates(password)[0]  # whether any password was given
        
        for pattern in self.PEM_KEY_PATTERNS:
            for match in pattern.finditer(content):
                # Skip if we already processed a key at this position
                if match.start() in seen_positions:
                    continue
                seen_positions.add(match.start())
                
                pem_block = match.group(0)
                is_encrypted = 'ENCRYPTED' in pem_block
                
                try:
                    key = _load_key(pem_block, password, self._attempts)
                    obj = self._parse_private_key(key)
                    # an encrypted block keeps the decrypted PKCS#8: matcher and importer read it without a password
                    if not is_encrypted:
                        pem_block = normalize_private_key_pem(pem_block)  # ML-DSA "both" -> seed
                        obj.raw_pem = pem_block
                    obj.index = match.start()
                    obj.is_encrypted = is_encrypted
                    objects.append(obj)
                except FipsRestricted:
                    raise
                except MalformedKey as e:
                    objects.append(ParsedObject(
                        type=ObjectType.PRIVATE_KEY, raw_pem=pem_block, index=match.start(),
                        is_encrypted=is_encrypted, key_algorithm="invalid", error=str(e)))
                except Exception as e:
                    # Encrypted without a password, with a wrong one or none tried: the latter two are errors
                    obj = ParsedObject(
                        type=ObjectType.PRIVATE_KEY,
                        raw_pem=pem_block,
                        index=match.start(),
                        is_encrypted=True,
                        key_algorithm="unknown (encrypted)",
                        error=(str(e) if isinstance(e, PasswordNotTried)
                               else WRONG_PASSWORD if pwd and is_encrypted else None),
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
                    obj.key_algorithm, obj.key_size = self._public_key_info(csr)
                    
                    # Extract SANs if present
                    try:
                        san_ext = csr_extensions(csr).get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                        for name in san_ext.value:
                            if isinstance(name, x509.DNSName):
                                obj.san_dns.append(name.value)
                            elif isinstance(name, x509.IPAddress):
                                obj.san_ip.append(str(name.value))
                            elif isinstance(name, x509.RFC822Name):
                                obj.san_email.append(name.value)
                            elif isinstance(name, x509.UniformResourceIdentifier):
                                obj.san_uri.append(name.value)
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
        
        # Check if CA (BasicConstraints) and CA signing capability (KeyUsage)
        try:
            basic_constraints = cert.extensions.get_extension_for_oid(ExtensionOID.BASIC_CONSTRAINTS)
            obj.is_ca = basic_constraints.value.ca
        except x509.ExtensionNotFound:
            obj.is_ca = False
        try:
            key_usage = cert.extensions.get_extension_for_oid(ExtensionOID.KEY_USAGE)
            obj.key_cert_sign = bool(key_usage.value.key_cert_sign)
        except x509.ExtensionNotFound:
            obj.key_cert_sign = False

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
                elif isinstance(name, x509.RFC822Name):
                    obj.san_email.append(name.value)
                elif isinstance(name, x509.UniformResourceIdentifier):
                    obj.san_uri.append(name.value)
        except x509.ExtensionNotFound:
            pass
        
        # Extract SKI/AKI for reliable chain matching
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_KEY_IDENTIFIER)
            obj.ski = ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        try:
            ext = cert.extensions.get_extension_for_oid(ExtensionOID.AUTHORITY_KEY_IDENTIFIER)
            if ext.value.key_identifier:
                obj.aki = ext.value.key_identifier.hex(':').upper()
        except x509.ExtensionNotFound:
            pass
        
        # Key info
        obj.key_algorithm, obj.key_size = self._public_key_info(cert)
        
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
    
    def _parse_pkcs12(self, data: bytes, password=None) -> List[ParsedObject]:
        """Parse PKCS12 binary data"""
        objects = []
        refuse_pkcs12_import()
        try:
            private_key, cert, additional_certs = _load_pkcs12(data, password, self._attempts)
            
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
        except FipsRestricted:
            raise
        except PasswordNotTried as e:
            return [self._sealed_der_key(data, str(e))]
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
    
    def _parse_der_key(self, data: bytes, password=None) -> Optional[ParsedObject]:
        """Parse DER private key"""
        try:
            pwd = _candidates(password)[0]  # whether any password was given
            key = _load_key(data, password, self._attempts)
            obj = self._parse_private_key(key)
            obj.raw_der = data
            return obj
        except FipsRestricted:
            raise
        except MalformedKey as e:
            return self._malformed_der_key(data, e)
        except PasswordNotTried as e:
            return self._sealed_der_key(data, str(e))
        except ValueError as e:
            return self._sealed_der_key(data) if pwd and _password_failed(e, data) else None
        except Exception:
            return None

    @staticmethod
    def _sealed_der_key(data: bytes, error: str = WRONG_PASSWORD) -> ParsedObject:
        """An encrypted key, or PKCS#12, left unopened, with the reason."""
        return ParsedObject(type=ObjectType.PRIVATE_KEY, raw_der=data, is_encrypted=True,
                            key_algorithm="unknown (encrypted)", error=error)

    @staticmethod
    def _malformed_der_key(data: bytes, error: MalformedKey) -> ParsedObject:
        """A DER key that was read but cannot be used, kept with its reason."""
        return ParsedObject(type=ObjectType.PRIVATE_KEY, raw_der=data,
                            key_algorithm="invalid", error=str(error))
    
    def _public_key_info(self, cert_or_csr) -> Tuple[str, Optional[int]]:
        """Algorithm and size of a certificate's or CSR's key; a key pyca cannot load keeps its name or OID."""
        from utils.foreign_algorithms import describe_public_key
        foreign = describe_public_key(cert_or_csr)
        if foreign:
            return foreign['label'], foreign['key_size']
        return self._get_key_info(cert_or_csr.public_key())

    def _get_key_info(self, key) -> Tuple[str, Optional[int]]:
        """Algorithm and size of any key type; a post-quantum key has no size (None)"""
        from cryptography.hazmat.primitives.asymmetric import rsa, ec, ed25519, ed448
        from utils import key_algorithms

        label = key_algorithms.label_for_public_key(key) or key_algorithms.label_for_private_key(key)
        if key_algorithms.is_post_quantum(label):
            return label, None
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
