"""
Discovery helpers — module-level constants and pure utility functions.
"""
import ipaddress
import threading
from datetime import datetime
from typing import Optional, Tuple
from utils.datetime_utils import to_naive_utc

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

# Upper bound on hosts expanded from a single CIDR. A /16 (65 534 hosts) is a
# generous ceiling for one scan; anything larger (e.g. a /8 = 16M hosts) would
# materialise millions of job tuples and exhaust memory before scanning starts.
_MAX_SCAN_HOSTS = 65536

# Upper bound on total probes (host × port pairs) for one scan. The host cap
# alone still lets a /16 across 9 ports expand to ~590k probes — days of
# scanning and hundreds of MB of queued work (#293).
_MAX_SCAN_JOBS = 65536


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
    """Parse an ISO datetime into naive UTC, the form every DateTime column stores."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return to_naive_utc(val)
    try:
        return to_naive_utc(datetime.fromisoformat(val.replace('Z', '+00:00')))
    except (ValueError, AttributeError):
        return None
