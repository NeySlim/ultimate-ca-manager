"""SSRF protection utilities — validate URLs/hosts don't resolve to private IPs."""

import ipaddress
import logging
import socket
import threading
from contextlib import contextmanager
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

# Deny-list as parsed IP objects so an IPv4-mapped IPv6 form (::ffff:a.b.c.d) can't
# evade a string comparison by re-encoding an IPv4 target as IPv6.
_CLOUD_METADATA_IP_OBJS = {ipaddress.ip_address(a) for a in _CLOUD_METADATA_IPS}


def _forbidden_ip_reason(ip):
    """Why `ip` (an ipaddress object) is a forbidden SSRF target — cloud metadata,
    loopback, or unspecified (0.0.0.0 / ::, which route to loopback on most OSes) — or
    None. IPv4-mapped IPv6 is collapsed to IPv4 first so it can't slip past the checks."""
    mapped = getattr(ip, 'ipv4_mapped', None)
    if mapped is not None:
        ip = mapped
    if ip in _CLOUD_METADATA_IP_OBJS:
        return "cloud metadata IP"
    if ip.is_loopback or ip.is_unspecified:
        return "loopback/unspecified address"
    return None


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
        reason = _forbidden_ip_reason(ip)
        if reason:
            raise ValueError(f"Host {host} is a {reason}")
        return
    except ValueError as e:
        if "metadata" in str(e) or "loopback" in str(e) or "unspecified" in str(e):
            raise
        # Not a literal IP — fall through to DNS resolution

    # Resolve hostname and check all returned IPs
    try:
        addrs = socket.getaddrinfo(host, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            reason = _forbidden_ip_reason(ip)
            if reason:
                raise ValueError(f"Host {host} resolves to {reason} {ip}")
    except socket.gaierror:
        # Cannot resolve — not a SSRF risk (can't reach anything)
        pass


# ---------------------------------------------------------------------------
# DNS-rebinding-safe outbound HTTP
# ---------------------------------------------------------------------------
#
# validate_url_not_cloud_metadata() resolves the hostname once, but the
# subsequent requests.* call resolves it AGAIN. A hostile / compromised DNS
# server can return a benign IP for the validation lookup and a forbidden
# IP (cloud metadata, loopback, etc.) for the connection lookup — classic
# DNS rebinding.
#
# The standard mitigation is to resolve once, validate the IP, and then
# pin the connection to that exact IP while preserving the original
# hostname for SNI + certificate verification. We implement that by
# installing a thread-local override of urllib3's create_connection.
#
# Caller responsibility: only use safe_request_post() / safe_request_get()
# for outbound HTTP whose URL is provided by an authenticated UCM admin
# (webhooks, SSO discovery, etc.). Do NOT use it for ACME/CDP/OCSP — those
# are protocol-driven and have their own validation.

_pinned_resolution = threading.local()


def _patched_create_connection(address, *args, **kwargs):
    """urllib3.util.connection.create_connection wrapper that re-routes
    the connection to a thread-locally pinned IP while keeping the
    original hostname intact for SNI / cert verification."""
    pinned = getattr(_pinned_resolution, 'host_to_ip', None)
    if pinned:
        host, port = address
        ip = pinned.get(host.lower().rstrip('.'))
        if ip:
            address = (ip, port)
    return _orig_create_connection(address, *args, **kwargs)


# Lazy import & patch — only when a caller actually wants safe outbound HTTP.
_orig_create_connection = None
_patch_lock = threading.Lock()


def _ensure_urllib3_patched():
    global _orig_create_connection
    if _orig_create_connection is not None:
        return
    with _patch_lock:
        if _orig_create_connection is not None:
            return
        from urllib3.util import connection as urllib3_connection
        _orig_create_connection = urllib3_connection.create_connection
        urllib3_connection.create_connection = _patched_create_connection


@contextmanager
def _pin_host(host: str, ip: str):
    """Within this block, all urllib3 connections to `host` go to `ip`."""
    _ensure_urllib3_patched()
    pinned = getattr(_pinned_resolution, 'host_to_ip', None)
    if pinned is None:
        pinned = {}
        _pinned_resolution.host_to_ip = pinned
    key = host.lower().rstrip('.')
    prev = pinned.get(key)
    pinned[key] = ip
    try:
        yield
    finally:
        if prev is None:
            pinned.pop(key, None)
        else:
            pinned[key] = prev


def _resolve_and_validate(url: str) -> tuple:
    """Resolve URL hostname to a single safe IP. Returns (host, ip).

    Raises ValueError if the URL has no hostname, fails to resolve,
    or every resolved IP is forbidden (cloud metadata / loopback)."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    # Already a literal IP — validate and pin to itself.
    try:
        ip_obj = ipaddress.ip_address(host)
        reason = _forbidden_ip_reason(ip_obj)
        if reason:
            raise ValueError(f"Host {host} is a {reason}")
        return host, str(ip_obj)
    except ValueError as e:
        if "metadata" in str(e) or "loopback" in str(e) or "unspecified" in str(e):
            raise
        # Not a literal IP — resolve below.

    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve {host}: {e}")

    chosen = None
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        reason = _forbidden_ip_reason(ip)
        if reason:
            raise ValueError(f"Host {host} resolves to {reason} {ip}")
        if chosen is None:
            chosen = str(ip)

    if chosen is None:
        raise ValueError(f"Host {host} produced no usable IPs")

    return host, chosen


def safe_request_post(url, **kwargs):
    """requests.post() with DNS-rebinding protection.

    Resolves the URL hostname once, validates it against the cloud-metadata
    deny-list, and pins the underlying TCP connection to that exact IP for
    the duration of the call. SNI and certificate verification continue to
    use the original hostname so HTTPS works normally.
    """
    import requests
    host, ip = _resolve_and_validate(url)
    with _pin_host(host, ip):
        return requests.post(url, **kwargs)


def safe_request_get(url, **kwargs):
    """requests.get() counterpart of safe_request_post()."""
    import requests
    host, ip = _resolve_and_validate(url)
    with _pin_host(host, ip):
        return requests.get(url, **kwargs)
