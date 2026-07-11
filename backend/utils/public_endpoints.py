"""Public endpoint URLs: admin GUI, PKI protocol HTTP, and ACME vhost.

Single source of truth for canonical admin host, CORS origins, redirect
targets, and Host-role enforcement (admin vs ACME split topology).
"""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import socket
import ssl
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlsplit, urlunsplit

from flask import current_app, request as flask_request

from models import SystemConfig
from utils.acme_public_url import is_valid_public_vhost

logger = logging.getLogger(__name__)

_IP_RE = re.compile(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$')
_DEFAULT_LOCALHOSTS = frozenset({
    'localhost', '127.0.0.1', '::1', 'localhost.localdomain',
    'ucm.example.com', 'ucm.local', 'test.local',
})

# Paths that skip canonical-admin redirect and strict host-role checks.
_HEALTH_PATHS = frozenset({
    '/api/v2/health', '/api/health', '/health',
    '/metrics', '/api/v2/metrics',
    '/api/auth/verify', '/api/v2/auth/verify',
})
_PROTOCOL_PREFIXES = (
    '/cdp/', '/ca/', '/ocsp', '/scep/', '/.well-known/', '/tsa', '/ssh/setup/',
)
_ACME_PREFIXES = ('/acme/',)
_STATIC_PREFIXES = ('/static/', '/assets/')

# Hostnames that must never appear in operator-configured public URLs.
_BLOCKED_METADATA_HOSTS = frozenset({
    'metadata',
    'metadata.google.internal',
    'metadata.goog',
})


@dataclass(frozen=True)
class ParsedPublicUrl:
    scheme: str
    host: str
    port: int
    normalized: str


def _config_value(key: str, default: str = '') -> str:
    try:
        row = SystemConfig.query.filter_by(key=key).first()
        return (row.value or '').strip() if row else default
    except Exception:
        return default


def _https_port() -> int:
    """Deployment HTTPS listen port (ucm.env HTTPS_PORT, default 8443)."""
    env = os.getenv('HTTPS_PORT')
    if env is not None:
        try:
            return int(env)
        except (TypeError, ValueError):
            pass
    try:
        return int(current_app.config.get('HTTPS_PORT', 8443))
    except Exception:
        return 8443


def _explicit_port_in_raw(raw: str) -> bool:
    """True when the stored URL string includes an explicit :port."""
    text = (raw or '').strip()
    if not text:
        return False
    if '://' not in text:
        netloc = text.split('/')[0]
    else:
        netloc = urlsplit(text).netloc
    return ':' in netloc


def _format_public_origin(scheme: str, host: str, port: int) -> str:
    """Build scheme://host[:port] omitting default 443/80."""
    if (scheme == 'https' and port == 443) or (scheme == 'http' and port == 80):
        host_part = host
    else:
        host_part = f'{host}:{port}'
    return urlunsplit((scheme, host_part, '', '', ''))


def _effective_port_for_stored_url(stored_raw: str, scheme: str, deployment_port: int) -> int:
    """Port for runtime URLs: explicit in DB string, else deployment listen port."""
    if _explicit_port_in_raw(stored_raw):
        parsed = parse_public_url(stored_raw, default_scheme=scheme)
        return parsed.port if parsed else deployment_port
    return deployment_port


def _env_fqdn() -> Optional[str]:
    fqdn = os.getenv('UCM_FQDN') or os.getenv('FQDN')
    if fqdn and fqdn.lower() not in _DEFAULT_LOCALHOSTS:
        return fqdn.lower()
    try:
        from config.settings import get_system_fqdn
        fqdn = get_system_fqdn()
        if fqdn and fqdn.lower() not in _DEFAULT_LOCALHOSTS:
            return fqdn.lower()
    except Exception:
        pass
    try:
        fqdn = current_app.config.get('FQDN')
        if fqdn and fqdn.lower() not in _DEFAULT_LOCALHOSTS:
            return fqdn.lower()
    except Exception:
        pass
    return None


def parse_public_url(raw: str, *, default_scheme: str = 'https') -> Optional[ParsedPublicUrl]:
    """Parse and normalize a public base URL (scheme + host + optional port)."""
    text = (raw or '').strip()
    if not text:
        return None
    if '://' not in text:
        text = f'{default_scheme}://{text}'
    parts = urlsplit(text)
    if parts.username or parts.password:
        return None
    if parts.path not in ('', '/'):
        return None
    if parts.query or parts.fragment:
        return None
    host = (parts.hostname or '').lower()
    if not host or not is_valid_public_vhost(host):
        return None
    scheme = (parts.scheme or default_scheme).lower()
    if scheme not in ('http', 'https'):
        return None
    port = parts.port
    if port is None:
        port = 443 if scheme == 'https' else 80
    if port < 1 or port > 65535:
        return None
    host_part = host if (
        (scheme == 'https' and port == 443) or (scheme == 'http' and port == 80)
    ) else f'{host}:{port}'
    normalized = urlunsplit((scheme, host_part, '', '', ''))
    return ParsedPublicUrl(scheme=scheme, host=host, port=port, normalized=normalized)


def validate_public_host_ssrf(hostname: str) -> Optional[str]:
    """Return an error message when *hostname* must not be used for public URLs.

    Blocks cloud-metadata hostnames only. Loopback/private resolution is allowed
    on save — operators often use /etc/hosts or split-hostname lab setups.
    Preflight reports loopback as a warning, not a hard failure.
    """
    host = (hostname or '').lower().rstrip('.')
    if not host:
        return None
    if host in _BLOCKED_METADATA_HOSTS:
        return f'Host {host} is not allowed (cloud metadata endpoint)'
    return None


def _resolve_host_ips(hostname: str) -> tuple[list[str], Optional[str]]:
    """Resolve *hostname* via the system resolver (/etc/hosts + resolv.conf)."""
    try:
        addrs = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        return [], str(exc)
    ips: list[str] = []
    for _fam, _typ, _proto, _canon, sockaddr in addrs:
        ip = sockaddr[0]
        if ip not in ips:
            ips.append(ip)
    return ips, None


def _get_internal_dns_nameservers() -> list[str]:
    """Corporate/internal resolvers for preflight (split-horizon DNS).

    Order: ``UCM_CORPORATE_DNS_SERVERS`` env, then ``acme.dns01_nameservers`` in DB.
    """
    import os

    from utils.dns_txt_lookup import _parse_resolver_ips, get_configured_dns01_nameservers

    env_raw = os.getenv('UCM_CORPORATE_DNS_SERVERS', '').strip()
    if env_raw:
        ips = _parse_resolver_ips(env_raw)
        if ips:
            return ips
    try:
        return get_configured_dns01_nameservers()
    except Exception:
        return []


def _resolve_host_ips_via_nameservers(
    hostname: str,
    nameservers: list[str],
    *,
    nxdomain_detail: str,
    empty_detail: str,
) -> tuple[list[str], Optional[str]]:
    """Resolve *hostname* via explicit recursive nameservers (dnspython)."""
    if not nameservers:
        return [], empty_detail
    try:
        import dns.exception
        import dns.resolver
    except ImportError:
        return [], 'dnspython not available'

    host = (hostname or '').lower().rstrip('.')
    if not host:
        return [], 'empty hostname'

    last_error: Optional[str] = None
    for nameserver in nameservers:
        try:
            resolver = dns.resolver.Resolver(configure=False)
            resolver.nameservers = [nameserver]
            resolver.timeout = 3.0
            resolver.lifetime = 8.0
            ips: list[str] = []
            nxdomain_on_a = False
            for rtype in ('A', 'AAAA'):
                try:
                    answers = resolver.resolve(host, rtype)
                    for rdata in answers:
                        ip = str(rdata)
                        if ip not in ips:
                            ips.append(ip)
                except dns.resolver.NoAnswer:
                    pass
                except dns.resolver.NXDOMAIN:
                    if rtype == 'A':
                        nxdomain_on_a = True
                        break
            if ips:
                return ips, None
            if nxdomain_on_a:
                return [], nxdomain_detail
        except dns.exception.DNSException as exc:
            last_error = str(exc)
            continue
    return [], last_error or empty_detail


def _resolve_host_ips_internal(hostname: str) -> tuple[list[str], Optional[str]]:
    """Resolve via corporate DNS (e.g. 10.0.0.53). Skipped when not configured."""
    nameservers = _get_internal_dns_nameservers()
    if not nameservers:
        return [], None
    return _resolve_host_ips_via_nameservers(
        hostname,
        nameservers,
        nxdomain_detail='NXDOMAIN (internal DNS)',
        empty_detail='no internal DNS records',
    )


def _resolve_host_ips_public(hostname: str) -> tuple[list[str], Optional[str]]:
    """Resolve *hostname* via public recursive DNS (Internet / remote-client perspective)."""
    from utils.dns_txt_lookup import PUBLIC_DNS_RESOLVERS

    return _resolve_host_ips_via_nameservers(
        hostname,
        list(PUBLIC_DNS_RESOLVERS),
        nxdomain_detail='NXDOMAIN (public DNS)',
        empty_detail='no public DNS records',
    )


def _preflight_dns_is_usable(status: Optional[str]) -> bool:
    return status in ('ok', 'warn')


def _select_preflight_connect_ip(ips: list[str]) -> Optional[str]:
    """First resolved IP safe for outbound preflight probes (blocks metadata/loopback)."""
    from utils.ssrf_protection import _forbidden_ip_reason

    for ip_str in ips:
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if _forbidden_ip_reason(ip):
            continue
        return ip_str
    return None


def _first_usable_preflight_ips(
    hostname: str,
    local_ips: list[str],
    local_err: Optional[str],
    internal_ips: list[str],
    internal_err: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    """Return (connect_ip, error) for TLS/HTTP probes."""
    for candidates in (local_ips, internal_ips):
        connect_ip = _select_preflight_connect_ip(candidates)
        if connect_ip:
            return connect_ip, None
    if local_err:
        return None, local_err
    if internal_err:
        return None, internal_err
    if local_ips or internal_ips:
        return None, 'resolved address blocked for preflight probe'
    return None, 'no resolvable address'


def _classify_preflight_dns(hostname: str, ips: list[str], error: Optional[str]) -> tuple[str, str]:
    """Classify DNS preflight: ok | warn | fail."""
    if error:
        return 'fail', error
    if not ips:
        return 'fail', 'no addresses returned'
    if hostname.lower().rstrip('.') in _BLOCKED_METADATA_HOSTS:
        return 'fail', 'cloud metadata hostname is not allowed'

    try:
        from utils.ssrf_protection import _forbidden_ip_reason
        loopback_ips: list[str] = []
        private_ips: list[str] = []
        public_ips: list[str] = []
        for ip_str in ips:
            ip = ipaddress.ip_address(ip_str)
            if ip.is_loopback:
                loopback_ips.append(ip_str)
                continue
            reason = _forbidden_ip_reason(ip)
            if reason:
                return 'fail', f'resolves to {reason} {ip_str}'
            if ip.is_private:
                private_ips.append(ip_str)
            else:
                public_ips.append(ip_str)
        if loopback_ips and not private_ips and not public_ips:
            return 'warn', f"loopback ({', '.join(loopback_ips[:3])}) — /etc/hosts on this host"
        if private_ips and not public_ips:
            return 'warn', f"private ({', '.join(private_ips[:3])})"
        if loopback_ips or private_ips:
            return 'warn', f"mixed ({', '.join(ips[:3])})"
        return 'ok', f"→ {', '.join(ips[:3])}"
    except ValueError as exc:
        return 'fail', str(exc)


def validate_admin_base_url(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Return (normalized_url, error_message). Admin URL must be HTTPS."""
    parsed = parse_public_url(raw, default_scheme='https')
    if not parsed:
        return None, 'base_url must be a valid HTTPS URL (scheme, FQDN, optional port; no path)'
    if parsed.scheme != 'https':
        return None, 'base_url must use https://'
    ssrf_err = validate_public_host_ssrf(parsed.host)
    if ssrf_err:
        return None, ssrf_err
    return parsed.normalized, None


def validate_protocol_base_url(raw: str) -> tuple[Optional[str], Optional[str]]:
    """Return (normalized_url, error_message). Protocol URL must be HTTP."""
    text = (raw or '').strip()
    if not text:
        return '', None
    parsed = parse_public_url(text, default_scheme='http')
    if not parsed:
        return None, 'protocol_base_url must be a valid HTTP URL (scheme, FQDN, optional port; no path)'
    if parsed.scheme != 'http':
        return None, 'protocol_base_url must use http:// (avoids TLS verification loops on CRL/OCSP)'
    ssrf_err = validate_public_host_ssrf(parsed.host)
    if ssrf_err:
        return None, ssrf_err
    return parsed.normalized, None


def validate_acme_public_vhost_host(host: str) -> Optional[str]:
    """SSRF/metadata guard for acme_public_vhost (host only, no scheme)."""
    return validate_public_host_ssrf((host or '').strip().lower())


def get_admin_base_url() -> Optional[str]:
    """Configured admin base URL from SystemConfig, normalized."""
    raw = _config_value('base_url')
    if not raw:
        return None
    parsed = parse_public_url(raw, default_scheme='https')
    return parsed.normalized if parsed else None


def get_admin_public_host() -> Optional[str]:
    """Admin hostname for redirects and Host enforcement."""
    parsed = parse_public_url(_config_value('base_url'), default_scheme='https')
    if parsed:
        return parsed.host
    return _env_fqdn()


def get_acme_public_port() -> int:
    raw = _config_value('acme_public_port', '')
    if not raw:
        return _https_port()
    try:
        port = int(raw)
        return port if 1 <= port <= 65535 else _https_port()
    except (TypeError, ValueError):
        return _https_port()


def get_admin_canonical_origin() -> Optional[str]:
    """Effective https://admin.example.com[:port] for redirects and GUI."""
    raw = _config_value('base_url')
    if raw:
        parsed = parse_public_url(raw, default_scheme='https')
        if parsed:
            port = _effective_port_for_stored_url(raw, 'https', _https_port())
            return _format_public_origin('https', parsed.host, port)
    host = _env_fqdn()
    if not host:
        return None
    return _format_public_origin('https', host, _https_port())


def get_protocol_effective_url() -> Optional[str]:
    """Effective HTTP base URL for CDP/OCSP (honours HTTP_PROTOCOL_PORT / http_protocol_port)."""
    from protocol_http_server import get_http_protocol_port

    raw = _config_value('protocol_base_url')
    http_port = get_http_protocol_port()
    if raw:
        parsed = parse_public_url(raw, default_scheme='http')
        if parsed:
            port = _effective_port_for_stored_url(raw, 'http', http_port)
            return _format_public_origin('http', parsed.host, port)
    admin_host = get_admin_public_host()
    if http_port > 0 and admin_host:
        return _format_public_origin('http', admin_host, http_port)
    return None


def get_acme_public_host_configured() -> Optional[str]:
    host = _config_value('acme_public_vhost').lower()
    return host if host and is_valid_public_vhost(host) else None


def is_split_acme_topology() -> bool:
    """True when a dedicated ACME vhost is configured and differs from admin."""
    acme = get_acme_public_host_configured()
    admin = get_admin_public_host()
    return bool(acme and admin and acme != admin)


def get_protocol_host() -> Optional[str]:
    raw = _config_value('protocol_base_url')
    if raw:
        parsed = parse_public_url(raw, default_scheme='http')
        if parsed:
            return parsed.host
    admin = get_admin_public_host()
    return admin


def _host_from_request() -> str:
    try:
        return flask_request.host.split(':')[0].lower()
    except Exception:
        return ''


def _normalize_host(host: str) -> str:
    return (host or '').split(':')[0].lower()


def is_protocol_path(path: str) -> bool:
    return any(path.startswith(p) for p in _PROTOCOL_PREFIXES)


def is_acme_path(path: str) -> bool:
    return any(path.startswith(p) for p in _ACME_PREFIXES)


def is_admin_ui_path(path: str) -> bool:
    """SPA, authenticated API, static assets — not protocol/ACME-only paths."""
    if path in _HEALTH_PATHS or path.startswith(_STATIC_PREFIXES):
        return False
    if is_protocol_path(path) or is_acme_path(path):
        return False
    if path.startswith('/socket.io/'):
        return True
    if path.startswith('/api/'):
        return True
    # Frontend routes (/, /settings, etc.)
    return not path.startswith('/api/')


def skip_public_host_middleware(path: str) -> bool:
    if path in _HEALTH_PATHS:
        return True
    if path.startswith(_STATIC_PREFIXES):
        return True
    return False


def host_is_ip(host: str) -> bool:
    if _IP_RE.match(host or ''):
        return True
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def get_cors_origins() -> list[str]:
    """Dynamic CORS allowlist: localhost + canonical admin origin."""
    https_port = _https_port()
    suffix = '' if https_port == 443 else f':{https_port}'
    origins = [
        f'https://localhost{suffix}',
        f'https://127.0.0.1{suffix}',
    ]
    admin_origin = get_admin_canonical_origin()
    if admin_origin:
        origins.append(admin_origin.rstrip('/'))
    extra = os.getenv('CORS_EXTRA_ORIGINS', '')
    if extra:
        for item in extra.split(','):
            item = item.strip().rstrip('/')
            if item and item not in origins:
                origins.append(item)
    return origins


def env_locked_fields() -> dict[str, bool]:
    """Fields forced by environment (read-only hints for the GUI)."""
    return {
        'fqdn_env': bool(os.getenv('UCM_FQDN') or os.getenv('FQDN')),
        'https_port_env': os.getenv('HTTPS_PORT') is not None,
        'http_protocol_port_env': os.getenv('HTTP_PROTOCOL_PORT') is not None,
        'cors_extra_origins': bool(os.getenv('CORS_EXTRA_ORIGINS', '').strip()),
    }


def build_effective_endpoints(flask_request=None) -> dict:
    """Snapshot for GET /api/v2/settings/public-endpoints."""
    admin_raw = _config_value('base_url')
    admin_host = get_admin_public_host()
    admin_canonical = get_admin_canonical_origin() or ''
    protocol_raw = _config_value('protocol_base_url')

    from protocol_http_server import get_http_protocol_port
    http_port = get_http_protocol_port()
    https_port = _https_port()

    acme_host = get_acme_public_host_configured()
    acme_port = get_acme_public_port()
    if acme_host:
        acme_origin = _format_public_origin('https', acme_host, acme_port)
    elif flask_request is not None:
        from utils.acme_public_url import get_acme_public_origin
        acme_origin = get_acme_public_origin(flask_request).rstrip('/')
    else:
        acme_origin = admin_canonical.rstrip('/') if admin_canonical else None

    protocol_effective = get_protocol_effective_url() or ''

    req_host = _normalize_host(_host_from_request()) if flask_request else None

    return {
        'admin': {
            'base_url': admin_raw or '',
            'host': admin_host or '',
            'canonical_origin': admin_canonical,
            'https_port': https_port,
        },
        'protocol': {
            'base_url': protocol_raw,
            'effective_url': protocol_effective,
            'http_protocol_port': http_port,
        },
        'acme': {
            'vhost': acme_host or '',
            'port': acme_port,
            'origin': acme_origin or '',
            'directory_url': f'{acme_origin}/acme' if acme_origin else '',
            'proxy_url': f'{acme_origin}/acme/proxy' if acme_origin else '',
            'split_topology': is_split_acme_topology(),
        },
        'cors_origins': get_cors_origins(),
        'env_locked': env_locked_fields(),
        'request_host': req_host or '',
        'host_role_ok': _request_host_role_ok(req_host) if req_host else None,
    }


def _request_host_role_ok(current_host: str) -> bool:
    if not current_host:
        return True
    admin = get_admin_public_host()
    acme = get_acme_public_host_configured()
    if is_split_acme_topology():
        return current_host in (admin, acme)
    if admin:
        return current_host == admin or not host_is_ip(current_host)
    return True


def build_canonical_redirect_url(path_query: str) -> Optional[str]:
    """Redirect target for non-canonical admin hosts (IP or alias FQDN)."""
    origin = get_admin_canonical_origin()
    if not origin:
        return None
    return f'{origin}{path_query}'


def check_host_access(path: str, host: str) -> Optional[tuple[int, str]]:
    """Return (status_code, message) when access must be denied, else None."""
    host = _normalize_host(host)
    if skip_public_host_middleware(path):
        return None
    if is_protocol_path(path):
        return None

    acme_host = get_acme_public_host_configured()
    admin_host = get_admin_public_host()

    if is_split_acme_topology() and host == acme_host:
        if is_acme_path(path):
            return None
        if is_admin_ui_path(path):
            return 404, 'Admin interface is not available on the ACME public vhost'

    if admin_host and is_admin_ui_path(path) and host != admin_host:
        if host_is_ip(host) or (acme_host and host != acme_host):
            return None  # redirect middleware handles redirect
        if host != admin_host:
            return None  # redirect alias FQDN → canonical admin

    return None


def run_preflight_checks() -> dict:
    """DNS/TLS diagnostics for configured public hosts (admin + ACME)."""
    results = []

    def _check_dns(label: str, hostname: str):
        entry = {
            'label': label,
            'host': hostname,
            'dns': 'skip',
            'dns_local': 'skip',
            'dns_internal': 'skip',
            'dns_public': 'skip',
            'tls': 'skip',
            'detail': '',
            '_local_ips': [],
            '_internal_ips': [],
        }
        if not hostname:
            entry['detail'] = 'not configured'
            results.append(entry)
            return
        meta_err = validate_public_host_ssrf(hostname)
        if meta_err:
            entry['dns'] = 'fail'
            entry['dns_local'] = 'fail'
            entry['dns_internal'] = 'fail'
            entry['dns_public'] = 'fail'
            entry['detail'] = meta_err
            results.append(entry)
            return

        local_ips, local_err = _resolve_host_ips(hostname)
        entry['_local_ips'] = local_ips
        local_status, local_detail = _classify_preflight_dns(hostname, local_ips, local_err)
        entry['dns_local'] = local_status

        internal_ips, internal_err = _resolve_host_ips_internal(hostname)
        entry['_internal_ips'] = internal_ips
        if _get_internal_dns_nameservers():
            internal_status, internal_detail = _classify_preflight_dns(
                hostname, internal_ips, internal_err
            )
            entry['dns_internal'] = internal_status
        else:
            internal_status, internal_detail = 'skip', ''

        pub_ips, pub_err = _resolve_host_ips_public(hostname)
        pub_status, pub_detail = _classify_preflight_dns(hostname, pub_ips, pub_err)
        entry['dns_public'] = pub_status

        for status in (pub_status, internal_status, local_status):
            if _preflight_dns_is_usable(status):
                entry['dns'] = status
                break
        else:
            entry['dns'] = pub_status if pub_status != 'skip' else (
                internal_status if internal_status != 'skip' else local_status
            )

        detail_parts: list[str] = []
        if local_status != 'skip':
            detail_parts.append(f"local: {local_detail}")
        if internal_status != 'skip':
            detail_parts.append(f"internal: {internal_detail}")
        if pub_status != 'skip':
            detail_parts.append(f"public: {pub_detail}")
        entry['detail'] = ' | '.join(detail_parts)
        results.append(entry)

    def _check_tls(label: str, hostname: str, port: int):
        for entry in results:
            if entry['label'] == label and entry['host'] == hostname:
                connect_ip, connect_err = _first_usable_preflight_ips(
                    hostname,
                    entry.get('_local_ips') or [],
                    None,
                    entry.get('_internal_ips') or [],
                    None,
                )
                if not connect_ip:
                    entry['tls'] = 'skip'
                    if connect_err and not entry.get('detail'):
                        entry['detail'] = connect_err
                    return
                break
        else:
            return
        try:
            ctx = ssl.create_default_context()
            connect_ip, _ = _first_usable_preflight_ips(
                hostname,
                entry.get('_local_ips') or [],
                None,
                entry.get('_internal_ips') or [],
                None,
            )
            target = connect_ip or hostname
            with socket.create_connection((target, port), timeout=10) as sock:
                with ctx.wrap_socket(sock, server_hostname=hostname) as ssock:
                    cert = ssock.getpeercert()
                    sans = [v for t, v in cert.get('subjectAltName', ()) if t == 'DNS']
                    entry = next(e for e in results if e['label'] == label)
                    entry['tls'] = 'ok'
                    san_detail = f"TLS {port}: SAN: {', '.join(sans[:5])}" if sans else f'TLS {port}: no SAN'
                    if entry.get('detail'):
                        entry['detail'] = f"{entry['detail']} | {san_detail}"
                    else:
                        entry['detail'] = san_detail
        except OSError as exc:
            entry = next(e for e in results if e['label'] == label)
            entry['tls'] = 'fail'
            tls_detail = f'TLS :{port} — {exc}'
            if entry.get('detail'):
                entry['detail'] = f"{entry['detail']} | {tls_detail}"
            else:
                entry['detail'] = tls_detail

    def _check_http(label: str, hostname: str, port: int):
        for entry in results:
            if entry['label'] == label and entry['host'] == hostname:
                connect_ip, _ = _first_usable_preflight_ips(
                    hostname,
                    entry.get('_local_ips') or [],
                    None,
                    entry.get('_internal_ips') or [],
                    None,
                )
                if not connect_ip:
                    return
                break
        else:
            return
        try:
            connect_ip, _ = _first_usable_preflight_ips(
                hostname,
                entry.get('_local_ips') or [],
                None,
                entry.get('_internal_ips') or [],
                None,
            )
            target = connect_ip or hostname
            with socket.create_connection((target, port), timeout=5):
                pass
            entry = next(e for e in results if e['label'] == label)
            entry['tls'] = 'ok'
            http_detail = f'HTTP :{port} reachable'
            if entry.get('detail'):
                entry['detail'] = f"{entry['detail']} | {http_detail}"
            else:
                entry['detail'] = http_detail
        except OSError as exc:
            entry = next(e for e in results if e['label'] == label)
            entry['tls'] = 'fail'
            entry['detail'] = f'HTTP :{port} — {exc}'

    admin_raw = _config_value('base_url')
    admin_parsed = parse_public_url(admin_raw, default_scheme='https')
    if admin_parsed:
        admin_port = _effective_port_for_stored_url(admin_raw, 'https', _https_port())
        _check_dns('admin', admin_parsed.host)
        _check_tls('admin', admin_parsed.host, admin_port)

    acme = get_acme_public_host_configured()
    if acme:
        port = get_acme_public_port()
        _check_dns('acme', acme)
        _check_tls('acme', acme, port)

    proto_raw = _config_value('protocol_base_url')
    if proto_raw:
        pp = parse_public_url(proto_raw, default_scheme='http')
        if pp:
            from protocol_http_server import get_http_protocol_port
            proto_port = _effective_port_for_stored_url(proto_raw, 'http', get_http_protocol_port())
            _check_dns('protocol', pp.host)
            if proto_port > 0:
                _check_http('protocol', pp.host, proto_port)

    for entry in results:
        entry.pop('_local_ips', None)
        entry.pop('_internal_ips', None)

    return {
        'checks': results,
        'split_topology': is_split_acme_topology(),
        'canonical_admin': get_admin_canonical_origin() or '',
        'internal_dns_configured': bool(_get_internal_dns_nameservers()),
        'corporate_dns_servers': _get_internal_dns_nameservers(),
    }
