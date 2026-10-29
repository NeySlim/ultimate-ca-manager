"""NS1: PUT only creates, POST replaces the answers, so a second TXT value needs the union via POST."""
import re

import pytest
import requests

from services.acme.dns_providers.ns1 import Ns1DnsProvider


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = '' if body is None else 'x'
        self._body = body

    def json(self):
        return self._body


class FakeNs1:
    def __init__(self):
        self.records = {}
        self.calls = []
        self.get_status = None

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path = url.removeprefix(Ns1DnsProvider.BASE_URL)
        self.calls.append((method, path, json))
        if method == 'GET' and path == '/zones':
            return _Response(200, [{'zone': 'example.com'}])
        m = re.fullmatch(r'/zones/example.com/([^/]+)/TXT', path)
        if not m:
            return _Response(404, {'message': 'zone not found'})
        name = m.group(1)
        if method == 'GET':
            if self.get_status:
                return _Response(self.get_status, {'message': 'internal error'})
            if name not in self.records:
                return _Response(404, {'message': 'record not found'})
            return _Response(200, self.records[name])
        if method == 'PUT':
            if name in self.records:
                return _Response(400, {'message': 'record already exists'})
            self.records[name] = {'ttl': json['ttl'], 'answers': list(json['answers'])}
            return _Response(200, self.records[name])
        if method == 'POST':
            if name not in self.records:
                return _Response(404, {'message': 'record not found'})
            self.records[name] = {'ttl': json['ttl'], 'answers': list(json['answers'])}
            return _Response(200, self.records[name])
        return _Response(405, {'message': 'method not allowed'})

    def values(self, name='_acme-challenge.example.com'):
        return [a['answer'][0] for a in self.records[name]['answers']]


@pytest.fixture
def api(monkeypatch):
    fake = FakeNs1()
    monkeypatch.setattr(requests, 'request', fake)
    return fake


def _create(value):
    return Ns1DnsProvider({'api_key': 'k'}).create_txt_record('example.com', '_acme-challenge.example.com', value)


def test_first_value_creates_the_record(api):
    ok, msg = _create('tok1')
    assert ok, msg
    assert api.values() == ['tok1']
    assert api.records['_acme-challenge.example.com']['ttl'] == 300


def test_second_value_keeps_the_first(api):
    assert _create('apex')[0]
    ok, msg = _create('wildcard')
    assert ok, msg
    assert api.values() == ['apex', 'wildcard']


def test_existing_ttl_is_kept(api):
    api.records['_acme-challenge.example.com'] = {'ttl': 60, 'answers': [{'answer': ['old']}]}
    assert _create('new')[0]
    assert api.records['_acme-challenge.example.com']['ttl'] == 60


def test_value_already_present_is_not_written_again(api):
    assert _create('tok1')[0]
    ok, msg = _create('tok1')
    assert ok, msg
    assert api.values() == ['tok1']
    assert [c[0] for c in api.calls if c[0] in ('PUT', 'POST')] == ['PUT']


def test_unreadable_record_is_not_overwritten(api):
    api.records['_acme-challenge.example.com'] = {'ttl': 300, 'answers': [{'answer': ['other']}]}
    api.get_status = 500
    ok, msg = _create('tok1')
    assert not ok and 'internal error' in msg
    assert not [c for c in api.calls if c[0] in ('PUT', 'POST')]
    assert api.values() == ['other']
