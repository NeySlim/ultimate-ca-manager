"""Source networks an API key is limited to (#403).

Same parsing and matching as the admin allowlist (utils/admin_allowlist.py), on the address UCM
resolves for the request (request.remote_addr, after the trusted proxy hops). An empty list admits
any address; a list no entry of which parses admits none.
"""
import ipaddress
import logging
import time

from utils import admin_allowlist

logger = logging.getLogger(__name__)

REFUSAL_MESSAGE = 'This API key is not allowed from this address'
_LOG_INTERVAL = 300.0
_logged = {}


def parse(value) -> list:
    """Canonical list from a JSON list or a comma/newline separated string; ValueError names the entry."""
    if value is None or value == '':
        return []
    return admin_allowlist.parse_entries(value)


def admits(networks, addr) -> bool:
    return not networks or admin_allowlist.address_allowed_by(addr or '', networks)


def _network(entry):
    return ipaddress.ip_network(entry, strict=False)


def within(networks, limits) -> bool:
    """Every network of `networks` lies inside one of `limits` (an empty `limits` holds anything)."""
    if not limits:
        return True
    if not networks:
        return False
    try:
        outer = [_network(e) for e in limits]
        return all(any(net.version == lim.version and net.subnet_of(lim) for lim in outer)
                   for net in (_network(e) for e in networks))
    except ValueError:
        return False


def log_refusal(key_id, addr) -> None:
    """Warn at most once per key and address every few minutes."""
    now = time.monotonic()
    mark = (key_id, addr)
    if now - _logged.get(mark, -_LOG_INTERVAL) < _LOG_INTERVAL:
        return
    if len(_logged) > 1024:
        _logged.clear()
    _logged[mark] = now
    logger.warning('API key %s refused from %s: address outside its allowed networks', key_id, addr or 'unknown')
