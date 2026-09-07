"""
Trusted proxy detection.

Used to gate code paths that trust reverse-proxy-injected headers
(SSL_CLIENT_CERT, X-SSL-Client-*, X-Forwarded-*, etc.). These headers
MUST never be honored when the request originates from an untrusted
source — otherwise an attacker who can reach gunicorn directly (or
poison a header through a misconfigured proxy) can spoof client
certificate authentication and obtain arbitrary certificates.

Configuration:
    UCM_TRUSTED_PROXIES   Comma-separated list of proxy IP addresses or
                          CIDR networks that are allowed to set client-cert
                          / forwarded-for headers. Examples:
                              UCM_TRUSTED_PROXIES=127.0.0.1,::1
                              UCM_TRUSTED_PROXIES=10.0.0.5
                              UCM_TRUSTED_PROXIES=10.42.0.0/16,fd00::/8
                              UCM_TRUSTED_PROXIES=*           (trust all, dangerous)

    A CIDR entry matches any peer inside that network, which is useful
    behind an ingress controller whose pod IP rotates. An entry that is
    neither a valid IP nor a valid network is ignored with a warning (it
    never widens the trust). Default (unset) trusts loopback only
    (127.0.0.1, ::1), safe for nginx/apache running on the same host and
    the most common deploy.
"""
import functools
import ipaddress
import logging
import os

from flask import request

logger = logging.getLogger(__name__)

_DEFAULT_TRUSTED = frozenset({
    ipaddress.ip_address('127.0.0.1'),
    ipaddress.ip_address('::1'),
})


@functools.lru_cache(maxsize=16)
def _compile_trusted_proxies(proxies_str):
    """Parse UCM_TRUSTED_PROXIES into ``(exact_ips, networks, trust_all)``.

    Cached on the raw string so the parse (and any warning log) happens
    once per distinct value rather than on every request.
    """
    proxies_str = (proxies_str or '').strip()
    if not proxies_str:
        return _DEFAULT_TRUSTED, (), False
    if proxies_str == '*':
        return frozenset(), (), True  # explicit opt-in to trust everyone
    exact = set()
    networks = []
    for raw in proxies_str.split(','):
        entry = raw.strip()
        if not entry:
            continue
        try:
            if '/' in entry:
                networks.append(ipaddress.ip_network(entry, strict=False))
            else:
                ip = ipaddress.ip_address(entry)
                exact.add(ip)
                # An entry written in the mapped form (::ffff:10.0.0.5) must
                # also match the bare IPv4 peer PeerAddressNormalizer reports.
                mapped = getattr(ip, 'ipv4_mapped', None)
                if mapped is not None:
                    exact.add(mapped)
        except ValueError:
            logger.warning(
                "Ignoring UCM_TRUSTED_PROXIES entry %r: not an IP address or "
                "CIDR network", entry,
            )
    return frozenset(exact), tuple(networks), False


def _is_trusted_peer(peer):
    """True iff *peer* (a string address) is covered by UCM_TRUSTED_PROXIES."""
    exact, networks, trust_all = _compile_trusted_proxies(
        os.environ.get('UCM_TRUSTED_PROXIES', '')
    )
    if trust_all:
        return True
    if not peer:
        return False
    try:
        ip = ipaddress.ip_address(peer)
    except ValueError:
        return False
    # A dual-stack listener (HOST=::) reports IPv4 peers as ::ffff:a.b.c.d.
    # PeerAddressNormalizer already rewrites REMOTE_ADDR, but match the
    # mapped IPv4 form here too so a bare ::ffff:… slipping through still
    # compares against IPv4 entries and networks.
    mapped = getattr(ip, 'ipv4_mapped', None)
    candidates = (ip, mapped) if mapped is not None else (ip,)
    for cand in candidates:
        if cand in exact:
            return True
        if any(cand in net for net in networks):
            return True
    return False


def immediate_peer_addr() -> str:
    """
    Return the request's real TCP peer, undoing any ProxyFix rewrite.

    When ProxyFix is active (UCM_BEHIND_PROXY=1 / UCM_TRUSTED_PROXY_HOPS>0)
    it overwrites REMOTE_ADDR with a value taken from X-Forwarded-For, so
    request.remote_addr is the *client* IP — client-controlled input — not
    the peer that opened the TCP connection. Werkzeug preserves the original
    peer in environ['werkzeug.proxy_fix.orig']['REMOTE_ADDR'].

    Every trust decision keyed on the peer (trusted-proxy gating, loopback
    checks) MUST use this value. Using request.remote_addr instead is wrong
    in both directions:
      - trusted proxies fail the check (their REMOTE_ADDR was rewritten to
        the client IP, which is not in UCM_TRUSTED_PROXIES), and
      - a direct attacker can PASS the check by sending
        `X-Forwarded-For: 127.0.0.1`, impersonating a trusted peer.
    """
    orig = request.environ.get('werkzeug.proxy_fix.orig')
    if orig is not None:
        # ProxyFix ran: the original entry is the only trustworthy source,
        # even when empty (a WSGI server that sets no REMOTE_ADDR at all).
        return orig.get('REMOTE_ADDR') or ''
    return request.remote_addr or ''


def is_request_from_trusted_proxy() -> bool:
    """
    Return True iff the current request's immediate peer is in the
    trusted-proxy set (or the operator opted in to trust all).

    MUST be called inside a Flask request context.
    """
    return _is_trusted_peer(immediate_peer_addr())


def reject_untrusted_proxy_headers(*header_names) -> bool:
    """
    Convenience: returns True when the named headers should be IGNORED
    because the request did not come from a trusted proxy. Logs a
    warning when one of the headers IS present from an untrusted peer
    (likely a spoof attempt).
    """
    if is_request_from_trusted_proxy():
        return False
    present = [h for h in header_names if request.headers.get(h) or request.environ.get(h)]
    if present:
        logger.warning(
            "Ignoring proxy headers %s from untrusted peer %s",
            present, immediate_peer_addr(),
        )
    return True


def client_ip() -> str:
    """
    Return the best-effort real client IP for audit logging.

    When ProxyFix has rewritten REMOTE_ADDR it has already resolved the
    real client IP using the configured TRUSTED_PROXY_HOPS, so that value
    is returned as-is — re-parsing X-Forwarded-For here would both ignore
    the hop count and trust client-supplied leading entries.

    Otherwise (no ProxyFix, or ProxyFix found no X-Forwarded-For to apply),
    behind a trusted reverse proxy (UCM_TRUSTED_PROXIES contains the
    immediate peer) the left-most entry of X-Forwarded-For is taken as the
    original client IP, falling back to X-Real-IP. When the request
    comes directly from gunicorn or from a peer NOT in the trusted
    set — request.remote_addr is returned and any X-Forwarded-* on
    the request is ignored. This is the same gating that protects
    SSL_CLIENT_* headers; spoofed XFF from untrusted peers must NEVER
    end up in the audit trail as if it were the real client.

    Always returns a non-empty string ('unknown' as last resort).
    """
    orig = request.environ.get('werkzeug.proxy_fix.orig')
    if orig is not None and orig.get('REMOTE_ADDR') != request.remote_addr:
        return request.remote_addr or 'unknown'
    if is_request_from_trusted_proxy():
        xff = request.headers.get('X-Forwarded-For') or ''
        if xff:
            # Left-most IP is the originating client per RFC 7239.
            first = xff.split(',', 1)[0].strip()
            if first:
                return first
        real_ip = request.headers.get('X-Real-IP')
        if real_ip:
            return real_ip.strip()
    return request.remote_addr or 'unknown'
