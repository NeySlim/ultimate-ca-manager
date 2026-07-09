"""
DNS TXT lookup helpers for ACME DNS-01 propagation checks.

Checks run in order:
1. ``acme.dns01_nameservers`` when configured in SystemConfig
2. authoritative nameservers for the zone (fast — record published at source)
3. public recursive resolvers (9.9.9.9, 8.8.8.8, 1.1.1.1) — global propagation
4. system resolver as last resort
"""
import ipaddress
import logging
from typing import Dict, List, Tuple

from utils.acme_debug import acme_log

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
    """Match a TXT rdata against the expected ACME token.

    Some public resolvers (notably Quad9) split long TXT character-strings
    across multiple ``rdata.strings`` chunks (RFC 1035 §3.3.14 allows a TXT RR
    to carry several <character-string> elements). The ACME authorization token
    is a single value regardless of how it was wire-split, so join the chunks
    before comparing — a correct record would otherwise render as
    ``value_mismatch`` / ``pending`` (issue #171).
    """
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


def check_public_resolvers(name: str, expected: str) -> Dict[str, bool]:
    """Query each public resolver individually for the expected TXT value.

    A resolver is ``OK`` only when it returns an answer containing the expected
    TXT value. Any failure (NXDOMAIN, SERVFAIL, timeout, wrong value) is logged
    at DEBUG with the exception type so operators can tell a flaky resolver
    apart from a genuine propagation gap (issue #171).
    """
    status: Dict[str, bool] = {}
    for resolver_ip in PUBLIC_DNS_RESOLVERS:
        try:
            answers = _resolve_with_ns(name, [resolver_ip])
            status[resolver_ip] = _answers_contain_expected(answers, expected)
        except Exception as exc:
            # Preserve the reason so it can be surfaced in logs; a bare bool
            # hides SERVFAIL/timeouts behind the same 'pending' label.
            acme_log(
                logger,
                'DNS public resolver %s returned no matching TXT for %s: %s: %s',
                resolver_ip, name, type(exc).__name__, exc,
            )
            status[resolver_ip] = False
    return status


def log_public_resolver_status(name: str, expected: str) -> Dict[str, bool]:
    """Log and return per-resolver public propagation status.

    This is a *diagnostic* log only: the DNS-01 self-check succeeds as soon as
    the authoritative (or configured) resolver sees the TXT record, regardless of
    whether the public recursors have caught up. The line is emitted even on
    success to aid debugging; a ``pending`` entry does NOT block issuance.
    """
    status = check_public_resolvers(name, expected)
    parts = [f'{ip}={"OK" if ok else "pending"}' for ip, ok in status.items()]
    logger.info(
        'DNS public propagation for %s (diagnostic, does not block issuance): %s',
        name, ', '.join(parts),
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
            acme_log(logger, 'TXT via configured NS failed for %s: %s', name, exc)

    auth_ips = _authoritative_nameserver_ips(name)
    if auth_ips:
        try:
            return _resolve_with_ns(name, auth_ips[:6]), 'authoritative'
        except Exception as exc:
            acme_log(logger, 'TXT via authoritative NS failed for %s: %s', name, exc)

    for resolver_ip in PUBLIC_DNS_RESOLVERS:
        try:
            answers = _resolve_with_ns(name, [resolver_ip])
            return answers, f'public:{resolver_ip}'
        except Exception as exc:
            acme_log(logger, 'TXT via %s failed for %s: %s', resolver_ip, name, exc)

    return dns.resolver.resolve(name, 'TXT', lifetime=10), 'recursive'


def txt_record_present(name: str, expected: str, *, log_public: bool = True) -> bool:
    """True when *name* serves a TXT RR whose value equals *expected*."""
    try:
        answers, source = resolve_txt_answers(name)
        if _answers_contain_expected(answers, expected):
            acme_log(logger, 'DNS TXT lookup for %s via %s', name, source)
            if source != 'recursive' and not source.startswith('public:'):
                logger.info('DNS TXT confirmed for %s via %s resolver', name, source)
            elif source.startswith('public:'):
                resolver_ip = source.split(':', 1)[1]
                logger.info('DNS TXT confirmed for %s via public resolver %s', name, resolver_ip)
            if log_public and not source.startswith('public:'):
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
