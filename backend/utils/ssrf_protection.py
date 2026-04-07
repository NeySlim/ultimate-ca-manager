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
