"""SSRF protection utilities — validate URLs/hosts don't resolve to private IPs."""

import ipaddress
import logging
import socket
import threading
from contextlib import contextmanager
from urllib.parse import urlparse, urljoin

logger = logging.getLogger(__name__)


def validate_url_not_private(url: str) -> None:
    """Validate that a URL doesn't resolve to a private/reserved IP.
    
    Raises ValueError if the URL host resolves to private, loopback,
    reserved, or link-local addresses.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")
    validate_host_not_private(host)


def validate_host_not_private(host: str) -> list:
    """Validate that a hostname doesn't resolve to a private/reserved IP.

    Raises ValueError if the host is — or resolves to — a private, loopback,
    reserved or link-local address, or if it cannot be resolved at all.

    Returns every validated IP address (deduplicated, in resolver order), so
    a caller can pin its connection to exactly what was checked (see
    pin_host) instead of letting the HTTP client resolve the name a second
    time. The whole set comes back because the loop below rejects the host
    outright if ANY address is forbidden — so on return every address is
    public-safe, and discarding any of them would only cost the caller
    multi-A/dual-stack failover, not security.
    """
    # First check if host is already an IP. A trailing root dot
    # ("169.254.169.254.") names the same address on any resolver that accepts
    # it, so it must not turn the literal into an opaque "hostname".
    # Parsing and policy are decided SEPARATELY: ipaddress.ip_address()
    # embeds its input verbatim in the ValueError it raises ("'<host>' does
    # not appear to be an IPv4 or IPv6 address"), so deciding from the
    # message text would refuse any hostname that merely CONTAINS a policy
    # word — e.g. private-ca.corp.example.com.
    try:
        ip = ipaddress.ip_address(host.rstrip('.') or host)
    except ValueError:
        ip = None  # Not an IP literal — resolve it below.
    if ip is not None:
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise ValueError(f"Host {host} is a private/reserved IP address")
        return [str(ip)]

    # Fail CLOSED when the host can be neither parsed nor resolved. Treating
    # that as "not a SSRF risk" was a fail-open: a value like
    # "169.254.169.254:80" or "evil@169.254.169.254" is unresolvable as a
    # HOSTNAME, but requests re-parses it as a URL authority, splits off the
    # port/userinfo and happily connects to the private address behind it.
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve host {host}: {e}")

    chosen = []
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local:
            raise ValueError(f"Host {host} resolves to private/reserved IP {ip}")
        if str(ip) not in chosen:
            chosen.append(str(ip))

    if not chosen:
        raise ValueError(f"Host {host} produced no usable IP addresses")
    return chosen


# Cloud metadata endpoints and loopback — NEVER legitimate targets for
# outbound HTTP from UCM. Unlike validate_url_not_private (which also blocks
# RFC1918 private ranges), this narrow check allows admins to legitimately
# point UCM at internal infrastructure (AD, Keycloak on 10.x, internal ACME
# CAs, on-prem IdP) while still blocking the highest-impact SSRF targets:
# cloud instance metadata services (which leak IAM credentials) and loopback
# (which would let attackers probe UCM's own internal endpoints).
_CLOUD_METADATA_IPS = {
    '169.254.169.254',          # AWS, Azure, DigitalOcean, GCP (also link-local)
    '169.254.170.2',            # AWS ECS/EKS task credentials (see note below)
    '100.100.100.200',          # Alibaba Cloud
    '192.0.0.192',              # Oracle Cloud (see note below)
    '169.254.42.42',            # Scaleway
    'fd00:ec2::254',            # AWS IPv6
    'fd00:42::42',              # Scaleway IPv6
}
# 192.0.0.192 sits in 192.0.0.0/24, which `ipaddress` calls private, and this
# guard lets private addresses through on purpose: UCM is pointed at internal
# infrastructure all the time. So being private refuses nothing, and the
# address has to be named like the others.
# 169.254.170.2 is NOT the instance metadata service, which is why it was missed:
# it is the ECS task-credentials endpoint, reached by appending the container's
# AWS_CONTAINER_CREDENTIALS_RELATIVE_URI. It hands out live task-role IAM
# credentials exactly as IMDS does, so the impact is identical even though the
# address is not. Blocked unconditionally with the rest -- a link-local address
# is never a legitimate ACME/webhook/SSO target, whatever allow_private_ips says.
_CLOUD_METADATA_HOSTS = {
    'metadata.google.internal',
    'metadata',                 # GCP short name
    'metadata.goog',
}

# Deny-list as parsed IP objects so an IPv4-mapped IPv6 form (::ffff:a.b.c.d) can't
# evade a string comparison by re-encoding an IPv4 target as IPv6.
_CLOUD_METADATA_IP_OBJS = {ipaddress.ip_address(a) for a in _CLOUD_METADATA_IPS}

# The well-known NAT64 prefix (RFC 6052 §2.1): on an IPv6-only network, a
# gateway translates 64:ff9b::<a.b.c.d> back to that IPv4 address. So
# The embedded address is read out and judged like any other rather than the
# prefix being refused wholesale. The well-known prefix is a /96 and says so;
# the local-use one is a container (RFC 8215 section 4.1) out of which an
# operator cuts their real prefix, so several layouts fit and all are read.
_NAT64_WELL_KNOWN = ipaddress.ip_network('64:ff9b::/96')
_NAT64_LOCAL_USE = ipaddress.ip_network('64:ff9b:1::/48')

# The prefix lengths an operator may have cut out of the local-use container.
# RFC 8215 reports /64 as the shortest translation prefix seen deployed; the
# container itself is listed too, since nothing stops it being used directly.
_LOCAL_USE_CANDIDATES = (48, 56, 64, 96)

# RFC 6052 section 2.2, one row per allowed prefix length: where the IPv4
# address sits, as (first bit, last bit) counted from the most significant,
# high part then low part. Bits 64 to 71 are `u` and sit between them.
_RFC6052_LAYOUT = {
    32: ((32, 63), None),
    40: ((40, 63), (72, 79)),
    48: ((48, 63), (72, 87)),
    56: ((56, 63), (72, 95)),
    64: ((72, 103), None),
    96: ((96, 127), None),
}


def _bits(value: int, first: int, last: int) -> int:
    return (value >> (127 - last)) & ((1 << (last - first + 1)) - 1)


def _rfc6052_ipv4(value: int, prefix_length: int):
    """The IPv4 address an RFC 6052 section 2.2 layout carries, or None.

    The address is the low 32 bits only for a /96 prefix. For every shorter
    one the octets are laid around bits 64 to 71, which are reserved and must
    be zero. Reading those eight bits as part of the address is how
    `64:ff9b:1:a9fe:a9:fe00::`, which is the metadata service, came back as
    169.254.0.254 and went through.

    All six lengths the specification allows are read. Returning None for the
    four that were missing was fail-open: the address fell back on its bare
    IPv6 judgement, which is exactly the judgement that cannot see through a
    translation prefix.

    Bits 64 to 71 are the reserved `u` octet and never belong to the address:
    the layouts above step around them. They are not checked either, and that
    is deliberate. Section 2.2 requires a sender to set them to zero, but the
    extraction in section 2.3 says to remove the octet and read on, with no
    validation, so a conforming translator forwards an address whose `u` is
    not zero. Refusing to decode one was a way of not looking:
    `64:ff9b:1:1:ffa9:fea9:fe00:0` carries 169.254.169.254 in bits 72 to 103,
    read it or not, and not reading it let it through.
    """
    layout = _RFC6052_LAYOUT.get(prefix_length)
    if layout is None:
        return None
    high, low = layout
    carried = _bits(value, *high)
    if low is not None:
        carried = (carried << (low[1] - low[0] + 1)) | _bits(value, *low)
    return ipaddress.ip_address(carried)


def _nat64_readings(ip):
    """What a NAT64 form carries, as (certain, speculative).

    Certain means the layout is known from the prefix alone. Speculative
    means several layouts fit and only the operator knows which, so a reading
    that lands somewhere alarming is as likely to be the wrong layout as a
    real target. The two are judged differently.
    """
    if ip.version != 6:
        return (), ()
    if ip in _NAT64_WELL_KNOWN:
        carried = _rfc6052_ipv4(int(ip), 96)
        return ((carried,) if carried is not None else ()), ()
    if ip in _NAT64_LOCAL_USE:
        readings = tuple(
            r for r in (_rfc6052_ipv4(int(ip), n) for n in _LOCAL_USE_CANDIDATES)
            if r is not None)
        return (), readings
    return (), ()


# The deprecated IPv4-compatible form, ::a.b.c.d (RFC 4291 section 2.5.5.1).
_IPV4_COMPATIBLE = ipaddress.ip_network('::/96')

# ISATAP (RFC 5214 section 6.1): the interface identifier is 00-00-5E-FE or,
# when the address is globally unique, 02-00-5E-FE, followed by the IPv4
# address. `fe80::5efe:169.254.169.254` reaches the metadata service.
_ISATAP_IDENTIFIERS = (0x00005EFE, 0x02005EFE)


def _ipv4_forms(ip):
    """Every IPv4 address an IPv6 encoding certainly carries. Possibly none.

    Six ways of writing an IPv4 address as IPv6 reach the same host: the
    mapped form, the deprecated compatible form, 6to4, Teredo, NAT64 and
    ISATAP. A deny-list that understands one of them refuses one spelling of
    an address and accepts the others, which is how `169.254.169.254` kept
    coming back.

    Teredo yields two: the Teredo server, whose IPv4 address sits in bits 32
    to 63, and the client behind it, whose address is stored as its ones
    complement. The client is the host the traffic is for; the server is
    judged as well because it is named in the same address and costs nothing
    to read.
    """
    if ip.version != 6:
        return ()

    certain, _speculative = _nat64_readings(ip)
    found = list(certain)
    for candidate in (getattr(ip, 'ipv4_mapped', None),
                      getattr(ip, 'sixtofour', None)):
        if candidate is not None:
            found.append(candidate)

    teredo = getattr(ip, 'teredo', None)
    if teredo is not None:
        found.extend(teredo)

    if _bits(int(ip), 64, 95) in _ISATAP_IDENTIFIERS:
        found.append(ipaddress.ip_address(int(ip) & 0xFFFFFFFF))

    if ip in _IPV4_COMPATIBLE:
        found.append(ipaddress.ip_address(int(ip) & 0xFFFFFFFF))

    return tuple(found)


def _speculative_ipv4_forms(ip):
    """Addresses an ambiguous encoding may carry, one layout among several."""
    if ip.version != 6:
        return ()
    _certain, speculative = _nat64_readings(ip)
    return speculative


def _forbidden_ip_reason(ip, allow_loopback: bool = False):
    """Why `ip` (an ipaddress object) is a forbidden SSRF target — cloud metadata,
    loopback, or unspecified (0.0.0.0 / ::, which route to loopback on most OSes) — or
    None. Every IPv4 address an IPv6 encoding carries is judged as well as the
    address itself, so no spelling of a denied address gets through by being
    written another way. One exception is deliberate: under a translation
    prefix whose layout is unknown, the readings are judged against the
    metadata endpoints only, not against loopback, because a reading taken
    with the wrong layout lands there readily.

    allow_loopback=True permits loopback/unspecified (for a colocated ACME upstream
    such as Pebble/step-ca on 127.0.0.1); cloud metadata stays blocked regardless."""
    for carried in _ipv4_forms(ip):
        # Judged on every address the encoding carries, not only on the one
        # this happens to recognise first.
        if carried in _CLOUD_METADATA_IP_OBJS:
            return "cloud metadata IP"
        if (carried.is_loopback or carried.is_unspecified) and not allow_loopback:
            return "loopback/unspecified address"

    speculative = _speculative_ipv4_forms(ip)
    if speculative:
        # Only one layout is the operator's and the address does not say which.
        # Metadata endpoints are worth the guess; loopback and 0.0.0.0 are
        # not, since a wrong layout lands on them readily. This leaves a
        # loopback behind a translator open, which is the translator's own.
        for carried in speculative:
            if carried in _CLOUD_METADATA_IP_OBJS:
                return "cloud metadata IP"
        if all(c.is_unspecified for c in speculative) and not allow_loopback:
            # Every layout agrees, so this is the prefix's own base address
            # and it carries nothing.
            return "loopback/unspecified address"

    if ip in _CLOUD_METADATA_IP_OBJS:
        return "cloud metadata IP"
    if (ip.is_loopback or ip.is_unspecified) and not allow_loopback:
        return "loopback/unspecified address"
    return None


def validate_url_not_cloud_metadata(url: str, allow_loopback: bool = False) -> None:
    """Validate that a URL doesn't target cloud metadata services or loopback.

    This is a *narrow* SSRF guard — it explicitly ALLOWS RFC1918 private IPs
    (10.x, 192.168.x, 172.16.x) because UCM is commonly configured against
    internal infrastructure (AD, internal Keycloak, on-prem IdP, internal
    ACME CAs). It blocks only the highest-impact SSRF targets:

    - Cloud instance metadata endpoints (credential exfiltration)
    - Loopback (would let a compromised admin probe UCM's own internals)

    allow_loopback=True is an opt-in used only for a colocated ACME upstream
    (Pebble/step-ca on 127.0.0.1); cloud metadata stays blocked regardless.

    Raises ValueError if the URL targets a forbidden endpoint.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    host_l = host.lower().rstrip('.')

    # Short-circuit: explicit bad hostnames
    if host_l in _CLOUD_METADATA_HOSTS:
        raise ValueError(f"Host {host} is a cloud metadata endpoint")

    # Check literal IP (host_l has any trailing root dot stripped — "127.0.0.1."
    # reaches the same address wherever the resolver accepts it). Parsing and
    # policy are decided SEPARATELY: ip_address()'s parse error embeds the
    # hostname verbatim, so matching on the exception message would refuse
    # legitimate names that merely CONTAIN "metadata"/"loopback"/"unspecified"
    # — e.g. metadata-db.corp.example.com.
    try:
        ip = ipaddress.ip_address(host_l)
    except ValueError:
        ip = None  # Not a literal IP — fall through to DNS resolution.
    if ip is not None:
        reason = _forbidden_ip_reason(ip, allow_loopback)
        if reason:
            raise ValueError(f"Host {host} is a {reason}")
        return

    # Resolve hostname and check all returned IPs. Fail CLOSED when the host
    # cannot be resolved, the same rule validate_host_not_private applies:
    # "cannot resolve, so cannot reach anything" proved to be a fail-open —
    # the HTTP client re-parses odd values as a URL authority and resolves on
    # its own, and a resolver that answers the fetch but SERVFAILs this check
    # would otherwise switch the guard off entirely.
    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve host {host}: {e}")
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        reason = _forbidden_ip_reason(ip, allow_loopback)
        if reason:
            raise ValueError(f"Host {host} resolves to {reason} {ip}")


# ---------------------------------------------------------------------------
# DNS-rebinding-safe outbound HTTP
# ---------------------------------------------------------------------------
#
# validate_url_not_cloud_metadata() resolves the hostname once, but the
# subsequent requests.* call resolves it AGAIN. A hostile / compromised DNS
# server can return a benign IP for the validation lookup and a forbidden
# IP (cloud metadata, loopback, etc.) for the connection lookup — classic
# DNS rebinding.
#
# The standard mitigation is to resolve once, validate the IP, and then
# pin the connection to that exact IP while preserving the original
# hostname for SNI + certificate verification. We implement that by
# installing a thread-local override of urllib3's create_connection.
#
# Caller responsibility: only use safe_request_post() / safe_request_get() /
# safe_request_head() for outbound HTTP whose URL is provided by an authenticated UCM admin
# (webhooks, SSO discovery, etc.). Protocol-driven fetches (ACME challenge
# validation, CDP/OCSP) run their own identifier validation instead — but that
# validation resolves the name and then lets the HTTP client resolve it again,
# so it is only rebinding-safe where the caller pins the connection itself with
# pin_host() (ACME HTTP-01 / TLS-ALPN-01 do, when private IPs are disallowed).

_pinned_resolution = threading.local()


def _patched_create_connection(address, *args, **kwargs):
    sock = _pinned_create_connection(address, *args, **kwargs)
    watch = getattr(_pinned_resolution, 'socket_watch', None)
    if watch is not None:
        try:
            watch(sock)
        except BaseException:
            sock.close()
            raise
    return sock


def _pinned_create_connection(address, *args, **kwargs):
    """urllib3.util.connection.create_connection wrapper that re-routes
    the connection to a thread-locally pinned IP while keeping the
    original hostname intact for SNI / cert verification.

    A pinned entry may be a single IP or a list of validated IPs; a list is
    tried in order — mirroring urllib3's own getaddrinfo loop — so pinning
    does not silently discard multi-A/dual-stack failover. The original
    hostname is NEVER handed back to the OS resolver while a pin is in
    place, even when every pinned address fails: a rebinding answer outside
    the validated set must stay unreachable."""
    pinned = getattr(_pinned_resolution, 'host_to_ip', None)
    if pinned:
        host, port = address
        ips = pinned.get(host.lower().rstrip('.'))
        if ips:
            if isinstance(ips, str):
                ips = [ips]
            err = None
            for ip in ips:
                try:
                    return _orig_create_connection((ip, port), *args, **kwargs)
                except OSError as e:
                    err = e
            raise err
    return _orig_create_connection(address, *args, **kwargs)


# Lazy import & patch — only when a caller actually wants safe outbound HTTP.
_orig_create_connection = None
_patch_lock = threading.Lock()


def _ensure_urllib3_patched():
    global _orig_create_connection
    if _orig_create_connection is not None:
        return
    with _patch_lock:
        if _orig_create_connection is not None:
            return
        from urllib3.util import connection as urllib3_connection
        _orig_create_connection = urllib3_connection.create_connection
        urllib3_connection.create_connection = _patched_create_connection


@contextmanager
def watch_sockets(callback):
    """Within this block, every socket urllib3 opens on this thread is passed to
    `callback` as soon as it is connected (before TLS, which detaches it)."""
    _ensure_urllib3_patched()
    prev = getattr(_pinned_resolution, 'socket_watch', None)
    _pinned_resolution.socket_watch = callback
    try:
        yield
    finally:
        _pinned_resolution.socket_watch = prev


@contextmanager
def pin_host(host: str, ip):
    """Within this block, all urllib3 connections to `host` go to `ip` —
    a single IP string, or a list of validated IPs tried in order (see
    _pinned_create_connection)."""
    _ensure_urllib3_patched()
    pinned = getattr(_pinned_resolution, 'host_to_ip', None)
    if pinned is None:
        pinned = {}
        _pinned_resolution.host_to_ip = pinned
    key = host.lower().rstrip('.')
    prev = pinned.get(key)
    pinned[key] = ip
    try:
        yield
    finally:
        if prev is None:
            pinned.pop(key, None)
        else:
            pinned[key] = prev


def _resolve_and_validate(url: str, allow_loopback: bool = False) -> tuple:
    """Resolve URL hostname to its safe IPs. Returns (host, [ips]).

    Every validated address comes back (deduplicated, in resolver order),
    exactly as validate_host_not_private does and for the same reason: the
    loop below refuses the host outright if ANY resolved address is
    forbidden, so on return the whole set is public-safe. Returning only the
    first would pin the caller's outbound HTTP to one address and lose
    multi-A/dual-stack failover for zero security benefit.

    Raises ValueError if the URL has no hostname, fails to resolve,
    or any resolved IP is forbidden (cloud metadata / loopback)."""
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError("URL has no hostname")

    # Already a literal IP — validate and pin to itself. Parse failure must
    # not be conflated with the policy raise: ip_address() embeds the
    # hostname in its parse-error message, so a message sniff would refuse
    # hosts merely containing "metadata"/"loopback"/"unspecified".
    try:
        ip_obj = ipaddress.ip_address(host)
    except ValueError:
        ip_obj = None  # Not a literal IP — resolve below.
    if ip_obj is not None:
        reason = _forbidden_ip_reason(ip_obj, allow_loopback)
        if reason:
            raise ValueError(f"Host {host} is a {reason}")
        return host, [str(ip_obj)]

    try:
        addrs = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve {host}: {e}")

    chosen = []
    for _, _, _, _, sockaddr in addrs:
        ip = ipaddress.ip_address(sockaddr[0])
        reason = _forbidden_ip_reason(ip, allow_loopback)
        if reason:
            raise ValueError(f"Host {host} resolves to {reason} {ip}")
        if str(ip) not in chosen:
            chosen.append(str(ip))

    if not chosen:
        raise ValueError(f"Host {host} produced no usable IPs")

    return host, chosen


def validated_addresses(url: str, allow_loopback: bool = False) -> tuple:
    """The host and the addresses `url` resolves to, once vetted.

    The three helpers below resolve, vet and pin around a single request, and
    that is what most callers want. A caller holding its own
    `requests.Session` cannot use them, and validating on its own leaves the
    name to be resolved a second time when the connection is made: between
    the two, a name answering different addresses in turn reaches whatever it
    likes, with no race to win. This hands back what `pin_host` needs so such
    a caller can vet once and connect to what was vetted.

    The pin must be entered before the session's first connection: a socket
    already in its pool was created outside it.
    """
    return _resolve_and_validate(url, allow_loopback)


# Redirects are where a validated request stops being one: the first host is
# resolved, vetted and pinned, then the upstream answers 302 and requests
# follows it to an address nobody looked at. Each hop goes through the same
# check.
MAX_REDIRECTS = 5
_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_BODY_KEYS = ('data', 'json', 'files')
_BODY_HEADERS = ('content-type', 'content-length', 'transfer-encoding')


def _same_origin(first: str, second: str) -> bool:
    one, two = urlparse(first), urlparse(second)
    return (one.scheme, one.hostname, one.port) == (two.scheme, two.hostname, two.port)


# Headers that may cross to another origin. An allowlist, not a denylist: a
# credential travels under whatever name its provider chose (`X-API-Key`,
# `X-Access-Key`, `Private-Token`, anything), so listing the suspicious names
# is a game that cannot be won. These carry no identity and no payload.
_PORTABLE_HEADERS = frozenset({
    'accept', 'accept-encoding', 'accept-language', 'user-agent',
    'cache-control', 'pragma',
})


def _strip_credentials(kwargs: dict) -> None:
    """Everything the other origin has no business receiving.

    A cross-origin hop is not the request the caller authorised: a webhook
    carries the operator's bearer token, a token exchange carries a client
    secret in its body, and an integration carries its key under a name of
    its own. `requests` drops only `Authorization`; here the request is
    reduced to a bare GET carrying nothing but the headers above.
    """
    for key in ('auth', 'cookies', 'params', *_BODY_KEYS):
        kwargs.pop(key, None)
    headers = kwargs.get('headers')
    if headers:
        kwargs['headers'] = {name: value for name, value in headers.items()
                             if name.lower() in _PORTABLE_HEADERS}


def safe_request(method: str, url: str, *, allow_loopback: bool = False,
                 max_redirects: int = MAX_REDIRECTS, **kwargs):
    """`requests` with every hop resolved, vetted and pinned, not just the first.

    Stricter than requests at an origin change: the hop becomes a bare GET,
    without credentials, body or query, whatever its status. Within one
    origin it follows requests, where a 303 (and a 301/302 on POST) becomes a
    GET without its body. `allow_redirects=False` returns the 3xx itself.
    """
    import requests

    kwargs.setdefault('timeout', 30)
    follow = kwargs.pop('allow_redirects', True)
    current_method = method.upper()
    current_url = url

    for _ in range(max_redirects + 1):
        host, addresses = _resolve_and_validate(current_url, allow_loopback)
        send = getattr(requests, current_method.lower(), None)
        with pin_host(host, addresses):
            if send is None:
                response = requests.request(current_method, current_url,
                                            allow_redirects=False, **kwargs)
            else:
                response = send(current_url, allow_redirects=False, **kwargs)

        if not follow or response.status_code not in _REDIRECT_STATUSES:
            return response
        location = response.headers.get('Location')
        if not location:
            return response

        # The hop is not the answer: close it or its socket never returns to
        # the pool, which matters most under stream=True.
        response.close()

        next_url = urljoin(current_url, location)
        crossed_origin = not _same_origin(current_url, next_url)
        if crossed_origin:
            _strip_credentials(kwargs)
        current_url = next_url

        drops_body = (crossed_origin
                      or response.status_code == 303
                      or (response.status_code in (301, 302)
                          and current_method == 'POST'))
        if drops_body:
            current_method = 'GET'
            for key in _BODY_KEYS:
                kwargs.pop(key, None)
            headers = kwargs.get('headers')
            if headers:
                kwargs['headers'] = {name: value for name, value in headers.items()
                                     if name.lower() not in _BODY_HEADERS}

    raise requests.TooManyRedirects(
        f"Exceeded {max_redirects} redirects starting at {url}")


def safe_request_post(url, allow_loopback: bool = False, **kwargs):
    """requests.post() with DNS-rebinding protection, redirects included.

    Every hop is resolved, vetted against the cloud-metadata deny-list and
    pinned to the addresses that were validated, the whole set so a
    dual-stack upstream keeps its failover. SNI and certificate verification
    keep the original hostname, so HTTPS works normally.

    allow_loopback=True permits a colocated upstream on 127.0.0.1 (ACME
    Pebble/step-ca); cloud metadata stays blocked. Default keeps loopback denied.
    """
    return safe_request('POST', url, allow_loopback=allow_loopback, **kwargs)


def safe_request_get(url, allow_loopback: bool = False, **kwargs):
    """requests.get() counterpart of safe_request_post()."""
    return safe_request('GET', url, allow_loopback=allow_loopback, **kwargs)


def safe_request_head(url, allow_loopback: bool = False, **kwargs):
    """requests.head() with DNS-rebinding protection (e.g. ACME newNonce)."""
    return safe_request('HEAD', url, allow_loopback=allow_loopback, **kwargs)
