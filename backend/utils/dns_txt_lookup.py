"""
DNS TXT lookup helpers for ACME DNS-01 propagation checks.

Checks run in order:
1. ``acme.dns01_nameservers`` when configured in SystemConfig
2. authoritative nameservers for the zone (fast — record published at source)
3. public recursive resolvers (9.9.9.9, 8.8.8.8, 1.1.1.1) — global propagation
4. system resolver as last resort

A domain is considered ready when **any** path above returns the expected TXT.
Public resolver lines in logs are informational (#171); they do not require 3/3 OK.
"""
import ipaddress
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# Public resolvers polled explicitly (matches typical /etc/resolv.conf on UCM hosts).
PUBLIC_DNS_RESOLVERS: Tuple[str, ...] = ('9.9.9.9', '8.8.8.8', '1.1.1.1')


def _parse_resolver_ips(raw: str) -> List[str]:
    """Parse comma-separated resolver IPs; skip invalid entries with a warning."""
    ips: List[str] = []
    for part in str(raw).split(','):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            logger.warning(
                'Ignoring invalid acme.dns01_nameservers entry: %r', candidate
            )
            continue
        ips.append(candidate)
    return ips


def get_configured_dns01_nameservers() -> List[str]:
    """SystemConfig ``acme.dns01_nameservers``: comma-separated resolver IPs."""
    try:
        from models import SystemConfig

        setting = SystemConfig.query.filter_by(key='acme.dns01_nameservers').first()
        if not setting or not setting.value:
            return []
        return _parse_resolver_ips(setting.value)
    except Exception:
        return []


def _txt_rdata_matches(rdata, expected: str) -> bool:
    """Match a TXT rdata against the expected ACME token (single or split strings)."""
    try:
        chunks = [chunk.decode('utf-8', 'ignore') for chunk in rdata.strings]
        if ''.join(chunks) == expected:
            return True
        for chunk in chunks:
            if chunk == expected:
                return True
    except Exception:
        if str(rdata).strip('"') == expected:
            return True
    return False


def _answers_contain_expected(answers, expected: str) -> bool:
    for rdata in answers:
        if _txt_rdata_matches(rdata, expected):
            return True
    return False


def _resolver_failure_reason(exc: Exception) -> str:
    import dns.resolver

    exc_types = (
        ('nxdomain', 'NXDOMAIN'),
        ('no_answer', 'NoAnswer'),
        ('no_nameservers', 'NoNameservers'),
        ('timeout', 'Timeout'),
    )
    for label, attr in exc_types:
        exc_cls = getattr(dns.resolver, attr, None)
        if exc_cls is not None and isinstance(exc, exc_cls):
            return label

    msg = str(exc).lower()
    if 'nxdomain' in msg:
        return 'nxdomain'
    if 'timeout' in msg:
        return 'timeout'
    if 'no answer' in msg or 'noanswer' in msg:
        return 'no_answer'
    return type(exc).__name__.lower()


def _resolve_with_ns(name: str, nameservers: List[str], rtype: str = 'TXT'):
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = nameservers
    resolver.timeout = 5
    resolver.lifetime = 10
    return resolver.resolve(name, rtype)


def _authoritative_nameserver_ips(name: str) -> List[str]:
    """Return A/AAAA addresses for the authoritative NS of *name*'s zone."""
    import dns.resolver

    parts = name.rstrip('.').split('.')
    for i in range(len(parts) - 1):
        zone = '.'.join(parts[i:])
        try:
            ns_answers = dns.resolver.resolve(zone, 'NS', lifetime=10)
        except Exception:
            continue

        ips: List[str] = []
        for ns in ns_answers:
            host = str(ns).rstrip('.')
            for family in ('A', 'AAAA'):
                try:
                    addrs = dns.resolver.resolve(host, family, lifetime=5)
                    ips.extend(str(r) for r in addrs)
                except Exception:
                    pass
        if ips:
            return ips
    return []


def _check_one_public_resolver(name: str, expected: str, resolver_ip: str) -> Tuple[bool, str]:
    """Query one public resolver; return (ok, status_label)."""
    try:
        answers = _resolve_with_ns(name, [resolver_ip])
        if _answers_contain_expected(answers, expected):
            return True, 'OK'
        return False, 'value_mismatch'
    except Exception as exc:
        return False, _resolver_failure_reason(exc)


def check_public_resolvers(name: str, expected: str) -> Dict[str, bool]:
    """Query each public resolver individually for the expected TXT value."""
    status: Dict[str, bool] = {}
    for resolver_ip in PUBLIC_DNS_RESOLVERS:
        ok, _reason = _check_one_public_resolver(name, expected, resolver_ip)
        status[resolver_ip] = ok
    return status


def log_public_resolver_status(name: str, expected: str) -> Dict[str, bool]:
    """Log per-resolver public propagation status with failure reasons."""
    status: Dict[str, bool] = {}
    parts: List[str] = []
    for resolver_ip in PUBLIC_DNS_RESOLVERS:
        ok, reason = _check_one_public_resolver(name, expected, resolver_ip)
        status[resolver_ip] = ok
        if ok:
            parts.append(f'{resolver_ip}=OK')
        else:
            parts.append(f'{resolver_ip}=pending ({reason})')
    ok_count = sum(1 for ok in status.values() if ok)
    logger.info('DNS public propagation for %s: %s', name, ', '.join(parts))
    logger.info(
        'DNS public propagation summary for %s: %s/%s resolvers OK '
        '(informational only; UCM proceeds when authoritative or any resolver confirms)',
        name,
        ok_count,
        len(PUBLIC_DNS_RESOLVERS),
    )
    return status


def resolve_txt_answers(name: str) -> Tuple[object, str]:
    """
    Resolve TXT records with resolver fallbacks:
    1. ``acme.dns01_nameservers`` when configured
    2. authoritative nameservers for the containing zone
    3. each public resolver (9.9.9.9, 8.8.8.8, 1.1.1.1)
    4. system recursive resolver

    Returns (answers, source) where *source* identifies the winning resolver.
    """
    import dns.resolver

    custom = get_configured_dns01_nameservers()
    if custom:
        try:
            return _resolve_with_ns(name, custom), 'configured'
        except Exception as exc:
            logger.debug('TXT via configured NS failed for %s: %s', name, exc)

    auth_ips = _authoritative_nameserver_ips(name)
    if auth_ips:
        try:
            return _resolve_with_ns(name, auth_ips[:6]), 'authoritative'
        except Exception as exc:
            logger.debug('TXT via authoritative NS failed for %s: %s', name, exc)

    for resolver_ip in PUBLIC_DNS_RESOLVERS:
        try:
            answers = _resolve_with_ns(name, [resolver_ip])
            return answers, f'public:{resolver_ip}'
        except Exception as exc:
            logger.debug('TXT via %s failed for %s: %s', resolver_ip, name, exc)

    return dns.resolver.resolve(name, 'TXT', lifetime=10), 'recursive'


def txt_record_present(name: str, expected: str, *, log_public: bool = True) -> bool:
    """True when *name* serves a TXT RR whose value equals *expected*."""
    try:
        answers, source = resolve_txt_answers(name)
        if _answers_contain_expected(answers, expected):
            if source == 'configured':
                logger.info('DNS TXT confirmed for %s via configured resolver(s)', name)
            elif source == 'authoritative':
                logger.info('DNS TXT confirmed for %s via authoritative resolver', name)
            elif source and source.startswith('public:'):
                resolver_ip = source.split(':', 1)[1]
                logger.info('DNS TXT confirmed for %s via public resolver %s', name, resolver_ip)
            else:
                logger.info('DNS TXT confirmed for %s via system resolver', name)
            if log_public:
                log_public_resolver_status(name, expected)
            return True
    except Exception:
        pass

    if log_public:
        log_public_resolver_status(name, expected)
    return False


def public_propagation_ready(name: str, expected: str) -> bool:
    """True when at least one public resolver (9.9.9.9 / 8.8.8.8 / 1.1.1.1) sees the TXT."""
    return any(check_public_resolvers(name, expected).values())
