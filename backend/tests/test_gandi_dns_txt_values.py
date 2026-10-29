"""Gandi LiveDNS: PUT replaces the whole RRset, so TXT values of one name must be merged."""
import json
import re

import pytest
import requests

from services.acme.dns_providers.gandi import GandiDnsProvider

NAME = '_acme-challenge.example.com'


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


class FakeGandi:
    """Routes from the LiveDNS spec: GET on a missing name/type pair answers 404, PUT 201, DELETE 204."""

    def __init__(self):
        self.rrsets = {}
        self.calls = []
        self.get_status = None

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path = url.removeprefix(GandiDnsProvider.BASE_URL)
        self.calls.append((method, path, json))
        if method == 'GET' and path == '/domains/example.com':
            return _Response(200, {'fqdn': 'example.com'})
        m = re.fullmatch(r'/domains/example\.com/records/([^/]+)/TXT', path)
        if not m:
            return _Response(404, {'message': 'not found'})
        name = m.group(1)
        if method == 'GET':
            if self.get_status:
                return _Response(self.get_status, {'message': 'internal error'})
            if name not in self.rrsets:
                return _Response(404, {'cause': 'Not Found', 'message': 'record not found'})
            return _Response(200, {'rrset_name': name, 'rrset_type': 'TXT', **self.rrsets[name]})
        if method == 'PUT':
            self.rrsets[name] = {'rrset_values': list(json['rrset_values']), 'rrset_ttl': json['rrset_ttl']}
            return _Response(201, {'message': 'DNS Record Created'})
        if method == 'DELETE':
            self.rrsets.pop(name, None)
            return _Response(204)
        return _Response(405, {'message': 'method not allowed'})


@pytest.fixture
def api(monkeypatch):
    fake = FakeGandi()
    monkeypatch.setattr(requests, 'request', fake)
    return fake


def _provider():
    return GandiDnsProvider({'api_key': 'k'})


def test_first_value_creates_the_rrset(api):
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert api.rrsets['_acme-challenge'] == {'rrset_values': ['tok1'], 'rrset_ttl': 300}


def test_apex_and_wildcard_both_keep_their_value(api):
    provider = _provider()
    for token in ('apex-token', 'wildcard-token'):
        ok, msg = provider.create_txt_record('example.com', NAME, token)
        assert ok, msg
    assert api.rrsets['_acme-challenge']['rrset_values'] == ['apex-token', 'wildcard-token']


def test_existing_rrset_keeps_its_own_ttl(api):
    api.rrsets['_acme-challenge'] = {'rrset_values': ['stale'], 'rrset_ttl': 900}
    ok, msg = _provider().create_txt_record('example.com', NAME, 'fresh')
    assert ok, msg
    assert api.rrsets['_acme-challenge'] == {'rrset_values': ['stale', 'fresh'], 'rrset_ttl': 900}


def test_value_already_present_is_not_sent_again(api):
    api.rrsets['_acme-challenge'] = {'rrset_values': ['tok1'], 'rrset_ttl': 300}
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert api.rrsets['_acme-challenge']['rrset_values'] == ['tok1']
    assert not [c for c in api.calls if c[0] == 'PUT']


def test_unreadable_rrset_is_not_overwritten(api):
    api.rrsets['_acme-challenge'] = {'rrset_values': ['other'], 'rrset_ttl': 300}
    api.get_status = 500
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert not ok and 'internal error' in msg
    assert not [c for c in api.calls if c[0] == 'PUT']
    assert api.rrsets['_acme-challenge']['rrset_values'] == ['other']


def test_cleanup_called_once_per_challenge_succeeds_twice(api):
    provider = _provider()
    for token in ('a', 'b'):
        provider.create_txt_record('example.com', NAME, token)
    for _ in range(2):
        ok, msg = provider.delete_txt_record('example.com', NAME)
        assert ok, msg
    assert api.rrsets == {}


def test_subdomain_and_its_wildcard_on_one_provider(api):
    provider = _provider()
    for token in ('apex-token', 'wildcard-token'):
        ok, msg = provider.create_txt_record('www.example.com', '_acme-challenge.www.example.com', token)
        assert ok, msg
    assert api.rrsets['_acme-challenge.www']['rrset_values'] == ['apex-token', 'wildcard-token']


def test_value_stored_with_quotes_is_recognised(api):
    api.rrsets['_acme-challenge'] = {'rrset_values': ['"tok1"'], 'rrset_ttl': 300}
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert not [c for c in api.calls if c[0] == 'PUT']
