"""DNS-01 resolver mode (#394): on a network that blocks outbound DNS, the
operator restricts TXT checks to the system resolver or to chosen resolvers."""
import json

import dns.resolver
import pytest

from models import db, SystemConfig
from services.acme import dns_selfcheck
from utils import dns_txt_lookup as lookup


class _RData:
    def __init__(self, value):
        self.strings = [value.encode()]


def _set(app, key, value):
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if row:
            row.value = value
        else:
            db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


@pytest.fixture
def resolver_config(app):
    def _configure(mode, servers=''):
        _set(app, 'acme.dns01_resolver_mode', mode)
        _set(app, 'acme.dns01_nameservers', servers)
    yield _configure
    _configure('auto', '')


@pytest.fixture
def queries(monkeypatch):
    """Record every DNS path; nothing answers unless a test says so."""
    seen = []

    def _with_ns(name, nameservers, rtype='TXT'):
        seen.append(('ns', tuple(nameservers)))
        raise dns.resolver.NoNameservers()

    def _system(name, rtype, lifetime=None):
        seen.append(('system',))
        return [_RData('tok')]

    def _configured(self, name, rtype='TXT', *a, **k):
        seen.append(('configured', tuple((n.address, n.port) for n in self.nameservers)))
        raise dns.resolver.NoNameservers()

    monkeypatch.setattr(lookup, '_resolve_with_ns', _with_ns)
    monkeypatch.setattr(lookup, '_authoritative_nameserver_ips', lambda name: seen.append(('authoritative',)) or ['192.0.2.53'])
    monkeypatch.setattr(dns.resolver, 'resolve', _system)
    monkeypatch.setattr(dns.resolver.Resolver, 'resolve', _configured)
    return seen


def test_parse_and_format_round_trip():
    raw = '10.0.0.1, 127.0.0.1:5353, [2001:db8::53]:5300, 2001:db8::1'
    entries = lookup.parse_resolver_entries(raw, strict=True)
    assert entries == [('10.0.0.1', 53), ('127.0.0.1', 5353), ('2001:db8::53', 5300), ('2001:db8::1', 53)]
    assert lookup.parse_resolver_entries(lookup.format_resolver_entries(entries)) == entries


@pytest.mark.parametrize('bad', ['dns.example.com', '10.0.0.1:0', '[::1', '1.2.3.4:99999', '[::1]x'])
def test_invalid_resolver_is_rejected_when_strict(bad):
    with pytest.raises(ValueError):
        lookup.parse_resolver_entries(bad, strict=True)


def test_system_mode_queries_only_the_system_resolver(app, resolver_config, queries):
    resolver_config('system', '10.0.0.53')
    with app.app_context():
        assert lookup.txt_record_present('_acme-challenge.example.com', 'tok') is True
    assert queries == [('system',)]


def test_custom_mode_never_falls_back(app, resolver_config, queries):
    resolver_config('custom', '10.0.0.53, 127.0.0.1:5353')
    with app.app_context():
        assert lookup.txt_record_present('_acme-challenge.example.com', 'tok') is False
    assert queries == [('configured', (('10.0.0.53', 53), ('127.0.0.1', 5353)))]


def test_auto_mode_keeps_the_full_chain(app, resolver_config, queries):
    resolver_config('auto', '10.0.0.53')
    with app.app_context():
        assert lookup.txt_record_present('_acme-challenge.example.com', 'tok', log_public=False) is True
    assert queries[0][0] == 'configured'
    assert ('authoritative',) in queries
    assert ('ns', ('9.9.9.9',)) in queries
    assert queries[-1] == ('system',)


def test_poll_queries_public_resolvers_once_per_tick(app, resolver_config, monkeypatch):
    resolver_config('auto')
    calls = []
    monkeypatch.setattr(lookup, 'resolve_txt_answers', lambda name: ([], 'recursive'))
    monkeypatch.setattr(lookup, 'check_public_resolvers', lambda name, expected: calls.append(name) or {})
    with app.app_context():
        dns_selfcheck.wait_for_challenges({'example.com': {'dns_txt_value': 'tok'}}, 0)
    assert len(calls) == 1


def test_acme_server_validation_honours_system_mode(app, resolver_config):
    from services.acme.acme_service import AcmeService
    resolver_config('system', '10.0.0.53')
    with app.app_context():
        assert AcmeService(base_url='http://localhost')._acme_dns01_resolver() is None
    resolver_config('auto', '10.0.0.53')
    with app.app_context():
        assert AcmeService(base_url='http://localhost')._acme_dns01_resolver() is not None


def _patch(client, data):
    return client.patch('/api/v2/acme/client/settings', data=json.dumps(data),
                        content_type='application/json')


def test_settings_store_a_normalized_list(app, auth_client, resolver_config):
    r = _patch(auth_client, {'dns01_resolver_mode': 'custom',
                             'dns01_nameservers': ' 10.0.0.53 ,[2001:db8::53]:5300,'})
    assert r.status_code == 200, r.get_data(as_text=True)
    data = auth_client.get('/api/v2/acme/client/settings').get_json()['data']
    assert data['dns01_resolver_mode'] == 'custom'
    assert data['dns01_nameservers'] == '10.0.0.53, [2001:db8::53]:5300'


@pytest.mark.parametrize('payload', [
    {'dns01_resolver_mode': 'public'},
    {'dns01_resolver_mode': 'custom', 'dns01_nameservers': ''},
    {'dns01_nameservers': 'dns.example.com'},
    {'dns01_nameservers': 53},
])
def test_settings_reject_invalid_input(app, auth_client, resolver_config, payload):
    resolver_config('auto', '10.0.0.53')
    assert _patch(auth_client, payload).status_code == 400
    with app.app_context():
        assert lookup.dns01_resolver_mode() == 'auto'
        assert lookup.configured_nameservers_raw() == '10.0.0.53'
