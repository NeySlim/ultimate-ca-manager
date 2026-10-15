"""
DNS TXT lookup helpers for ACME DNS-01 propagation checks.

``acme.dns01_resolver_mode`` picks the resolvers:
- ``auto``: ``acme.dns01_nameservers`` if set, then the authoritative
  nameservers (following the CNAMEs they return): every one that answers must
  serve the value, and one still lacking it ends the check. Only when none answers:
  9.9.9.9 / 8.8.8.8 / 1.1.1.1, then the system resolver;
- ``system``: the system resolver only;
- ``custom``: ``acme.dns01_nameservers`` only.
Outside ``auto`` nothing else is queried, for networks that block outbound DNS.
"""
import ipaddress
import logging
from typing import Dict, List, Optional, Tuple

from utils.acme_debug import acme_log

logger = logging.getLogger(__name__)

# Public resolvers polled explicitly (matches typical /etc/resolv.conf on UCM hosts).
PUBLIC_DNS_RESOLVERS: Tuple[str, ...] = ('9.9.9.9', '8.8.8.8', '1.1.1.1')
RESOLVER_MODES: Tuple[str, ...] = ('auto', 'system', 'custom')


def _parse_entry(entry: str) -> Tuple[str, int]:
    """``ip``, ``ipv4:port`` or ``[ipv6]:port`` → (ip, port). Raises ValueError."""
    host, port = entry, '53'
    if entry.startswith('['):
        host, sep, rest = entry[1:].partition(']')
        if not sep or (rest and not rest.startswith(':')):
            raise ValueError(entry)
        port = rest[1:] or '53'
    elif entry.count(':') == 1:
        host, _, port = entry.partition(':')
    ipaddress.ip_address(host)
    if not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError(entry)
    return host, int(port)


def parse_resolver_entries(raw: str, *, strict: bool = False) -> List[Tuple[str, int]]:
    """Comma-separated resolvers → [(ip, port)]. Invalid entries are skipped
    with a warning, or raise ValueError when *strict*."""
    entries: List[Tuple[str, int]] = []
    for part in str(raw or '').split(','):
        candidate = part.strip()
        if not candidate:
            continue
        try:
            entries.append(_parse_entry(candidate))
        except ValueError:
            if strict:
                raise ValueError(f'Invalid DNS resolver: {candidate}')
            logger.warning('Ignoring invalid acme.dns01_nameservers entry: %r', candidate)
    return entries


def format_resolver_entries(entries: List[Tuple[str, int]]) -> str:
    """Inverse of :func:`parse_resolver_entries`; port 53 is left implicit."""
    def one(host, port):
        if port == 53:
            return host
        return f'[{host}]:{port}' if ':' in host else f'{host}:{port}'
    return ', '.join(one(h, p) for h, p in entries)


def _parse_resolver_ips(raw: str) -> List[str]:
    """Resolvers on port 53 only, for callers that cannot take a port."""
    return [host for host, port in parse_resolver_entries(raw) if port == 53]


def _config_value(key: str) -> str:
    try:
        from models import SystemConfig

        setting = SystemConfig.query.filter_by(key=key).first()
        return (setting.value or '') if setting else ''
    except Exception:
        return ''


def dns01_resolver_mode() -> str:
    mode = _config_value('acme.dns01_resolver_mode').strip().lower()
    return mode if mode in RESOLVER_MODES else 'auto'


def configured_nameservers_raw() -> str:
    return _config_value('acme.dns01_nameservers')


def _configured_entries() -> List[Tuple[str, int]]:
    if dns01_resolver_mode() == 'system':
        return []
    return parse_resolver_entries(_config_value('acme.dns01_nameservers'))


def get_configured_dns01_nameservers() -> List[str]:
    """Configured resolver IPs on port 53 (empty in ``system`` mode)."""
    return [host for host, port in _configured_entries() if port == 53]


def configured_resolver():
    """dns.resolver.Resolver over the configured resolvers, or None to use the system one."""
    entries = _configured_entries()
    if not entries:
        return None
    import dns.nameserver
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = [dns.nameserver.Do53Nameserver(host, port) for host, port in entries]
    resolver.timeout = 5
    resolver.lifetime = 10
    return resolver


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


def _resolve_with_ns(name: str, nameservers: List[str], rtype: str = 'TXT', lifetime: float = 10,
                     recurse: bool = True):
    import dns.resolver

    resolver = dns.resolver.Resolver(configure=False)
    resolver.nameservers = nameservers
    resolver.timeout = min(5, lifetime)
    resolver.lifetime = lifetime
    if not recurse:
        # RD clear: an authoritative server that also recurses answers from its own data only.
        resolver.flags = 0
    return resolver.resolve(name, rtype)


# Authoritative servers answer in milliseconds; each one is polled separately.
AUTHORITATIVE_QUERY_LIFETIME = 4


def _authoritative_nameservers(name: str) -> List[Tuple[str, List[str]]]:
    """(NS host, its A then AAAA addresses) for each authoritative NS of *name*'s zone."""
    import dns.resolver

    parts = name.rstrip('.').split('.')
    for i in range(len(parts) - 1):
        zone = '.'.join(parts[i:])
        try:
            ns_answers = dns.resolver.resolve(zone, 'NS', lifetime=10)
        except Exception:
            continue

        servers: List[Tuple[str, List[str]]] = []
        for ns in ns_answers:
            host = str(ns).rstrip('.')
            ips: List[str] = []
            for family in ('A', 'AAAA'):
                try:
                    addrs = dns.resolver.resolve(host, family, lifetime=5)
                    ips.extend(str(r) for r in addrs)
                except Exception:
                    pass
            if ips:
                servers.append((host, ips))
        if servers:
            return servers
    return []


MAX_CNAME_HOPS = 8


def _cname_target(response, qname: str) -> Optional[str]:
    """End of the CNAME chain for *qname* in *response*'s answer section, if any."""
    import dns.rdatatype

    def norm(name) -> str:
        return str(name).rstrip('.').lower()

    hops = {norm(rrset.name): norm(rrset[0].target) for rrset in response.answer
            if rrset.rdtype == dns.rdatatype.CNAME and len(rrset)}
    current = norm(qname)
    for _ in range(MAX_CNAME_HOPS):
        if current not in hops:
            break
        current = hops[current]
    else:
        return None
    return None if current == norm(qname) else current


def _negative_reply(exc, qname: str):
    """('lacks', None) when an authoritative server (AA) holds no TXT for *qname*,
    ('hop', target) when its answer is a CNAME chain without the TXT,
    ('skip', None) for a lame or unreadable reply."""
    import dns.flags
    import dns.resolver

    try:
        if isinstance(exc, dns.resolver.NXDOMAIN):
            responses = list(exc.responses().values())
        else:
            responses = [exc.response()]
    except Exception:
        return 'skip', None
    for response in responses:
        if not response.flags & dns.flags.AA:
            continue
        target = _cname_target(response, qname)
        return ('hop', target) if target else ('lacks', None)
    return 'skip', None


def _authoritative_txt_answers(name: str, expected: str, seen: frozenset = frozenset()):
    """Answers once every authoritative NS of *name* that responds serves
    *expected*; ``[]`` while one still lacks it; None when none responds or a
    CNAME it returns cannot be checked.

    The CA validates from several vantage points that each reach any NS, so a
    single up-to-date server proves nothing. A CNAME is followed only as the
    authoritative servers return it, never from a recursive cache (wildcards).
    """
    import dns.flags
    import dns.resolver

    seen = seen | {name.rstrip('.').lower()}
    servers = _authoritative_nameservers(name) if len(seen) <= MAX_CNAME_HOPS else []
    confirmed, lagging, hops = None, [], set()
    for host, ips in servers:
        try:
            answers = _resolve_with_ns(name, ips, lifetime=AUTHORITATIVE_QUERY_LIFETIME, recurse=False)
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer) as exc:
            verdict, target = _negative_reply(exc, name)
            if verdict == 'lacks':
                lagging.append(host)
            elif verdict == 'hop':
                hops.add(target)
            else:
                acme_log(logger, 'TXT via %s for %s: non-authoritative reply ignored', host, name)
            continue
        except Exception as exc:
            acme_log(logger, 'TXT via authoritative %s failed for %s: %s', host, name, exc)
            continue
        response = getattr(answers, 'response', None)
        if response is not None and not response.flags & dns.flags.AA:
            acme_log(logger, 'TXT via %s for %s: non-authoritative reply ignored', host, name)
        elif _answers_contain_expected(answers, expected):
            confirmed = answers
        else:
            lagging.append(host)
    if lagging:
        acme_log(logger, 'TXT for %s not yet served by authoritative %s', name, ', '.join(lagging))
        return []
    unchecked = False
    for target in sorted(hops):
        result = None if target in seen else _authoritative_txt_answers(target, expected, seen)
        if result == []:
            return []
        if result is None:
            unchecked = True
        else:
            confirmed = result
    if unchecked:
        acme_log(logger, 'TXT for %s: a CNAME returned by its nameservers could not be checked', name)
        return None
    return confirmed


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
    the configured resolver or every authoritative one sees the TXT record, regardless of
    whether the public recursors have caught up. The line is emitted even on
    success to aid debugging; a ``pending`` entry does NOT block issuance.
    Skipped outside ``auto`` mode, where public resolvers must not be queried.
    """
    if dns01_resolver_mode() != 'auto':
        return {}
    status = check_public_resolvers(name, expected)
    parts = [f'{ip}={"OK" if ok else "pending"}' for ip, ok in status.items()]
    logger.info(
        'DNS public propagation for %s (diagnostic, does not block issuance): %s',
        name, ', '.join(parts),
    )
    return status


def resolve_txt_answers(name: str, expected: str) -> Tuple[object, str]:
    """Resolve TXT records per ``acme.dns01_resolver_mode`` (see module docstring).

    Returns (answers, source) where *source* identifies the winning resolver.
    """
    import dns.resolver

    mode = dns01_resolver_mode()
    custom = configured_resolver()
    if custom is not None:
        try:
            return custom.resolve(name, 'TXT'), 'configured'
        except Exception as exc:
            acme_log(logger, 'TXT via configured NS failed for %s: %s', name, exc)
            if mode == 'custom':
                raise
    if mode != 'auto':
        return dns.resolver.resolve(name, 'TXT', lifetime=10), 'recursive'

    answers = _authoritative_txt_answers(name, expected)
    if answers is not None:
        return answers, 'authoritative'

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
        answers, source = resolve_txt_answers(name, expected)
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
