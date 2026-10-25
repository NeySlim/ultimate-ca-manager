"""Regression tests: ACME challenge SSRF follow-ups to PR #244.

Three holes survived that fix.

1. A ``dns`` identifier was never syntax-checked, so a value carrying a port or
   userinfo ('169.254.169.254:80', 'evil@10.0.0.5') was accepted by new-order.
   Such a value is unresolvable as a HOSTNAME, so ``validate_host_not_private``
   swallowed the resolver error and returned — fail-open — and ``requests`` then
   re-parsed it as a URL *authority*, split off the port/userinfo and connected
   to the private address behind it.

2. The private-address guard only runs when ``acme.allow_private_ips`` is off,
   and it defaults to ON (on-prem issuance is the main use case). So in the
   default configuration an order for 169.254.169.254 still produced a
   challenge GET to the cloud metadata service, even though everywhere else in
   UCM (``validate_url_not_cloud_metadata``) metadata stays blocked while
   RFC 1918 ranges are allowed.

3. The guard resolved the identifier and ``requests`` resolved it again: a
   short-TTL record can answer public for the check and private for the fetch.

The validators are driven through a minimal harness rather than the ``app``
fixture — these are function-level tests of the mixin and need no database.
Every DNS answer is stubbed: the runner's resolver (an NXDOMAIN-hijacking ISP
resolver, say) must never decide the outcome.
"""
import socket

import pytest

import utils.ssrf_protection as ssrf_protection
from services.acme.mixins import challenge as challenge_mod
from services.acme.mixins.challenge import ChallengeMixin


# Values that are NOT resolvable as a hostname but ARE reachable once an HTTP
# client parses them as a URL authority. All five returned without raising
# before the guard was made to fail closed.
UNRESOLVABLE_BUT_REACHABLE = [
    '169.254.169.254:80',
    'evil@169.254.169.254',
    '127.0.0.1:8080',
    '169.254.169.254.',
    '169.254.169.254/latest/meta-data/#',
]


# --------------------------------------------------------------------------
# Harness — the collaborators the two validators actually touch
# --------------------------------------------------------------------------

class _StubSession:
    def __init__(self):
        self.commits = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        pass

    def refresh(self, *_args, **_kwargs):
        # The stub objects are their own source of truth
        pass


class _StubDb:
    def __init__(self):
        self.session = _StubSession()


class _Auth:
    def __init__(self, identifier_type, identifier_value):
        self.identifier_type = identifier_type
        self.identifier_value = identifier_value
        self.status = 'pending'
        self.order = None
        self.challenges = []


class _Challenge:
    def __init__(self, auth, token='ssrf-probe-token'):
        self.authorization = auth
        self.token = token
        self.status = 'pending'
        self.error = None
        self.validated = None
        auth.challenges.append(self)


class _Account:
    jwk_thumbprint = 'test-thumbprint'


class _Service(ChallengeMixin):
    def __init__(self, allow_private_ips):
        self._allow_private_ips = allow_private_ips

    def _acme_allow_private_ips(self):
        return self._allow_private_ips

    def _compute_key_authorization(self, token, jwk_thumbprint):
        return f'{token}.{jwk_thumbprint}'


def _drive(validator_name, identifier_type, value, allow_private_ips):
    """Run one challenge validator against a fresh challenge. Returns
    (result, challenge)."""
    auth = _Auth(identifier_type, value)
    challenge = _Challenge(auth)
    service = _Service(allow_private_ips)
    result = getattr(service, validator_name)(challenge, _Account())
    return result, challenge


def _assert_rejected(result, challenge, outbound):
    """A blocked challenge: no outbound attempt, and the ACME state actually
    says rejectedIdentifier (not merely 'returned False')."""
    assert result is False
    assert not outbound['fetched'], (
        f"the validator reached out to {outbound['target']!r}"
    )
    assert challenge.status == 'invalid'
    assert 'rejectedIdentifier' in (challenge.error or '')
    assert challenge.authorization.status == 'invalid'


@pytest.fixture
def outbound(monkeypatch):
    """Record — and refuse — every outbound attempt a validator makes."""
    import requests

    seen = {'fetched': False, 'target': None, 'pinned': None}

    def _get(url, *_a, **_kw):
        seen['fetched'] = True
        seen['target'] = url
        seen['pinned'] = dict(
            getattr(ssrf_protection._pinned_resolution, 'host_to_ip', None) or {}
        )
        raise AssertionError(f'SSRF: outbound HTTP attempted to {url!r}')

    def _connect(address, *_a, **_kw):
        seen['fetched'] = True
        seen['target'] = address
        raise AssertionError(f'SSRF: outbound connection attempted to {address!r}')

    monkeypatch.setattr(requests, 'get', _get)
    monkeypatch.setattr(socket, 'create_connection', _connect)
    monkeypatch.setattr(challenge_mod, 'db', _StubDb())
    return seen


@pytest.fixture
def no_dns(monkeypatch):
    """Every name is unresolvable."""
    def _fail(host, *_a, **_kw):
        raise socket.gaierror(-2, 'Name or service not known')

    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo', _fail)


@pytest.fixture
def dns_public(monkeypatch):
    """Every name resolves to one public address."""
    def _public(host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))]

    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo', _public)


@pytest.fixture
def dns_private(monkeypatch):
    """Every name resolves to one RFC 1918 address — the on-prem LAN reality."""
    def _private(host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('10.0.0.5', 0))]

    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo', _private)


@pytest.fixture
def dns_two_public(monkeypatch):
    """Every name resolves to two public addresses (multi-A / failover shape)."""
    def _two(host, *_a, **_kw):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, '', ('198.41.0.4', 0)),
        ]

    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo', _two)


# --------------------------------------------------------------------------
# 1. The guard fails closed on a host it can neither parse nor resolve
# --------------------------------------------------------------------------

@pytest.mark.parametrize('value', UNRESOLVABLE_BUT_REACHABLE)
def test_guard_fails_closed_on_unresolvable_host(value, no_dns):
    with pytest.raises(ValueError):
        ssrf_protection.validate_host_not_private(value)


def test_guard_returns_the_validated_ips_for_pinning(dns_public):
    assert ssrf_protection.validate_host_not_private('example.test') == ['93.184.216.34']
    assert ssrf_protection.validate_host_not_private('8.8.8.8') == ['8.8.8.8']


def test_guard_returns_every_validated_address(dns_two_public):
    """The guard raises if ANY resolved address is private, so when it
    returns, the whole set is already validated — returning only the first
    would discard failover addresses for zero security benefit."""
    assert ssrf_protection.validate_host_not_private('multi.example.test') == [
        '93.184.216.34', '198.41.0.4',
    ]


# --------------------------------------------------------------------------
# 2. new-order / new-authz refuse a DNS identifier that is not a domain name
# --------------------------------------------------------------------------

@pytest.mark.parametrize('value', [
    # '169.254.169.254.' is deliberately absent: it IS a syntactically valid
    # domain name, so it is the guard's job (below), not the parser's.
    '169.254.169.254:80',
    'evil@169.254.169.254',
    '127.0.0.1:8080',
    '169.254.169.254/latest/meta-data/#',
    'host with space.example.com',
    'http://example.com',
    'example.com:443',
    '',
    'x' * 250 + '.example.com',
    '-leading-hyphen.example.com',
    'a..example.com',
    None,
])
def test_malformed_dns_identifier_is_rejected(value):
    from api.acme.acme_api import validate_acme_identifier
    ok, err_type, detail = validate_acme_identifier({'type': 'dns', 'value': value})
    assert ok is False
    assert err_type == 'malformed'
    assert detail


@pytest.mark.parametrize('value', [
    'example.com',
    '*.example.com',
    'sub.example.co.uk',
    'xn--80ak6aa92e.com',      # punycode / IDN A-label
    'host-1.internal.lan',
    'EXAMPLE.com',
    'example.com.',            # single trailing root dot
    '_acme-challenge.example.com',
    'localhost',
])
def test_legitimate_dns_identifier_is_accepted(value):
    from api.acme.acme_api import validate_acme_identifier
    ok, err_type, _ = validate_acme_identifier({'type': 'dns', 'value': value})
    assert ok is True
    assert err_type is None


# --------------------------------------------------------------------------
# 3. End to end: the validators refuse the bypass values
# --------------------------------------------------------------------------

@pytest.mark.parametrize('value', [
    '10.0.0.5:8080',            # port — not metadata, so only the guard can stop it
    'evil@10.0.0.5',            # userinfo
    '169.254.169.254:80',
])
def test_http01_blocks_a_dns_identifier_carrying_a_port_or_userinfo(
    value, outbound, no_dns
):
    result, challenge = _drive(
        'validate_http01_challenge', 'dns', value, allow_private_ips=False
    )
    _assert_rejected(result, challenge, outbound)


# --------------------------------------------------------------------------
# 4. Cloud metadata is refused even when private IPs are allowed (the default)
# --------------------------------------------------------------------------

@pytest.mark.parametrize('identifier_type,value', [
    ('ip', '169.254.169.254'),          # AWS/Azure/GCP IMDS
    ('ip', '100.100.100.200'),          # Alibaba Cloud
    ('ip', 'fd00:ec2::254'),            # AWS IPv6 — bracketed into the URL
    ('dns', 'metadata.google.internal'),
    ('dns', '169.254.169.254.'),        # IP dressed up as a domain name
])
def test_http01_blocks_metadata_with_private_ips_allowed(
    identifier_type, value, outbound, no_dns
):
    result, challenge = _drive(
        'validate_http01_challenge', identifier_type, value,
        allow_private_ips=True,
    )
    _assert_rejected(result, challenge, outbound)


@pytest.mark.parametrize('identifier_type,value', [
    ('ip', '169.254.169.254'),
    ('dns', 'metadata.google.internal'),
])
def test_tls_alpn01_blocks_metadata_with_private_ips_allowed(
    identifier_type, value, outbound, no_dns
):
    result, challenge = _drive(
        'validate_tls_alpn01_challenge', identifier_type, value,
        allow_private_ips=True,
    )
    _assert_rejected(result, challenge, outbound)


@pytest.mark.parametrize('identifier_type,value', [
    ('ip', '10.0.0.5'),          # RFC 1918 — the on-prem use case
    ('ip', '192.168.1.10'),
    ('ip', '127.0.0.1'),         # colocated client
    ('dns', 'printer.internal.lan'),
    # Hostnames CONTAINING a policy word. ipaddress.ip_address() embeds its
    # input verbatim in the parse ValueError ("'<host>' does not appear to
    # be an IPv4 or IPv6 address"), so a guard that decides policy by
    # sniffing the exception message refuses all of these outright.
    ('dns', 'metadata-db.corp.example.com'),
    ('dns', 'svc-metadata.internal.lan'),
    ('dns', 'loopback0.rtr1.corp.example.com'),
    ('dns', 'unspecified-node.corp.lan'),
])
def test_private_targets_still_work_when_allowed(
    identifier_type, value, outbound, dns_private
):
    """Control: the metadata check must not tighten the default configuration
    beyond metadata itself, or every LAN deployment breaks."""
    result, challenge = _drive(
        'validate_http01_challenge', identifier_type, value,
        allow_private_ips=True,
    )
    assert result is False           # the stubbed fetch raises
    assert outbound['fetched'], 'a legitimate private target was blocked'
    assert 'rejectedIdentifier' not in (challenge.error or '')


# --------------------------------------------------------------------------
# 5. DNS rebinding: the fetch is pinned to the address that was validated
# --------------------------------------------------------------------------

def test_http01_pins_the_fetch_to_the_validated_address(outbound, dns_public):
    result, _challenge = _drive(
        'validate_http01_challenge', 'dns', 'rebind.example.test',
        allow_private_ips=False,
    )
    assert result is False           # the stubbed fetch raises
    assert outbound['fetched']
    assert outbound['pinned'].get('rebind.example.test') == ['93.184.216.34'], (
        'the challenge fetch was not pinned to the validated address — a '
        'second DNS answer can still redirect it'
    )


def test_pinned_connection_ignores_a_second_dns_answer(monkeypatch):
    """The pin overrides whatever address the connection lookup would use."""
    ssrf_protection._ensure_urllib3_patched()
    seen = {}
    monkeypatch.setattr(
        ssrf_protection, '_orig_create_connection',
        lambda address, *_a, **_kw: seen.setdefault('address', address),
    )
    with ssrf_protection.pin_host('rebind.example.test', '93.184.216.34'):
        ssrf_protection._patched_create_connection(('rebind.example.test', 80))
    assert seen['address'] == ('93.184.216.34', 80)


# --------------------------------------------------------------------------
# 6. Policy comes from the ADDRESS, never from a parse-error message
# --------------------------------------------------------------------------
#
# ipaddress.ip_address() raises ValueError("'<host>' does not appear to be an
# IPv4 or IPv6 address") — the hostname embedded verbatim. A guard that
# re-raises based on substrings of the exception message therefore refuses
# every ordinary hostname whose NAME contains a policy word.

HOSTNAMES_CONTAINING_POLICY_WORDS = [
    'metadata-db.corp.example.com',
    'svc-metadata.internal.lan',
    'loopback0.rtr1.corp.example.com',
    'unspecified-node.corp.lan',
    'private-ca.corp.example.com',
    'reserved-pool.corp.lan',
]


@pytest.mark.parametrize('host', HOSTNAMES_CONTAINING_POLICY_WORDS)
def test_metadata_guard_allows_hostnames_containing_policy_words(host, dns_public):
    # Must not raise: the name resolves to a public address.
    ssrf_protection.validate_url_not_cloud_metadata(f'http://{host}/x')
    ssrf_protection.validate_url_not_cloud_metadata(
        f'http://{host}/x', allow_loopback=True
    )


@pytest.mark.parametrize('host', HOSTNAMES_CONTAINING_POLICY_WORDS)
def test_private_guard_allows_hostnames_containing_policy_words(host, dns_public):
    assert ssrf_protection.validate_host_not_private(host) == ['93.184.216.34']


@pytest.mark.parametrize('host', HOSTNAMES_CONTAINING_POLICY_WORDS)
def test_resolve_and_validate_allows_hostnames_containing_policy_words(
    host, dns_public
):
    assert ssrf_protection._resolve_and_validate(f'https://{host}/') == (
        host, ['93.184.216.34'],
    )


def test_http01_allows_policy_word_hostname_in_hardened_config(
    outbound, dns_public
):
    """allow_private_ips=false: a public-resolving host whose NAME contains
    'private' must reach the (pinned) fetch, not be refused by a message
    sniff inside validate_host_not_private."""
    result, challenge = _drive(
        'validate_http01_challenge', 'dns', 'private-ca.corp.example.com',
        allow_private_ips=False,
    )
    assert result is False           # the stubbed fetch raises
    assert outbound['fetched'], 'a public-resolving hostname was blocked'
    assert 'rejectedIdentifier' not in (challenge.error or '')


@pytest.mark.parametrize('url', [
    'http://169.254.169.254/latest/meta-data/',
    'http://169.254.169.254./latest/meta-data/',
    'http://169.254.170.2/v2/credentials/',
    'http://[::ffff:169.254.170.2]/v2/credentials/',
    'http://100.100.100.200/',
    'http://[fd00:ec2::254]/',
    'http://[::ffff:169.254.169.254]/',
    'http://metadata.google.internal/computeMetadata/v1/',
    'http://metadata/computeMetadata/v1/',
    'http://metadata.goog/',
])
def test_genuine_metadata_endpoints_are_still_refused(url):
    """Control: separating parse from policy must not loosen the deny-list."""
    with pytest.raises(ValueError):
        ssrf_protection.validate_url_not_cloud_metadata(url, allow_loopback=True)


def test_every_credential_endpoint_is_refused_even_with_private_ips_allowed():
    """The deny-list is checked as a SET, so adding an entry cannot be forgotten here.

    169.254.170.2 was missing for exactly the reason a hand-maintained list
    goes stale: it is not the *instance* metadata service, it is the ECS
    task-credentials endpoint, so it did not look like the thing being listed
    -- while handing out the same live IAM credentials. Deriving the cases
    from _CLOUD_METADATA_IPS means the next address someone adds is covered
    without remembering to add it twice.
    """
    for addr in ssrf_protection._CLOUD_METADATA_IPS:
        host = '[%s]' % addr if ':' in addr else addr
        with pytest.raises(ValueError, match='(?i)metadata'):
            # allow_loopback=True is the permissive setting: a metadata
            # target must be refused regardless of the private-IP policy.
            ssrf_protection.validate_url_not_cloud_metadata(
                'http://%s/' % host, allow_loopback=True
            )


# --------------------------------------------------------------------------
# 7. Pinning keeps the WHOLE validated set — failover survives the pin
# --------------------------------------------------------------------------

def test_http01_pins_the_full_validated_set(outbound, dns_two_public):
    result, _challenge = _drive(
        'validate_http01_challenge', 'dns', 'multi.example.test',
        allow_private_ips=False,
    )
    assert result is False           # the stubbed fetch raises
    assert outbound['fetched']
    assert outbound['pinned'].get('multi.example.test') == [
        '93.184.216.34', '198.41.0.4',
    ], 'pinning must not discard already-validated failover addresses'


def test_pinned_connection_fails_over_within_the_validated_set(monkeypatch):
    """First validated address down -> the pin tries the next, mirroring
    urllib3's own getaddrinfo loop."""
    ssrf_protection._ensure_urllib3_patched()
    attempts = []

    def _connect(address, *_a, **_kw):
        attempts.append(address)
        if address[0] == '93.184.216.34':
            raise ConnectionRefusedError('first validated address is down')
        return 'sock'

    monkeypatch.setattr(ssrf_protection, '_orig_create_connection', _connect)
    with ssrf_protection.pin_host(
        'multi.example.test', ['93.184.216.34', '198.41.0.4']
    ):
        result = ssrf_protection._patched_create_connection(
            ('multi.example.test', 80)
        )
    assert result == 'sock'
    assert attempts == [('93.184.216.34', 80), ('198.41.0.4', 80)]


def test_pin_never_falls_back_to_the_hostname_resolution(monkeypatch):
    """A rebinding answer outside the validated set must stay unreachable:
    even when every pinned address fails, the original hostname is never
    handed back to the OS resolver — the last error surfaces instead."""
    ssrf_protection._ensure_urllib3_patched()
    attempts = []

    def _refuse(address, *_a, **_kw):
        attempts.append(address[0])
        raise ConnectionRefusedError(f'{address[0]} down')

    monkeypatch.setattr(ssrf_protection, '_orig_create_connection', _refuse)
    with ssrf_protection.pin_host(
        'rebind.example.test', ['93.184.216.34', '198.41.0.4']
    ):
        with pytest.raises(ConnectionRefusedError):
            ssrf_protection._patched_create_connection(('rebind.example.test', 80))
    assert attempts == ['93.184.216.34', '198.41.0.4']


class _SecondAddressReached(Exception):
    """Sentinel: the TLS-ALPN probe got as far as the second address."""


def test_tls_alpn01_fails_over_within_the_validated_set(
    monkeypatch, dns_two_public
):
    """The raw-socket path must try every validated address, not give up
    after the first — the guard vetted them all."""
    import socket as socket_mod

    attempts = []

    def _connect(address, *_a, **_kw):
        attempts.append(address[0])
        if address[0] == '93.184.216.34':
            raise ConnectionRefusedError('first validated address is down')
        raise _SecondAddressReached(address[0])   # stop before real TLS

    monkeypatch.setattr(socket_mod, 'create_connection', _connect)
    monkeypatch.setattr(challenge_mod, 'db', _StubDb())
    result, _challenge = _drive(
        'validate_tls_alpn01_challenge', 'dns', 'multi.example.test',
        allow_private_ips=False,
    )
    assert result is False           # the sentinel aborts the validation
    assert attempts == ['93.184.216.34', '198.41.0.4'], (
        'TLS-ALPN-01 gave up after the first validated address'
    )


# --------------------------------------------------------------------------
# 7b. The same rule on the admin-driven outbound path
#     (webhooks / SSO / OIDC / ACME client), which goes through
#     _resolve_and_validate() + safe_request_get/post/head()
# --------------------------------------------------------------------------
#
# _resolve_and_validate() VALIDATES every resolved address — it raises if any
# one of them is cloud metadata or loopback — but used to return only the
# first, so the pin collapsed a multi-A / dual-stack upstream onto a single
# address. That bought no security (the discarded addresses had already
# passed the same check) and cost failover: one dead address broke every
# webhook delivery, SSO metadata fetch and ACME client call to that host.

def test_resolve_and_validate_returns_every_validated_address(dns_two_public):
    assert ssrf_protection._resolve_and_validate('https://multi.example.test/x') == (
        'multi.example.test', ['93.184.216.34', '198.41.0.4'],
    )


def test_resolve_and_validate_returns_a_list_for_a_literal_ip():
    """Literal-IP URLs skip DNS entirely, but the shape must still match."""
    assert ssrf_protection._resolve_and_validate('https://93.184.216.34/x') == (
        '93.184.216.34', ['93.184.216.34'],
    )


class _Answer:
    """A reply the wrappers can read: they look at the status for a redirect."""

    status_code = 200
    headers = {}

    def __eq__(self, other):
        return other in ('ok', 'delivered over sock')


@pytest.mark.parametrize('verb', ['get', 'post', 'head'])
def test_safe_request_pins_the_full_validated_set(verb, monkeypatch, dns_two_public):
    """safe_request_* must hand pin_host every validated address."""
    import requests

    seen = {}

    def _capture(url, **_kw):
        seen['pinned'] = dict(
            getattr(ssrf_protection._pinned_resolution, 'host_to_ip', None) or {}
        )
        return _Answer()

    monkeypatch.setattr(requests, verb, _capture)
    call = getattr(ssrf_protection, f'safe_request_{verb}')
    assert call('https://multi.example.test/x') == 'ok'
    assert seen['pinned'].get('multi.example.test') == [
        '93.184.216.34', '198.41.0.4',
    ], 'pinning must not discard already-validated failover addresses'


@pytest.mark.parametrize('verb', ['get', 'post', 'head'])
def test_safe_request_fails_over_within_the_validated_set(
    verb, monkeypatch, dns_two_public
):
    """A two-A host whose FIRST address is unreachable still delivers: the
    pin carries both validated addresses and the connection layer moves on to
    the next, exactly as urllib3's own getaddrinfo loop would. requests is
    stubbed to stand in for urllib3 and open the connection itself, so the
    real resolve -> validate -> pin -> connect chain is what runs."""
    import requests

    ssrf_protection._ensure_urllib3_patched()
    attempts = []

    def _connect(address, *_a, **_kw):
        attempts.append(address)
        if address[0] == '93.184.216.34':
            raise ConnectionRefusedError('first validated address is down')
        return 'sock'

    monkeypatch.setattr(ssrf_protection, '_orig_create_connection', _connect)

    def _request(url, **_kw):
        # What urllib3 does inside requests, while the pin is in force.
        sock = ssrf_protection._patched_create_connection(('multi.example.test', 443))
        answer = _Answer()
        answer.delivered_over = sock
        return answer

    monkeypatch.setattr(requests, verb, _request)
    call = getattr(ssrf_protection, f'safe_request_{verb}')
    assert call('https://multi.example.test/x').delivered_over == 'sock'
    assert attempts == [('93.184.216.34', 443), ('198.41.0.4', 443)], (
        'the outbound request gave up after the first validated address'
    )


# --------------------------------------------------------------------------
# 8. The metadata guard fails closed on an unresolvable host
# --------------------------------------------------------------------------
#
# In the DEFAULT configuration (allow_private_ips=true) this guard is the
# ONLY one that runs before the challenge fetch. Its old
# ``except socket.gaierror: pass`` waved through any value its own resolver
# could not answer — while requests re-parses and re-resolves the value on
# its own: the exact fail-open this PR closed in validate_host_not_private.

def test_metadata_guard_fails_closed_on_unresolvable_host(no_dns):
    with pytest.raises(ValueError):
        ssrf_protection.validate_url_not_cloud_metadata(
            'http://unresolvable.example.test/x', allow_loopback=True
        )


def test_http01_refuses_an_unresolvable_identifier_in_the_default_config(
    outbound, no_dns
):
    result, challenge = _drive(
        'validate_http01_challenge', 'dns', 'servfail.example.test',
        allow_private_ips=True,
    )
    _assert_rejected(result, challenge, outbound)


def test_tls_alpn01_refuses_an_unresolvable_identifier_in_the_default_config(
    outbound, no_dns
):
    result, challenge = _drive(
        'validate_tls_alpn01_challenge', 'dns', 'servfail.example.test',
        allow_private_ips=True,
    )
    _assert_rejected(result, challenge, outbound)


# --------------------------------------------------------------------------
# 6. The default policy (private addresses allowed) is pinned as well: the
#    metadata check resolved the name, a second answer must not reach IMDS
# --------------------------------------------------------------------------

def test_http01_pins_under_the_default_policy(outbound, dns_private):
    _drive('validate_http01_challenge', 'dns', 'lan.example.test', allow_private_ips=True)
    assert outbound['fetched']
    assert outbound['pinned'].get('lan.example.test') == ['10.0.0.5']


def test_tls_alpn01_connects_to_the_vetted_address_under_the_default_policy(outbound, dns_private):
    _drive('validate_tls_alpn01_challenge', 'dns', 'lan.example.test', allow_private_ips=True)
    assert outbound['target'] == ('10.0.0.5', 443)


def test_a_redirect_hop_is_pinned_under_the_default_policy(monkeypatch, dns_private):
    import requests
    from services.acme import http01

    pinned = []

    class _Answer:
        def __init__(self, status, location=None):
            self.status_code = status
            self.headers = {'Location': location} if location else {}

    def _get(url, **_kw):
        pinned.append(dict(getattr(ssrf_protection._pinned_resolution, 'host_to_ip', None) or {}))
        if len(pinned) == 1:
            return _Answer(302, 'http://next.example.test/.well-known/acme-challenge/t')
        return _Answer(200)

    monkeypatch.setattr(requests, 'get', _get)
    first = ('first.example.test', ['10.0.0.5'])
    http01.fetch_following_redirects('http://first.example.test/x', first, allow_private=True)
    assert pinned[1].get('next.example.test') == ['10.0.0.5']


@pytest.fixture
def dns_rebinding(monkeypatch):
    """A name answering a LAN address to the first lookup, cloud metadata after."""
    answers = iter(['10.0.0.5'])

    def _rebind(host, *_a, **_kw):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (next(answers, '169.254.169.254'), 0))]

    monkeypatch.setattr(ssrf_protection.socket, 'getaddrinfo', _rebind)


@pytest.mark.parametrize('validator', ['validate_http01_challenge', 'validate_tls_alpn01_challenge'])
def test_a_rebinding_caught_by_the_second_lookup_rejects_the_identifier(
        outbound, dns_rebinding, validator):
    result, challenge = _drive(validator, 'dns', 'lan.example.test', allow_private_ips=True)
    _assert_rejected(result, challenge, outbound)


def test_the_client_self_check_pins_its_first_hop(outbound, dns_private):
    from services.acme import http01

    http01.challenge_reachable('lan.example.test', {'token': 't', 'key_authorization': 'k'})
    assert outbound['pinned'].get('lan.example.test') == ['10.0.0.5']
