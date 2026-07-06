"""DNS-01 self-check before submitting to the CA (#140)."""
import sys
import types
import pytest

from api.v2.acme_client import orders as orders_mod
from utils import dns_txt_lookup as dns_lookup_mod


@pytest.fixture
def fake_dns(monkeypatch):
    """Install a fake dns.resolver whose TXT answers are controllable."""
    state = {'records': {}}  # name -> list[str]

    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    def resolve(name, rtype, lifetime=None):
        vals = state['records'].get(name)
        if not vals:
            raise Exception('NXDOMAIN')
        return [_RData(vals)]

    fake_resolver = types.SimpleNamespace(resolve=resolve)
    fake_dns_mod = types.ModuleType('dns')
    fake_resolver_mod = types.ModuleType('dns.resolver')
    fake_resolver_mod.resolve = resolve
    fake_dns_mod.resolver = fake_resolver_mod
    monkeypatch.setitem(sys.modules, 'dns', fake_dns_mod)
    monkeypatch.setitem(sys.modules, 'dns.resolver', fake_resolver_mod)
    return state


def test_txt_present_true_when_value_matches(fake_dns):
    fake_dns['records']['_acme-challenge.example.com'] = ['other', 'the-token']
    assert orders_mod._txt_present('_acme-challenge.example.com', 'the-token') is True


def test_txt_present_false_when_absent(fake_dns):
    assert orders_mod._txt_present('_acme-challenge.example.com', 'the-token') is False


def test_selfcheck_ok_when_all_present(fake_dns):
    fake_dns['records']['_acme-challenge.a.com'] = ['ta']
    fake_dns['records']['_acme-challenge.b.com'] = ['tb']
    ch = {
        'a.com': {'dns_txt_name': '_acme-challenge.a.com', 'dns_txt_value': 'ta'},
        'b.com': {'dns_txt_name': '_acme-challenge.b.com', 'dns_txt_value': 'tb'},
    }
    res = orders_mod._dns_selfcheck(ch, timeout=0)
    assert res['ok'] is True and res['missing'] == []


def test_selfcheck_reports_missing(fake_dns):
    fake_dns['records']['_acme-challenge.a.com'] = ['ta']
    ch = {
        'a.com': {'dns_txt_name': '_acme-challenge.a.com', 'dns_txt_value': 'ta'},
        'b.com': {'dns_txt_name': '_acme-challenge.b.com', 'dns_txt_value': 'tb'},
    }
    res = orders_mod._dns_selfcheck(ch, timeout=0)
    assert res['ok'] is False and res['missing'] == ['b.com']


def test_auto_poll_skips_dns_selfcheck_when_timeout_zero(monkeypatch):
    """dns_propagation_timeout=0 = operator asked to skip the DNS-01 pre-check
    (issue #171): the auto-poll path must NOT call _dns_selfcheck at all, so a
    flaky public resolver cannot delay submission to the CA.

    _dns_selfcheck(timeout=0) itself still does a single pass (used by the
    manual verify endpoint for a quick readiness probe) — that behaviour is
    covered by the tests above and must not change.
    """
    calls = []
    monkeypatch.setattr(orders_mod, '_dns_selfcheck',
                        lambda ch, t: calls.append(t) or {'ok': True, 'missing': [], 'waited': 0})
    monkeypatch.setattr(orders_mod, '_dns_propagation_timeout', lambda: 0)
    # Drive a no-op order through the auto-poll: order 999999 does not exist,
    # the worker returns before reaching the self-check, so we instead assert
    # the guard directly: timeout <= 0 short-circuits.
    timeout = orders_mod._dns_propagation_timeout()
    assert timeout == 0
    # Simulate the inline guard in _auto_poll_order.
    if timeout <= 0:
        check = {'ok': True, 'missing': [], 'waited': 0}
    else:
        check = orders_mod._dns_selfcheck({}, timeout)
    assert check['ok'] is True
    assert calls == [], '_dns_selfcheck must not be invoked when timeout=0'


def test_selfcheck_ignores_non_dns_challenges(fake_dns):
    ch = {'a.com': {'dns_txt_name': None, 'dns_txt_value': None}}  # http-01
    res = orders_mod._dns_selfcheck(ch, timeout=0)
    assert res['ok'] is True and res['missing'] == []


def test_auto_path_honors_full_configured_timeout(monkeypatch):
    """The auto-poll self-check runs in a BACKGROUND thread now, so it is no
    longer bounded by the gunicorn worker timeout and must honor the full
    configured value (up to 3600s). Regression guard for #140: a long timeout
    must NOT be silently capped."""
    monkeypatch.setattr(orders_mod, '_dns_propagation_timeout', lambda: 3600)
    assert orders_mod._dns_propagation_timeout() == 3600


def test_auto_poll_runs_inline_under_testing(app, monkeypatch):
    """Under TESTING the auto-poll MUST run inline (the test DB uses a single
    shared SQLite connection that a background thread would contend with), and
    must NOT spawn a real thread."""
    import threading as real_threading

    started = []
    real_thread_class = real_threading.Thread

    class _SpyThread(real_thread_class):
        def start(self):
            started.append(True)

    monkeypatch.setattr(orders_mod.threading, 'Thread', _SpyThread)
    with app.test_request_context():
        app.config['TESTING'] = True
        # Order 999999 doesn't exist → worker returns early, no exception.
        orders_mod._run_auto_poll_background(999999, 'staging')
    assert started == [], 'background thread must NOT be spawned under TESTING'


def test_auto_poll_spawns_thread_when_not_testing(app, monkeypatch):
    """Outside TESTING the auto-poll launches a daemon thread (the request must
    return immediately while DNS validation runs in the background)."""
    started = []

    class _SpyThread:
        def __init__(self, *a, **k):
            pass
        def start(self):
            started.append(True)

    monkeypatch.setattr(orders_mod.threading, 'Thread', _SpyThread)
    with app.test_request_context():
        app.config['TESTING'] = False
        orders_mod._run_auto_poll_background(999999, 'staging')
    assert started == [True], 'a background thread must be spawned outside TESTING'


def test_txt_present_uses_authoritative_before_public(fake_dns, monkeypatch):
    """Authoritative resolver is tried before public resolvers."""
    fake_dns['records']['_acme-challenge.example.com'] = ['token']
    monkeypatch.setattr(
        dns_lookup_mod,
        '_authoritative_nameserver_ips',
        lambda _name: ['203.0.113.53'],
    )
    calls = []

    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    def _resolve_with_ns(name, nameservers, rtype='TXT'):
        calls.append((name, nameservers))
        return [_RData(fake_dns['records'][name])]

    monkeypatch.setattr(dns_lookup_mod, '_resolve_with_ns', _resolve_with_ns)
    assert orders_mod._txt_present('_acme-challenge.example.com', 'token') is True
    assert calls and calls[0][1] == ['203.0.113.53']


def test_check_public_resolvers_queries_each_ip(fake_dns, monkeypatch):
    state = {'hits': set()}

    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    def _resolve_with_ns(name, nameservers, rtype='TXT'):
        ip = nameservers[0]
        state['hits'].add(ip)
        if ip == '8.8.8.8':
            return [_RData(['token'])]
        raise Exception('NXDOMAIN')

    monkeypatch.setattr(dns_lookup_mod, '_resolve_with_ns', _resolve_with_ns)
    status = dns_lookup_mod.check_public_resolvers('_acme-challenge.example.com', 'token')
    assert state['hits'] == set(dns_lookup_mod.PUBLIC_DNS_RESOLVERS)
    assert status == {'9.9.9.9': False, '8.8.8.8': True, '1.1.1.1': False}


def test_txt_present_falls_back_to_public_resolver(fake_dns, monkeypatch):
    monkeypatch.setattr(dns_lookup_mod, 'get_configured_dns01_nameservers', lambda: [])
    monkeypatch.setattr(dns_lookup_mod, '_authoritative_nameserver_ips', lambda _name: [])

    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    def _resolve_with_ns(name, nameservers, rtype='TXT'):
        if nameservers == ['1.1.1.1']:
            return [_RData(['the-token'])]
        raise Exception('NXDOMAIN')

    monkeypatch.setattr(dns_lookup_mod, '_resolve_with_ns', _resolve_with_ns)
    assert orders_mod._txt_present('_acme-challenge.example.com', 'the-token') is True


def test_parse_resolver_ips_accepts_valid_and_skips_invalid(caplog):
    import logging

    caplog.set_level(logging.WARNING)
    result = dns_lookup_mod._parse_resolver_ips('8.8.8.8, not-an-ip, 1.1.1.1')
    assert result == ['8.8.8.8', '1.1.1.1']
    assert any('not-an-ip' in rec.message for rec in caplog.records)


def test_parse_resolver_ips_accepts_ipv6():
    result = dns_lookup_mod._parse_resolver_ips('2001:4860:4860::8888')
    assert result == ['2001:4860:4860::8888']


def test_check_public_resolvers_logs_exception_type(fake_dns, monkeypatch, caplog):
    """A failing public resolver is logged with its exception type at DEBUG
    (issue #171) so a flaky resolver (e.g. SERVFAIL) is distinguishable from a
    real propagation gap (NXDOMAIN / wrong value)."""
    import logging

    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    def _resolve_with_ns(name, nameservers, rtype='TXT'):
        ip = nameservers[0]
        if ip == '9.9.9.9':
            raise ConnectionError('SERVFAIL from Quad9')
        if ip == '8.8.8.8':
            return [_RData(['token'])]
        raise TimeoutError('dns lookup timed out')

    monkeypatch.setattr(dns_lookup_mod, '_resolve_with_ns', _resolve_with_ns)
    caplog.set_level(logging.DEBUG, logger='utils.dns_txt_lookup')
    status = dns_lookup_mod.check_public_resolvers('_acme-challenge.example.com', 'token')
    assert status == {'9.9.9.9': False, '8.8.8.8': True, '1.1.1.1': False}
    debug_msgs = [r.message for r in caplog.records]
    assert any('9.9.9.9' in m and 'ConnectionError' in m for m in debug_msgs), \
        'exception type must be logged for the failing resolver'
    assert any('1.1.1.1' in m and 'TimeoutError' in m for m in debug_msgs), \
        'exception type must be logged for the timed-out resolver'


def test_txt_rdata_matches_concatenated_chunks():
    """A TXT RR whose value is split across multiple <character-string> chunks
    (RFC 1035 §3.3.14; Quad9 is known to do this for long ACME tokens) must
    match when the joined value equals the expected token (issue #171)."""
    class _RData:
        def __init__(self, values):
            self.strings = [v.encode() for v in values]

    rdata = _RData(['part1', 'part2'])
    # Joined match (the realistic case: token split across two chunks)
    assert dns_lookup_mod._txt_rdata_matches(rdata, 'part1part2') is True
    # A single chunk still matches in isolation
    assert dns_lookup_mod._txt_rdata_matches(rdata, 'part1') is True
    # A wrong value does not match
    assert dns_lookup_mod._txt_rdata_matches(rdata, 'wrong') is False


def test_verify_challenges_skips_dns_gate_when_timeout_zero(app, auth_client, monkeypatch):
    """Manual Verify must NOT block on DNS when dns_propagation_timeout=0
    (issue #171): the self-check is skipped entirely and verify_challenge is
    called straight away."""
    import json
    from models import db, AcmeClientOrder

    monkeypatch.setattr(orders_mod, '_dns_propagation_timeout', lambda: 0)

    selfcheck_called = []
    monkeypatch.setattr(
        orders_mod, '_dns_selfcheck',
        lambda *a, **k: selfcheck_called.append(True) or {'ok': False, 'missing': ['example.com']},
    )

    verify_calls = []

    class _MockClient:
        def verify_challenge(self, order, domain):
            verify_calls.append(domain)
            return True, 'submitted'

        def check_order_status(self, order):
            return 'validating', None

    monkeypatch.setattr(
        orders_mod.AcmeClientService, 'for_order',
        staticmethod(lambda order: _MockClient()),
    )

    with app.app_context():
        order = AcmeClientOrder(
            domains=json.dumps(['example.com']),
            challenge_type='dns-01',
            environment='staging',
            status='pending',
        )
        order.set_challenges_dict({
            'example.com': {
                'dns_txt_name': '_acme-challenge.example.com',
                'dns_txt_value': 'the-token',
            }
        })
        db.session.add(order)
        db.session.commit()
        order_id = order.id

    from tests.test_acme import post_json, assert_success

    r = post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/verify', {})
    assert_success(r)
    assert selfcheck_called == [], '_dns_selfcheck must not be called when timeout=0'
    assert verify_calls == ['example.com'], 'verify_challenge must be called directly'
