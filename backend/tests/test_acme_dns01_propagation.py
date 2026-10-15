"""DNS-01 propagation (#395): the CA validates from several vantage points, so
every authoritative nameserver must serve the TXT before UCM submits, and a
settle delay follows for anycast nodes UCM cannot see."""
import json

import dns.flags
import dns.message
import dns.name
import dns.rcode
import dns.resolver
import dns.rrset
import pytest

from api.v2.acme_client import orders as orders_mod
from models import db, SystemConfig, AcmeClientOrder
from services.acme import dns_selfcheck
from utils import dns_txt_lookup as lookup

NAME = '_acme-challenge.example.com'
TOKEN = 'the-token'
NS_IPS = {'ns1.example.net.': '192.0.2.1', 'ns2.example.net.': '192.0.2.2'}
TARGET = 'abcd.acme-dns.example.org'
ALIAS = 'alias.example.com'


class _RData:
    def __init__(self, value):
        self.strings = [value.encode()]
        self._value = value

    def __str__(self):
        return self._value


def _reply(rcode=dns.rcode.NOERROR, authoritative=True, cname=None, qname=NAME):
    reply = dns.message.make_response(dns.message.make_query(qname, 'TXT'))
    reply.set_rcode(rcode)
    if authoritative:
        reply.flags |= dns.flags.AA
    if cname:
        reply.answer.append(dns.rrset.from_text(qname, 300, 'IN', 'CNAME', cname + '.'))
    return reply


def _nxdomain(name=NAME):
    qname = dns.name.from_text(name)
    return dns.resolver.NXDOMAIN(qnames=[qname], responses={qname: _reply(dns.rcode.NXDOMAIN, qname=name)})


def _no_answer(**kwargs):
    return dns.resolver.NoAnswer(response=_reply(**kwargs))


class _Answers(list):
    def __init__(self, value, authoritative=True):
        super().__init__([_RData(value)])
        self.response = _reply(authoritative=authoritative)


def _set(app, key, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


def _clear(app, key):
    with app.app_context():
        SystemConfig.query.filter_by(key=key).delete()
        db.session.commit()


@pytest.fixture
def zone(app, monkeypatch):
    """Two authoritative NS; each server's TXT answer is set per test. Public
    and system resolvers already see the token, as they would via ns1."""
    _set(app, 'acme.dns01_resolver_mode', 'auto')
    _set(app, 'acme.dns01_nameservers', '')
    served = {}
    asked = []

    def _system(qname, rtype, lifetime=None):
        if rtype == 'NS':
            return [_RData(host) for host in NS_IPS]
        if rtype == 'A':
            return [_RData(NS_IPS[qname + '.'])]
        if rtype == 'AAAA':
            raise dns.resolver.NoAnswer()
        return [_RData(TOKEN)]

    def _query(self, qname, rtype='TXT', *a, **k):
        # dnspython stops at the first server that answers.
        ip = str(self.nameservers[0])
        asked.append((ip, qname, self.flags))
        if ip not in served:
            return [_RData(TOKEN)]  # a public resolver
        outcome = served[ip]
        if isinstance(outcome, dict):
            outcome = outcome[qname]
        if isinstance(outcome, Exception):
            raise outcome
        if isinstance(outcome, _Answers):
            return outcome
        return [_RData(outcome)]

    monkeypatch.setattr(dns.resolver, 'resolve', _system)
    monkeypatch.setattr(dns.resolver.Resolver, 'resolve', _query)
    served['asked'] = asked
    return served


def test_one_authoritative_lagging_keeps_the_record_pending(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = _nxdomain()
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is False


def test_stale_value_on_one_authoritative_keeps_the_record_pending(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = 'previous-token'
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is False


def test_every_authoritative_serving_the_value_confirms(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = TOKEN
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


def test_unreachable_authoritative_does_not_block(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = dns.resolver.LifetimeTimeout(timeout=10.0, errors=[])
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


def test_empty_authoritative_reply_keeps_the_record_pending(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = _no_answer()
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is False


def test_lame_nameserver_is_ignored(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = _no_answer(authoritative=False)
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


def test_cname_returned_by_the_nameservers_is_followed(app, zone):
    hop = _no_answer(cname=TARGET)
    zone['192.0.2.1'] = {NAME: hop, TARGET: TOKEN}
    zone['192.0.2.2'] = {NAME: hop, TARGET: _nxdomain(TARGET)}
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is False
        zone['192.0.2.2'] = {NAME: hop, TARGET: TOKEN}
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


def test_wildcard_cname_cached_by_the_recursive_is_not_followed(app, zone, monkeypatch):
    # The explicit TXT beats *.example.com CNAME at the authoritative servers.
    monkeypatch.setattr(dns.resolver, 'canonical_name', lambda qname: dns.name.from_text(TARGET))
    zone['192.0.2.1'] = {NAME: TOKEN, TARGET: _nxdomain(TARGET)}
    zone['192.0.2.2'] = {NAME: TOKEN, TARGET: _nxdomain(TARGET)}
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


def test_in_zone_cname_without_txt_keeps_the_record_pending(app, zone):
    zone['192.0.2.1'] = {NAME: TOKEN, ALIAS: _no_answer(qname=ALIAS)}
    zone['192.0.2.2'] = {NAME: _no_answer(cname=ALIAS), ALIAS: _no_answer(qname=ALIAS)}
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is False


def test_cname_loop_ends_in_the_public_fallback(app, zone):
    zone['192.0.2.1'] = {NAME: _no_answer(cname=TARGET), TARGET: _no_answer(qname=TARGET, cname=NAME)}
    zone['192.0.2.2'] = zone['192.0.2.1']
    with app.app_context():
        assert lookup.resolve_txt_answers(NAME, TOKEN)[1] == 'public:9.9.9.9'
    authoritative = [q for q in zone['asked'] if q[0] in NS_IPS.values()]
    assert len(authoritative) == 4  # NAME then TARGET on each server, no more


def test_cname_target_that_cannot_be_checked_does_not_confirm(app, zone):
    unreachable = dns.resolver.NoNameservers()
    zone['192.0.2.1'] = {NAME: TOKEN, TARGET: unreachable}
    zone['192.0.2.2'] = {NAME: _no_answer(cname=TARGET), TARGET: unreachable}
    with app.app_context():
        assert lookup.resolve_txt_answers(NAME, TOKEN)[1] == 'public:9.9.9.9'


def test_authoritative_queries_do_not_ask_for_recursion(app, zone):
    zone['192.0.2.1'] = TOKEN
    zone['192.0.2.2'] = TOKEN
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN) is True
    flags = {ip: f for ip, _, f in zone['asked']}
    assert flags['192.0.2.1'] == 0 and flags['192.0.2.2'] == 0
    assert flags['9.9.9.9'] is None  # public resolvers keep RD


def test_non_authoritative_positive_reply_does_not_confirm(app, zone):
    zone['192.0.2.1'] = _Answers(TOKEN, authoritative=False)
    zone['192.0.2.2'] = dns.resolver.LifetimeTimeout(timeout=4.0, errors=[])
    with app.app_context():
        assert lookup.resolve_txt_answers(NAME, TOKEN)[1] == 'public:9.9.9.9'


def test_no_authoritative_reachable_falls_back_to_public(app, zone):
    zone['192.0.2.1'] = dns.resolver.NoNameservers()
    zone['192.0.2.2'] = dns.resolver.NoNameservers()
    with app.app_context():
        assert lookup.txt_record_present(NAME, TOKEN, log_public=False) is True


@pytest.fixture
def sleeps(monkeypatch):
    calls = []
    monkeypatch.setattr(dns_selfcheck.time, 'sleep', calls.append)
    return calls


@pytest.fixture
def delay_setting(app):
    yield lambda value: _set(app, 'acme.client.dns_propagation_delay', value)
    _clear(app, 'acme.client.dns_propagation_delay')


def test_settle_delay_follows_confirmation(app, monkeypatch, sleeps, delay_setting):
    delay_setting('7')
    monkeypatch.setattr(dns_selfcheck, 'txt_record_present', lambda name, value: True)
    with app.app_context():
        res = dns_selfcheck.wait_for_challenges({'example.com': {'dns_txt_value': TOKEN}}, 30)
    assert res == {'ok': True, 'missing': [], 'waited': 7}
    assert sleeps == [7]


def test_default_settle_delay(app, monkeypatch, sleeps):
    _clear(app, 'acme.client.dns_propagation_delay')
    monkeypatch.setattr(dns_selfcheck, 'txt_record_present', lambda name, value: True)
    with app.app_context():
        dns_selfcheck.wait_for_challenges({'example.com': {'dns_txt_value': TOKEN}}, 30)
    assert sleeps == [dns_selfcheck.DNS_PROPAGATION_DEFAULT_DELAY]


def test_slow_lookups_count_against_the_timeout(app, monkeypatch, sleeps):
    clock = iter(range(0, 1000, 20))
    monkeypatch.setattr(dns_selfcheck.time, 'monotonic', lambda: next(clock))
    checks = []
    monkeypatch.setattr(dns_selfcheck, 'txt_record_present', lambda name, value: checks.append(name) and False)
    with app.app_context():
        res = dns_selfcheck.wait_for_challenges({'example.com': {'dns_txt_value': TOKEN}}, 30)
    assert res['ok'] is False
    assert len(checks) == 2  # 20 s then 40 s of lookups, not 7 polls of 5 s
    assert res['waited'] >= 30


def test_no_settle_delay_when_the_record_is_missing(app, monkeypatch, sleeps, delay_setting):
    delay_setting('7')
    monkeypatch.setattr(dns_selfcheck, 'txt_record_present', lambda name, value: False)
    with app.app_context():
        res = dns_selfcheck.wait_for_challenges({'example.com': {'dns_txt_value': TOKEN}}, 0)
    assert res['ok'] is False
    assert sleeps == []


def test_manual_verify_caps_the_settle_delay(app, auth_client, monkeypatch, delay_setting):
    from tests.test_acme import post_json, assert_success

    delay_setting('300')
    seen = []
    monkeypatch.setattr(orders_mod, '_dns_propagation_timeout', lambda: 120)
    monkeypatch.setattr(orders_mod, '_dns_selfcheck', lambda ch, timeout, delay=None:
                        seen.append((timeout, delay)) or {'ok': True, 'missing': [], 'waited': 0})

    class _Client:
        def verify_challenge(self, order, domain):
            return True, 'submitted'

        def check_order_status(self, order):
            return 'validating', None

    monkeypatch.setattr(orders_mod.AcmeClientService, 'for_order', staticmethod(lambda order: _Client()))
    with app.app_context():
        order = AcmeClientOrder(domains=json.dumps(['example.com']), challenge_type='dns-01',
                                environment='staging', status='pending')
        order.set_challenges_dict({'example.com': {'dns_txt_name': NAME, 'dns_txt_value': TOKEN}})
        db.session.add(order)
        db.session.commit()
        order_id = order.id

    assert_success(post_json(auth_client, f'/api/v2/acme/client/orders/{order_id}/verify', {}))
    cap = orders_mod._MANUAL_VERIFY_MAX_WAIT_SEC
    assert seen == [(cap, cap)]


def _patch(client, data):
    return client.patch('/api/v2/acme/client/settings', data=json.dumps(data),
                        content_type='application/json')


def test_settings_round_trip_the_delay(app, auth_client, delay_setting):
    _clear(app, 'acme.client.dns_propagation_delay')
    assert auth_client.get('/api/v2/acme/client/settings').get_json()['data']['dns_propagation_delay'] == 10
    assert _patch(auth_client, {'dns_propagation_delay': 45}).status_code == 200
    assert auth_client.get('/api/v2/acme/client/settings').get_json()['data']['dns_propagation_delay'] == 45


@pytest.mark.parametrize('bad', [-1, 301, 'soon', None, True, False])
def test_settings_reject_an_invalid_delay(app, auth_client, delay_setting, bad):
    delay_setting('20')
    assert _patch(auth_client, {'dns_propagation_delay': bad}).status_code == 400
    with app.app_context():
        assert dns_selfcheck.dns_propagation_delay() == 20


@pytest.mark.parametrize('bad', [True, False])
def test_settings_reject_a_boolean_timeout(app, auth_client, bad):
    assert _patch(auth_client, {'dns_propagation_timeout': bad}).status_code == 400
