"""DNS-01 self-check before submitting to the CA (#140)."""
import sys
import types
import pytest

from api.v2.acme_client import orders as orders_mod


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


def test_selfcheck_ignores_non_dns_challenges(fake_dns):
    ch = {'a.com': {'dns_txt_name': None, 'dns_txt_value': None}}  # http-01
    res = orders_mod._dns_selfcheck(ch, timeout=0)
    assert res['ok'] is True and res['missing'] == []
