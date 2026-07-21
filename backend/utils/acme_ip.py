"""ACME IP address utilities for RFC 8738 support

Provides validation, formatting, and reverse mapping for IP identifiers
used in ACME certificate issuance (RFC 8738).
"""
import hashlib
import ipaddress
import logging
import os
import socket
import ssl
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

logger = logging.getLogger(__name__)

ACME_IDENTIFIER_OID = x509.ObjectIdentifier('1.3.6.1.5.5.7.1.31')
TLS_ALPN_PROTOCOL = 'acme-tls/1'


class TlsAlpn01ListenerError(RuntimeError):
    """Raised when the ephemeral TLS-ALPN-01 proof listener cannot start."""


def _tls_alpn_san(identifier: str):
    """Return the RFC 8737/8738 SAN value for an ACME identifier."""
    normalized_ip = normalize_ip_for_identifier(identifier)
    if normalized_ip is not None:
        return x509.IPAddress(ipaddress.ip_address(normalized_ip))
    return x509.DNSName(identifier.rstrip('.'))


def build_tls_alpn01_certificate(identifier: str, key_authorization: str) -> Tuple[bytes, bytes]:
    """Build the short-lived self-signed proof certificate from RFC 8737 §3."""
    if not isinstance(identifier, str) or not identifier:
        raise ValueError('TLS-ALPN-01 identifier is required')
    if not isinstance(key_authorization, str) or not key_authorization:
        raise ValueError('TLS-ALPN-01 key authorization is required')

    key = ec.generate_private_key(ec.SECP256R1(), default_backend())
    now = datetime.now(timezone.utc)
    digest = hashlib.sha256(key_authorization.encode('utf-8')).digest()
    # UnrecognizedExtension receives the ASN.1 extension value itself. RFC 8737
    # defines that value as an OCTET STRING containing the 32-byte SHA-256 hash.
    acme_identifier_der = b'\x04\x20' + digest
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, identifier)])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=1))
        .add_extension(
            x509.SubjectAlternativeName([_tls_alpn_san(identifier)]),
            critical=False,
        )
        .add_extension(
            x509.UnrecognizedExtension(ACME_IDENTIFIER_OID, acme_identifier_der),
            critical=True,
        )
        .sign(key, hashes.SHA256(), default_backend())
    )
    return (
        certificate.public_bytes(serialization.Encoding.PEM),
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ),
    )


class TlsAlpn01Listener:
    """Ephemeral raw-socket TLS listener serving one ACME proof certificate."""

    def __init__(
        self,
        identifier: str,
        key_authorization: str,
        *,
        port: int = 443,
        bind_host: Optional[str] = None,
    ):
        self.identifier = identifier
        self.key_authorization = key_authorization
        self.port = int(port)
        self.bind_host = bind_host
        self._socket = None
        self._thread = None
        self._stop_event = threading.Event()
        self._context = None

    @property
    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def _bind_candidates(self):
        if self.bind_host:
            try:
                parsed = ipaddress.ip_address(self.bind_host)
                family = socket.AF_INET6 if parsed.version == 6 else socket.AF_INET
            except ValueError:
                family = socket.AF_UNSPEC
            return [(family, self.bind_host)]

        normalized_ip = normalize_ip_for_identifier(self.identifier)
        if normalized_ip and ipaddress.ip_address(normalized_ip).version == 6:
            return [(socket.AF_INET6, '::')]
        # Prefer a dual-stack IPv6 socket for DNS names, then fall back to IPv4.
        return [
            (socket.AF_INET6, '::'),
            (socket.AF_INET, '0.0.0.0'),  # noqa: S104 - ACME CA must reach the proof listener
        ]

    def _build_context(self) -> ssl.SSLContext:
        cert_pem, key_pem = build_tls_alpn01_certificate(
            self.identifier, self.key_authorization
        )
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.set_alpn_protocols([TLS_ALPN_PROTOCOL])

        with tempfile.TemporaryDirectory(prefix='ucm-acme-alpn-') as temp_dir:
            cert_path = os.path.join(temp_dir, 'challenge.crt')
            key_path = os.path.join(temp_dir, 'challenge.key')
            with open(cert_path, 'wb') as cert_file:
                cert_file.write(cert_pem)
            with open(key_path, 'wb') as key_file:
                key_file.write(key_pem)
            os.chmod(cert_path, 0o600)
            os.chmod(key_path, 0o600)
            context.load_cert_chain(cert_path, key_path)

        # A callback is required when this listener is extended to host several
        # simultaneous proofs. For this single-proof listener it deliberately
        # keeps the challenge context selected for every valid SNI form,
        # including RFC 8738 reverse-pointer SNI for IP identifiers.
        def select_challenge_context(tls_socket, _server_name, _initial_context):
            tls_socket.context = context

        context.set_servername_callback(select_challenge_context)
        return context

    def _create_bound_socket(self):
        last_error = None
        for family, host in self._bind_candidates():
            try:
                if family == socket.AF_UNSPEC:
                    addresses = socket.getaddrinfo(
                        host, self.port, type=socket.SOCK_STREAM,
                        flags=socket.AI_PASSIVE,
                    )
                    family, socktype, proto, _, sockaddr = addresses[0]
                else:
                    socktype = socket.SOCK_STREAM
                    proto = 0
                    sockaddr = (host, self.port, 0, 0) if family == socket.AF_INET6 else (host, self.port)

                listener = socket.socket(family, socktype, proto)
                try:
                    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    if family == socket.AF_INET6 and self.bind_host is None:
                        listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
                    listener.bind(sockaddr)
                    listener.listen(16)
                    listener.settimeout(0.25)
                    self.port = listener.getsockname()[1]
                    return listener
                except Exception:
                    listener.close()
                    raise
            except OSError as exc:
                last_error = exc

        detail = str(last_error) if last_error else 'no usable bind address'
        raise TlsAlpn01ListenerError(
            f'TLS-ALPN-01 cannot listen on TCP port {self.port}: {detail}. '
            'Free the port or use http-01/dns-01 instead.'
        )

    def start(self) -> None:
        if self.is_running:
            return
        if not 0 <= self.port <= 65535:
            raise TlsAlpn01ListenerError('TLS-ALPN-01 listen port must be between 0 and 65535')

        self._stop_event.clear()
        self._context = self._build_context()
        self._socket = self._create_bound_socket()
        self._thread = threading.Thread(
            target=self._serve,
            name=f'acme-tls-alpn-{self.port}',
            daemon=True,
        )
        self._thread.start()
        logger.info('TLS-ALPN-01 listener started on port %s for %s', self.port, self.identifier)

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                connection, _peer = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            try:
                connection.settimeout(5)
                with self._context.wrap_socket(connection, server_side=True):
                    pass
            except (OSError, ssl.SSLError) as exc:
                logger.debug('TLS-ALPN-01 handshake ended: %s', exc)
            finally:
                try:
                    connection.close()
                except OSError:
                    pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._socket is not None:
            try:
                self._socket.close()
            except OSError:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._socket = None
        self._thread = None
        self._context = None


def is_ip_identifier(identifier: dict) -> bool:
    """Check if identifier is an IP address (RFC 8738)
    
    Args:
        identifier: Dict with 'type' and 'value' keys
        
    Returns:
        True if identifier type is 'ip'
    """
    return identifier.get('type') == 'ip'


def validate_ip_address(ip_str: str) -> Tuple[bool, Optional[str]]:
    """Validate IP address format per RFC 1123 (IPv4) and RFC 5952 (IPv6)
    
    Args:
        ip_str: IP address string to validate
        
    Returns:
        Tuple of (is_valid, canonical_form_or_error)
        
    Examples:
        >>> validate_ip_address('192.0.2.1')
        (True, '192.0.2.1')
        >>> validate_ip_address('2001:db8::1')
        (True, '2001:db8::1')
        >>> validate_ip_address('invalid')
        (False, 'Invalid IP address format')
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        # Return canonical form
        return True, str(ip)
    except ValueError as e:
        return False, f'Invalid IP address format: {str(e)}'


def normalize_ip_for_identifier(ip_str: str) -> Optional[str]:
    """Normalize IP address for ACME identifier value (RFC 8738)
    
    Returns canonical form suitable for use in ACME identifier 'value' field.
    IPv6 addresses are compressed per RFC 5952.
    
    Args:
        ip_str: IP address string
        
    Returns:
        Canonical IP string or None if invalid
    """
    is_valid, result = validate_ip_address(ip_str)
    if is_valid:
        return result
    return None


def ip_to_reverse_ptr(ip_str: str) -> Optional[str]:
    """Convert IP address to reverse DNS PTR name for tls-alpn-01 SNI
    
    Per RFC 8738 Section 6, tls-alpn-01 for IP identifiers must use
    the reverse mapping (IN-ADDR.ARPA or IP6.ARPA) as the SNI HostName.
    
    Args:
        ip_str: IP address string (IPv4 or IPv6)
        
    Returns:
        Reverse PTR name or None if invalid
        
    Examples:
        >>> ip_to_reverse_ptr('192.0.2.1')
        '1.2.0.192.in-addr.arpa'
        >>> ip_to_reverse_ptr('2001:db8::1')
        '1.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.0.8.b.d.0.1.0.0.2.ip6.arpa'
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.reverse_pointer
    except ValueError:
        return None


def format_ip_for_url(ip_str: str) -> str:
    """Format an IP address for use as the host part of a URL (RFC 3986)

    IPv6 literals MUST be wrapped in square brackets when used in a URL,
    otherwise the colons are misparsed (e.g. ``http://2001:db8::1/`` is
    rejected by most HTTP clients). IPv4 and hostnames are returned as-is.

    Args:
        ip_str: IP address (or hostname) string

    Returns:
        Bracketed form for IPv6, unchanged otherwise

    Examples:
        >>> format_ip_for_url('192.0.2.1')
        '192.0.2.1'
        >>> format_ip_for_url('2001:db8::1')
        '[2001:db8::1]'
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.version == 6:
            return f'[{ip_str}]'
    except ValueError:
        pass
    return ip_str


def is_ip_private(ip_str: str) -> bool:
    """Check if IP address is private/reserved (for SSRF protection)
    
    Args:
        ip_str: IP address string
        
    Returns:
        True if IP is private, loopback, or reserved
    """
    try:
        ip = ipaddress.ip_address(ip_str)
        return ip.is_private or ip.is_loopback or ip.is_reserved
    except ValueError:
        return False


def extract_ip_from_csr_san(csr) -> list:
    """Extract IP addresses from CSR SubjectAlternativeName extension
    
    Args:
        csr: cryptography x509.CertificateSigningRequest object
        
    Returns:
        List of IP address strings found in CSR SANs
    """
    from cryptography import x509
    
    ip_addresses = []
    try:
        san_ext = csr.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san = san_ext.value
        
        # Get all IP addresses from SAN
        for ip in san.get_values_for_type(x509.IPAddress):
            ip_addresses.append(str(ip))
    except x509.ExtensionNotFound:
        pass
    except Exception as e:
        logger.error(f"Error extracting IPs from CSR SAN: {e}")
    
    return ip_addresses
