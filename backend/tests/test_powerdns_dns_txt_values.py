"""PowerDNS: REPLACE rewrites the whole rrset, so several TXT values under one name must be sent together."""
import pytest

from services.acme.dns_providers import powerdns
from services.acme.dns_providers.powerdns import PowerDnsDnsProvider

NAME = '_acme-challenge.example.com.'


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = '' if body is None else 'x'
        self._body = body

    def json(self):
        return self._body


class FakePowerDns:
    """Zone API per the docs: GET filters by rrset_name/type, PATCH REPLACE swaps the whole rrset."""

    def __init__(self):
        self.rrsets = {}
        self.calls = []
        self.get_status = None

    def __call__(self, method, url, **kw):
        path = url.split('/api/v1/servers/localhost', 1)[1]
        self.calls.append((method, path, kw.get('json')))
        if method == 'GET' and path == '/zones':
            return _Response(200, [{'name': 'example.com.'}])
        if method == 'GET' and path.startswith('/zones/example.com.?'):
            if self.get_status:
                return _Response(self.get_status, {'error': 'backend down'})
            return _Response(200, {'rrsets': list(self.rrsets.values())})
        if method == 'PATCH' and path == '/zones/example.com.':
            for rr in kw['json']['rrsets']:
                assert rr['changetype'] == 'REPLACE'
                contents = [r['content'] for r in rr['records']]
                if len(contents) != len(set(contents)):
                    return _Response(422, {'error': f"Duplicate record in RRset {rr['name']} IN TXT"})
                self.rrsets[rr['name']] = {'name': rr['name'], 'type': 'TXT', 'ttl': rr['ttl'],
                                           'records': list(rr['records'])}
            return _Response(204)
        return _Response(404, {'error': 'not found'})

    def contents(self):
        return [r['content'] for r in self.rrsets[NAME]['records']]


@pytest.fixture
def api(monkeypatch):
    fake = FakePowerDns()
    monkeypatch.setattr(powerdns, 'safe_request', lambda m, u, **kw: fake(m, u, **kw))
    return fake


def _create(value):
    return PowerDnsDnsProvider({'server_url': 'http://pdns:8081', 'api_key': 'k'}).create_txt_record(
        'example.com', '_acme-challenge.example.com', value)


def test_first_value_creates_the_rrset(api):
    ok, msg = _create('tok1')
    assert ok, msg
    assert api.contents() == ['"tok1"']
    assert api.rrsets[NAME]['ttl'] == 300


def test_second_value_keeps_the_first(api):
    assert _create('apex')[0]
    ok, msg = _create('wildcard')
    assert ok, msg
    assert api.contents() == ['"apex"', '"wildcard"']


def test_existing_ttl_is_kept(api):
    api.rrsets[NAME] = {'name': NAME, 'type': 'TXT', 'ttl': 60,
                        'records': [{'content': '"old"', 'disabled': False}]}
    assert _create('new')[0]
    assert api.rrsets[NAME]['ttl'] == 60


def test_value_already_present_is_not_written_again(api):
    assert _create('tok1')[0]
    ok, msg = _create('tok1')
    assert ok, msg
    assert api.contents() == ['"tok1"']
    assert len([c for c in api.calls if c[0] == 'PATCH']) == 1


def test_unreadable_rrset_is_not_overwritten(api):
    api.rrsets[NAME] = {'name': NAME, 'type': 'TXT', 'ttl': 300,
                        'records': [{'content': '"other"', 'disabled': False}]}
    api.get_status = 500
    ok, msg = _create('tok1')
    assert not ok and 'backend down' in msg
    assert not [c for c in api.calls if c[0] == 'PATCH']
    assert api.contents() == ['"other"']


def test_disabled_copy_of_the_value_is_re_enabled_not_duplicated(api):
    api.rrsets[NAME] = {'name': NAME, 'type': 'TXT', 'ttl': 300,
                        'records': [{'content': '"tok1"', 'disabled': True},
                                    {'content': '"other"', 'disabled': False}]}
    ok, msg = _create('tok1')
    assert ok, msg
    assert api.rrsets[NAME]['records'] == [{'content': '"tok1"', 'disabled': False},
                                           {'content': '"other"', 'disabled': False}]
