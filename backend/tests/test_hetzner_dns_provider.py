"""Hetzner Cloud DNS: TXT values are added with actions/add_records, the API has no PATCH on an RRset."""
import json
import re

import pytest
import requests

from services.acme.dns_providers.hetzner import HetznerDnsProvider

ZONE = {'id': 7, 'name': 'example.com'}


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


class FakeHetzner:
    """Routes from the Cloud API spec only: an unknown path answers 404, an unknown method 405."""

    def __init__(self, rrsets=None):
        self.rrsets = rrsets or {}
        self.calls = []
        self.get_status = None
        self.action_status = 'running'

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path = url.removeprefix(HetznerDnsProvider.BASE_URL)
        self.calls.append((method, path, json))
        if method == 'GET' and path == '/zones':
            return _Response(200, {'zones': [ZONE]})
        if method == 'POST' and path == '/zones/7/rrsets':
            if json['name'] in self.rrsets:
                return _Response(409, {'error': {'message': 'rrset already exists'}})
            self.rrsets[json['name']] = {'ttl': json['ttl'], 'records': list(json['records'])}
            return _Response(201, {'rrset': self.rrsets[json['name']]})
        m = re.fullmatch(r'/zones/7/rrsets/([^/]+)/TXT(/actions/add_records)?', path)
        if not m:
            return _Response(404, {'error': {'message': 'not found'}})
        name, action = m.groups()
        if method == 'GET' and not action:
            if self.get_status:
                return _Response(self.get_status, {'error': {'message': 'rate limited'}})
            if name not in self.rrsets:
                return _Response(404, {'error': {'message': 'rrset not found'}})
            return _Response(200, {'rrset': self.rrsets[name]})
        if method == 'POST' and action:
            rrset = self.rrsets.setdefault(name, {'ttl': json.get('ttl'), 'records': []})
            if 'ttl' in json and rrset['ttl'] != json['ttl']:
                return _Response(422, {'error': {'message': 'ttl mismatch'}})
            values = [r['value'] for r in rrset['records']]
            for record in json['records']:
                if record['value'] in values:
                    return _Response(422, {'error': {'message': 'duplicate record'}})
                rrset['records'].append(record)
            return _Response(201, {'action': {'status': self.action_status, 'error': {'message': 'zone locked'}}})
        return _Response(405, {'error': {'message': 'method not allowed'}})


@pytest.fixture
def api(monkeypatch):
    fake = FakeHetzner()
    monkeypatch.setattr(requests, 'request', fake)
    return fake


def _provider():
    return HetznerDnsProvider({'api_token': 't'})


def _values(api, name='_acme-challenge'):
    return [r['value'] for r in api.rrsets[name]['records']]


def test_first_value_creates_the_rrset_with_its_ttl(api):
    ok, msg = _provider().create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    assert ok, msg
    assert _values(api) == ['"tok1"']
    assert api.rrsets['_acme-challenge']['ttl'] == 300


def test_apex_and_wildcard_both_get_their_value(api):
    provider = _provider()
    for token in ('apex-token', 'wildcard-token'):
        ok, msg = provider.create_txt_record('example.com', '_acme-challenge.example.com', token)
        assert ok, msg
    assert _values(api) == ['"apex-token"', '"wildcard-token"']
    assert not [c for c in api.calls if c[0] not in ('GET', 'POST')]


def test_existing_rrset_keeps_its_own_ttl(api):
    api.rrsets['_acme-challenge'] = {'ttl': 60, 'records': [{'value': '"stale"'}]}
    ok, msg = _provider().create_txt_record('example.com', '_acme-challenge.example.com', 'fresh')
    assert ok, msg
    assert _values(api) == ['"stale"', '"fresh"']


def test_value_already_present_is_not_sent_again(api):
    api.rrsets['_acme-challenge'] = {'ttl': 300, 'records': [{'value': '"tok1"'}]}
    ok, msg = _provider().create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    assert ok, msg
    assert _values(api) == ['"tok1"']
    assert not [c for c in api.calls if c[0] == 'POST']


def test_unreadable_rrset_is_not_overwritten_with_a_guessed_ttl(api):
    api.rrsets['_acme-challenge'] = {'ttl': 60, 'records': [{'value': '"other"'}]}
    api.get_status = 429
    ok, msg = _provider().create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    assert not ok and 'rate limited' in msg
    assert not [c for c in api.calls if c[0] == 'POST']


def test_failed_action_is_reported(api):
    api.action_status = 'error'
    ok, msg = _provider().create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    assert not ok and 'zone locked' in msg
