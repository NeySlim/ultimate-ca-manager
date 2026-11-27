"""Source networks an API key is limited to (#403).

Same parsing and matching as the admin allowlist (utils/admin_allowlist.py), on the address UCM
resolves for the request (request.remote_addr, after the trusted proxy hops). An empty list admits
any address; a list no entry of which parses admits none.
"""
import ipaddress
import logging
import re
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


# The first version whose nodes enforce the list: an older node in HA accepts the key from anywhere
ENFORCED_FROM = '3.1-dev'


def nodes_not_enforcing() -> list:
    """HA: the other nodes beating fresh on a version older than ENFORCED_FROM, as "node (version)"."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        return []
    from config.settings import Config
    from models.cluster import ClusterNode
    from services.scheduler_leader import STALE_PASSES, cluster_utc_now
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    from services.updates import parse_version
    now, stale = cluster_utc_now(), STALE_PASSES * WAKE_INTERVAL_SECONDS
    floor, behind = parse_version(ENFORCED_FROM), []
    # pid NULL: stopped cleanly; this node's own row may still hold the version it ran before
    for node in ClusterNode.query.filter(ClusterNode.pid.isnot(None), ClusterNode.node_id != Config.NODE_ID):
        if node.heartbeat_at is None or (now - node.heartbeat_at).total_seconds() > stale:
            continue
        # DEB/RPM spell 3.1-rc1 as 3.1~rc1 and may append a package revision ('-1')
        version = re.sub(r'-\d+$', '', (node.version or '').replace('~', '-').strip())
        if not version or parse_version(version) < floor:
            behind.append(f"{node.node_id} ({node.version or 'unknown version'})")
    return sorted(behind)


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
