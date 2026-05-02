"""
Discovery helpers — module-level constants and pure utility functions.
"""
import ipaddress
import threading
from datetime import datetime
from typing import Optional, Tuple

# Private/reserved IP ranges — block SSRF via scan targets
# Note: RFC1918 private ranges (10/8, 172.16/12, 192.168/16) are intentionally
# allowed — scanning internal networks for certificates is a core use case.
_BLOCKED_NETWORKS = [
    ipaddress.ip_network('169.254.0.0/16'),     # Link-local
    ipaddress.ip_network('224.0.0.0/4'),        # Multicast
    ipaddress.ip_network('240.0.0.0/4'),        # Reserved
    ipaddress.ip_network('fe80::/10'),          # IPv6 link-local
    ipaddress.ip_network('ff00::/8'),           # IPv6 multicast
]
# Note: loopback (127/8, ::1) is intentionally allowed — UCM is on-prem and
# admins legitimately scan services bound to localhost on the UCM host.
# Note: RFC1918 ranges (10/8, 172.16/12, 192.168/16) are intentionally allowed
# — scanning internal networks for certificates is a core use case.

# Concurrent scan rate limiting — prevents resource exhaustion
_MAX_CONCURRENT_SCANS = 3
_scan_semaphore = threading.Semaphore(_MAX_CONCURRENT_SCANS)


def _is_blocked_ip(host: str) -> bool:
    """Check if host IP is in a blocked range (link-local/multicast/reserved only)."""
    try:
        addr = ipaddress.ip_address(host)
        if addr.is_link_local or addr.is_multicast or addr.is_reserved:
            return True
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return True
    except ValueError:
        pass  # Not an IP — hostname, check after DNS resolution
    return False


def _validate_port(port) -> int:
    """Validate port number is in valid TCP range."""
    try:
        p = int(port)
        if 1 <= p <= 65535:
            return p
    except (ValueError, TypeError):
        pass
    return 0


def _parse_target(raw: str) -> Tuple[str, Optional[int]]:
    """Parse 'host' or 'host:port' string."""
    raw = raw.strip()
    if not raw:
        return ('', None)
    if raw.startswith('['):
        if ']:' in raw:
            host, port_s = raw.rsplit(':', 1)
            return (host.strip('[]'), int(port_s))
        return (raw.strip('[]'), None)
    if ':' in raw:
        parts = raw.rsplit(':', 1)
        try:
            return (parts[0], int(parts[1]))
        except ValueError:
            return (raw, None)
    return (raw, None)


def _parse_iso(val) -> Optional[datetime]:
    """Parse ISO datetime string."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    try:
        return datetime.fromisoformat(val.replace('Z', '+00:00'))
    except (ValueError, AttributeError):
        return None
