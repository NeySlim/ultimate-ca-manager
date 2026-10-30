"""deSEC: an RRset holds every TXT value of a name, so values must be merged, not replaced."""
import json
import re

import pytest
import requests

from services.acme.dns_providers.desec import DesecDnsProvider

NAME = '_acme-challenge.example.com'


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


class FakeDesec:
    """Routes from the deSEC docs: single-RRset GET is an object (404 if absent), POST on an
    existing RRset is 400, PATCH 200, DELETE 204 even when absent. TXT values keep their quotes,
    a TTL below the domain's server-set minimum_ttl (3600 by default) is refused."""

    def __init__(self):
        self.rrsets = {}
        self.calls = []
        self.get_status = None
        self.minimum_ttl = 3600

    def __call__(self, method, url, headers=None, json=None, timeout=None, params=None):
        path = url.removeprefix(DesecDnsProvider.BASE_URL)
        self.calls.append((method, path, json))
        if method == 'GET' and path == '/domains/':
            return _Response(200, [{'name': 'example.com', 'minimum_ttl': self.minimum_ttl}])
        if method == 'POST' and path == '/domains/example.com/rrsets/':
            if json['subname'] in self.rrsets:
                return _Response(400, {'non_field_errors': ['Another RRset with the same subdomain and type exists']})
            if json['ttl'] < self.minimum_ttl:
                return _Response(400, {'ttl': [f'Ensure this value is greater than or equal to {self.minimum_ttl}.']})
            if not all(r.startswith('"') and r.endswith('"') for r in json['records']):
                return _Response(400, {'records': ['Invalid TXT value']})
            self.rrsets[json['subname']] = {'ttl': json['ttl'], 'records': list(json['records'])}
            return _Response(201, {'subname': json['subname'], 'type': 'TXT', **self.rrsets[json['subname']]})
        m = re.fullmatch(r'/domains/example\.com/rrsets/([^/]+)/TXT/', path)
        if not m:
            return _Response(404, {'detail': 'Not found.'})
        sub = m.group(1)
        if method == 'GET':
            if self.get_status:
                return _Response(self.get_status, {'detail': 'Internal error.'})
            if sub not in self.rrsets:
                return _Response(404, {'detail': 'Not found.'})
            return _Response(200, {'subname': sub, 'type': 'TXT', **self.rrsets[sub]})
        if method == 'PATCH':
            if sub not in self.rrsets:
                return _Response(404, {'detail': 'Not found.'})
            if json.get('ttl', self.minimum_ttl) < self.minimum_ttl:
                return _Response(400, {'ttl': [f'Ensure this value is greater than or equal to {self.minimum_ttl}.']})
            self.rrsets[sub].update(json)
            return _Response(200, {'subname': sub, 'type': 'TXT', **self.rrsets[sub]})
        if method == 'DELETE':
            self.rrsets.pop(sub, None)
            return _Response(204)
        return _Response(405, {'detail': 'Method not allowed.'})


@pytest.fixture
def api(monkeypatch):
    fake = FakeDesec()
    monkeypatch.setattr(requests, 'request', fake)
    return fake


def _provider():
    return DesecDnsProvider({'api_token': 't'})


def test_first_value_creates_the_rrset_with_the_domain_minimum_ttl(api):
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert api.rrsets['_acme-challenge'] == {'ttl': 3600, 'records': ['"tok1"']}


def test_a_lowered_minimum_ttl_is_used_as_the_floor(api):
    api.minimum_ttl = 60
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1', ttl=10)
    assert ok, msg
    assert api.rrsets['_acme-challenge'] == {'ttl': 60, 'records': ['"tok1"']}


def test_apex_and_wildcard_both_keep_their_value(api):
    provider = _provider()
    for token in ('apex-token', 'wildcard-token'):
        ok, msg = provider.create_txt_record('example.com', NAME, token)
        assert ok, msg
    assert api.rrsets['_acme-challenge']['records'] == ['"apex-token"', '"wildcard-token"']


def test_existing_rrset_keeps_its_own_ttl(api):
    api.rrsets['_acme-challenge'] = {'ttl': 3600, 'records': ['"stale"']}
    ok, msg = _provider().create_txt_record('example.com', NAME, 'fresh')
    assert ok, msg
    assert api.rrsets['_acme-challenge'] == {'ttl': 3600, 'records': ['"stale"', '"fresh"']}


def test_value_already_present_is_not_sent_again(api):
    api.rrsets['_acme-challenge'] = {'ttl': 300, 'records': ['"tok1"']}
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert api.rrsets['_acme-challenge']['records'] == ['"tok1"']
    assert not [c for c in api.calls if c[0] in ('PATCH', 'POST')]


def test_unreadable_rrset_is_not_overwritten(api):
    api.rrsets['_acme-challenge'] = {'ttl': 300, 'records': ['"other"']}
    api.get_status = 500
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert not ok and 'Internal error' in msg
    assert not [c for c in api.calls if c[0] in ('PATCH', 'POST')]
    assert api.rrsets['_acme-challenge']['records'] == ['"other"']


def test_cleanup_called_once_per_challenge_succeeds_twice(api):
    provider = _provider()
    for token in ('a', 'b'):
        provider.create_txt_record('example.com', NAME, token)
    for _ in range(2):
        ok, msg = provider.delete_txt_record('example.com', NAME)
        assert ok, msg
    assert api.rrsets == {}


def test_delete_answered_404_without_text_is_a_success(api, monkeypatch):
    real = api.__call__

    def gone(method, url, **kwargs):
        if method == 'DELETE':
            return _Response(404, {'detail': 'Gone.'})
        return real(method, url, **kwargs)

    monkeypatch.setattr(requests, 'request', gone)
    ok, msg = _provider().delete_txt_record('example.com', '_acme-challenge.example.com')
    assert ok, msg


def test_apex_rrset_is_deleted_through_the_at_placeholder(api):
    api.rrsets['@'] = {'ttl': 3600, 'records': ['"x"']}
    ok, msg = _provider().delete_txt_record('example.com', 'example.com')
    assert ok, msg
    assert ('DELETE', '/domains/example.com/rrsets/@/TXT/', None) in api.calls
    assert api.rrsets == {}
