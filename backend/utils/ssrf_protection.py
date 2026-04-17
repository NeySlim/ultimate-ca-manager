"""SSRF protection utilities — validate URLs/hosts don't resolve to private IPs."""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


def validate_url_not_private(url: str) -> None:
    """Validate that a URL doesn't resolve to a private/reserved IP.
    
    Raises ValueError if the URL host resolves to private, loopback,
    reserved, or link-local addresses.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")
    validate_host_not_private(host)


def validate_host_not_private(host: str) -> None:
    """Validate that a hostname doesn't resolve to a private/reserved IP.
    
    Raises ValueError if the host resolves to private, loopback,
    reserved, or link-local addresses.
    """
    # First check if host is already an IP
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise ValueError(f"Host {host} is a private/reserved IP address")
        return
    except ValueError as e:
        if "private" in str(e) or "reserved" in str(e):
            raise
        # Not an IP, resolve it
    
    try:
        addrs = socket.getaddrinfo(host, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
                raise ValueError(f"Host {host} resolves to private/reserved IP {ip}")
    except socket.gaierror:
        # Cannot resolve — not a SSRF risk (can't reach internal services)
        pass


# Cloud metadata endpoints and loopback — NEVER legitimate targets for
# outbound HTTP from UCM. Unlike validate_url_not_private (which also blocks
# RFC1918 private ranges), this narrow check allows admins to legitimately
# point UCM at internal infrastructure (AD, Keycloak on 10.x, internal ACME
# CAs, on-prem IdP) while still blocking the highest-impact SSRF targets:
# cloud instance metadata services (which leak IAM credentials) and loopback
# (which would let attackers probe UCM's own internal endpoints).
_CLOUD_METADATA_IPS = {
    '169.254.169.254',          # AWS, Azure, DigitalOcean, GCP (also link-local)
    '100.100.100.200',          # Alibaba Cloud
    'fd00:ec2::254',            # AWS IPv6
}
_CLOUD_METADATA_HOSTS = {
    'metadata.google.internal',
    'metadata',                 # GCP short name
    'metadata.goog',
}


def validate_url_not_cloud_metadata(url: str) -> None:
    """Validate that a URL doesn't target cloud metadata services or loopback.

    This is a *narrow* SSRF guard — it explicitly ALLOWS RFC1918 private IPs
    (10.x, 192.168.x, 172.16.x) because UCM is commonly configured against
    internal infrastructure (AD, internal Keycloak, on-prem IdP, internal
    ACME CAs). It blocks only the highest-impact SSRF targets:

    - Cloud instance metadata endpoints (credential exfiltration)
    - Loopback (would let a compromised admin probe UCM's own internals)

    Raises ValueError if the URL targets a forbidden endpoint.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    host_l = host.lower().rstrip('.')

    # Short-circuit: explicit bad hostnames
    if host_l in _CLOUD_METADATA_HOSTS:
        raise ValueError(f"Host {host} is a cloud metadata endpoint")

    # Check literal IP
    try:
        ip = ipaddress.ip_address(host)
        if str(ip) in _CLOUD_METADATA_IPS:
            raise ValueError(f"Host {host} is a cloud metadata IP")
        if ip.is_loopback:
            raise ValueError(f"Host {host} is a loopback address")
        return
    except ValueError as e:
        if "metadata" in str(e) or "loopback" in str(e):
            raise
        # Not a literal IP — fall through to DNS resolution

    # Resolve hostname and check all returned IPs
    try:
        addrs = socket.getaddrinfo(host, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if str(ip) in _CLOUD_METADATA_IPS:
                raise ValueError(f"Host {host} resolves to cloud metadata IP {ip}")
            if ip.is_loopback:
                raise ValueError(f"Host {host} resolves to loopback {ip}")
    except socket.gaierror:
        # Cannot resolve — not a SSRF risk (can't reach anything)
        pass
