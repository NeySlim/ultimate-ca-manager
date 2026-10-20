"""Source-address allowlist for the admin UI and the management API (#402).

The list comes from UCM_ADMIN_ALLOWED_NETWORKS when set (it then locks the
setting), otherwise from the `admin_allowed_networks` SystemConfig row. An
empty list restricts nothing. PKI protocol endpoints and health probes are
never filtered, and UCM_ADMIN_ALLOWLIST_DISABLE=1 turns the check off.
"""
from __future__ import annotations

import functools
import ipaddress
import logging
import os
import re
import threading
import time

logger = logging.getLogger(__name__)

CONFIG_KEY = 'admin_allowed_networks'
ENV_NETWORKS = 'UCM_ADMIN_ALLOWED_NETWORKS'
ENV_DISABLE = 'UCM_ADMIN_ALLOWLIST_DISABLE'
MAX_ENTRIES = 100
_MAX_ENTRY_LENGTH = 64
_TRUE_WORDS = ('1', 'true', 'yes', 'on')
_SPLIT_RE = re.compile(r'[\s,;]+')

# Probes (Docker, Kubernetes, forward-auth) reach these from outside the list.
_EXEMPT_EXACT = frozenset({
    '/api/v2/health', '/api/health', '/health',
    '/api/v2/health/live', '/api/v2/health/ready',
    '/api/health/live', '/api/health/ready',
    '/health/live', '/health/ready',
    '/metrics', '/api/v2/metrics',
    # SCEP clients that hard-code the legacy path
    '/cgi-bin/pkiclient.exe',
})
# Forward-auth subrequests: exempt only when the reverse proxy itself asks,
# otherwise a stolen session cookie could be kept alive from anywhere.
FORWARD_AUTH_PATHS = frozenset({'/api/auth/verify', '/api/v2/auth/verify'})

# The DB row is re-read at most this often, so a change written by another
# process takes effect within seconds; a change written here is immediate.
_CACHE_TTL_SECONDS = 5.0
_cache_lock = threading.Lock()
_cache = {'raw': None, 'at': 0.0}

_REFUSAL_LOG_INTERVAL = 300.0
_MAX_TRACKED_REFUSALS = 1024
_refusals: dict[str, float] = {}


def is_exempt_path(path: str, from_trusted_proxy: bool = False) -> bool:
    """True for paths a PKI client or a probe reaches: never filtered."""
    if path in _EXEMPT_EXACT:
        return True
    if path in FORWARD_AUTH_PATHS:
        return from_trusted_proxy
    from utils.public_endpoints import is_public_protocol_path
    return is_public_protocol_path(path)


def disabled_by_env() -> bool:
    return os.environ.get(ENV_DISABLE, '').strip().lower() in _TRUE_WORDS


def env_value() -> str | None:
    """The env list, or None when unset or blank (blank does not lock)."""
    raw = os.environ.get(ENV_NETWORKS)
    if raw is None or not raw.strip():
        return None
    return raw.strip()


def env_locked() -> bool:
    return env_value() is not None


def split_entries(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = _SPLIT_RE.split(value)
    elif isinstance(value, (list, tuple)):
        items = []
        for item in value:
            if not isinstance(item, str):
                raise ValueError('Each allowed network must be a string')
            items.extend(_SPLIT_RE.split(item))
    else:
        raise ValueError('Allowed networks must be a list of IP addresses or CIDR networks')
    return [item.strip() for item in items if item.strip()]


def _canonical(entry: str) -> str:
    if len(entry) > _MAX_ENTRY_LENGTH or '%' in entry:
        raise ValueError(f'Invalid IP address or CIDR network: {entry[:_MAX_ENTRY_LENGTH]}')
    try:
        if '/' in entry:
            return str(ipaddress.ip_network(entry, strict=False))
        return str(ipaddress.ip_address(entry))
    except ValueError:
        raise ValueError(f'Invalid IP address or CIDR network: {entry}') from None


def parse_entries(value) -> list[str]:
    """Validate and canonicalize a list (or a comma/newline separated string).

    Raises ValueError naming the first invalid entry.
    """
    seen = []
    for entry in split_entries(value):
        canonical = _canonical(entry)
        if canonical not in seen:
            seen.append(canonical)
    if len(seen) > MAX_ENTRIES:
        raise ValueError(f'At most {MAX_ENTRIES} allowed networks can be configured')
    return seen


@functools.lru_cache(maxsize=16)
def _compile(raw: str) -> tuple:
    """Networks of a stored or env list; invalid entries are dropped with a warning."""
    networks = []
    for entry in split_entries(raw):
        try:
            net = ipaddress.ip_network(entry, strict=False)
        except ValueError:
            logger.warning('Ignoring admin allowlist entry %r: not an IP address or CIDR network', entry)
            continue
        networks.append(net)
        mapped = getattr(net.network_address, 'ipv4_mapped', None)
        if mapped is not None and net.prefixlen >= 96:
            networks.append(ipaddress.ip_network(f'{mapped}/{net.prefixlen - 96}', strict=False))
    return tuple(networks)


def address_in(addr: str, networks) -> bool:
    if not addr:
        return False
    try:
        ip = ipaddress.ip_address(addr.strip())
    except ValueError:
        return False
    mapped = getattr(ip, 'ipv4_mapped', None)
    candidates = (ip, mapped) if mapped is not None else (ip,)
    return any(cand in net for cand in candidates for net in networks)


def address_allowed_by(addr: str, entries: list[str]) -> bool:
    """Whether *addr* is covered by already canonical *entries*."""
    return address_in(addr, _compile(','.join(entries)))


def invalidate_cache() -> None:
    with _cache_lock:
        _cache['raw'] = None
        _cache['at'] = 0.0


def stored_value() -> str:
    """The DB row, read through a short cache; '' when absent or unreadable."""
    now = time.monotonic()
    with _cache_lock:
        if _cache['raw'] is not None and now - _cache['at'] < _CACHE_TTL_SECONDS:
            return _cache['raw']
        previous = _cache['raw']
    try:
        from models import SystemConfig
        row = SystemConfig.query.filter_by(key=CONFIG_KEY).first()
        raw = (row.value or '').strip() if row else ''
    except Exception as exc:
        logger.debug('admin allowlist could not read the setting: %s', exc)
        raw = previous if previous is not None else ''
    with _cache_lock:
        _cache['raw'] = raw
        _cache['at'] = now
    return raw


def effective_raw() -> str:
    env = env_value()
    return env if env is not None else stored_value()


def configured_entries() -> list[str]:
    """The list in force, as written (env) or as stored (DB)."""
    return split_entries(effective_raw())


def is_allowed(addr: str) -> bool:
    """True when *addr* may reach the admin UI and the management API."""
    if disabled_by_env():
        return True
    raw = effective_raw()
    if not raw:
        return True
    # A non-empty list whose entries are all invalid admits nobody.
    return address_in(addr, _compile(raw))


def guard_restored_value(raw) -> str:
    """The list a restore may write: '' when it would not admit the restoring
    request, or when there is no request to check (CLI restore)."""
    raw = (raw or '').strip() if isinstance(raw, str) else ''
    if not raw:
        return ''
    from flask import has_request_context, request
    if has_request_context() and address_in(request.remote_addr or '', _compile(raw)):
        return raw
    return ''


def log_refusal(addr: str, path: str) -> None:
    """Warn about a refused peer at most once per address every few minutes."""
    now = time.monotonic()
    last = _refusals.get(addr)
    if last is not None and now - last < _REFUSAL_LOG_INTERVAL:
        return
    if last is None and len(_refusals) >= _MAX_TRACKED_REFUSALS:
        _refusals.clear()
    _refusals[addr] = now
    logger.warning('Admin access refused for %s on %s: address not in the admin allowlist',
                   addr or 'unknown', path)


REFUSAL_MESSAGE = 'Access to the administration interface is not allowed from this address'


class SocketIOAllowlistGate:
    """WSGI gate for /socket.io/, which Flask-SocketIO serves before any Flask hook.

    The client address is resolved the way the main chain resolves it
    (ForwardedHeadersGate then ProxyFix), on a copy of the environ.
    """

    def __init__(self, app, flask_app, trusted_hops: int = 0):
        self.app = app
        self.flask_app = flask_app
        self._resolver = None
        if trusted_hops > 0:
            from werkzeug.middleware.proxy_fix import ProxyFix
            from utils.trusted_proxy import ForwardedHeadersGate
            self._resolver = ForwardedHeadersGate(
                ProxyFix(lambda environ, start_response: [], x_for=trusted_hops))

    def _client_addr(self, environ) -> str:
        if self._resolver is None:
            return environ.get('REMOTE_ADDR') or ''
        copy = dict(environ)
        self._resolver(copy, lambda *args, **kwargs: None)
        return copy.get('REMOTE_ADDR') or ''

    def __call__(self, environ, start_response):
        path = environ.get('PATH_INFO', '')
        if path.startswith('/socket.io/') and not disabled_by_env():
            addr = self._client_addr(environ)
            with self.flask_app.app_context():
                allowed = is_allowed(addr)
            if not allowed:
                log_refusal(addr, path)
                body = REFUSAL_MESSAGE.encode()
                start_response('403 Forbidden', [
                    ('Content-Type', 'text/plain; charset=utf-8'),
                    ('Content-Length', str(len(body))),
                ])
                return [body]
        return self.app(environ, start_response)
