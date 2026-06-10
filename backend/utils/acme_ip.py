"""ACME IP address utilities for RFC 8738 support

Provides validation, formatting, and reverse mapping for IP identifiers
used in ACME certificate issuance (RFC 8738).
"""
import ipaddress
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


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
