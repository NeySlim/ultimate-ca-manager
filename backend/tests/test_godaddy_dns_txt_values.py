"""GoDaddy: PUT on /records/TXT/{name} replaces every value of the name, so values must be merged."""
import json
import re

import pytest
import requests

from services.acme.dns_providers.godaddy import GoDaddyDnsProvider

NAME = '_acme-challenge.example.com'


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


class FakeGoDaddy:
    """Routes of the v1 API: GET, PUT and DELETE on /domains/{d}/records/{type}/{name}; PATCH
    exists only on /domains/{d}/records. PUT refuses a TTL below 600, DELETE of nothing is 404."""

    def __init__(self):
        self.records = {}
        self.calls = []
        self.get_status = None

    def __call__(self, method, url, headers=None, json=None, timeout=None, params=None):
        path = url.removeprefix(GoDaddyDnsProvider.BASE_URL)
        self.calls.append((method, path, json))
        if method == 'GET' and path == '/domains':
            return _Response(200, [{'domain': 'example.com'}])
        m = re.fullmatch(r'/domains/example\.com/records/TXT/([^/]+)', path)
        if not m:
            return _Response(404, {'code': 'NOT_FOUND', 'message': 'Not found'})
        name = m.group(1)
        if method == 'GET':
            if self.get_status:
                return _Response(self.get_status, {'code': 'ERROR', 'message': 'Internal error'})
            return _Response(200, [{'data': r['data'], 'name': name, 'ttl': r['ttl'], 'type': 'TXT'}
                                   for r in self.records.get(name, [])])
        if method == 'PUT':
            if not json or any(r['ttl'] < 600 for r in json):
                return _Response(422, {'code': 'INVALID_BODY', 'message': 'Request body invalid'})
            self.records[name] = [{'data': r['data'], 'ttl': r['ttl']} for r in json]
            return _Response(200)
        if method == 'DELETE':
            if name not in self.records:
                return _Response(404, {'code': 'NOT_FOUND', 'message': 'Record not found'})
            del self.records[name]
            return _Response(204)
        return _Response(404, {'code': 'NOT_FOUND', 'message': 'Not found'})


@pytest.fixture
def api(monkeypatch):
    fake = FakeGoDaddy()
    monkeypatch.setattr(requests, 'request', fake)
    return fake


def _provider():
    return GoDaddyDnsProvider({'api_key': 'k', 'api_secret': 's'})


def test_first_value_is_written_with_the_minimum_ttl(api):
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1', ttl=300)
    assert ok, msg
    assert api.records['_acme-challenge'] == [{'data': 'tok1', 'ttl': 600}]


def test_apex_and_wildcard_both_keep_their_value(api):
    provider = _provider()
    for token in ('apex-token', 'wildcard-token'):
        ok, msg = provider.create_txt_record('example.com', NAME, token)
        assert ok, msg
    assert [r['data'] for r in api.records['_acme-challenge']] == ['apex-token', 'wildcard-token']


def test_existing_values_keep_their_ttl(api):
    api.records['_acme-challenge'] = [{'data': 'stale', 'ttl': 3600}]
    ok, msg = _provider().create_txt_record('example.com', NAME, 'fresh')
    assert ok, msg
    assert api.records['_acme-challenge'] == [{'data': 'stale', 'ttl': 3600}, {'data': 'fresh', 'ttl': 600}]


def test_value_already_present_is_not_sent_again(api):
    api.records['_acme-challenge'] = [{'data': 'tok1', 'ttl': 600}]
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert ok, msg
    assert not [c for c in api.calls if c[0] == 'PUT']


def test_unreadable_name_is_not_overwritten(api):
    api.records['_acme-challenge'] = [{'data': 'other', 'ttl': 600}]
    api.get_status = 500
    ok, msg = _provider().create_txt_record('example.com', NAME, 'tok1')
    assert not ok and 'Internal error' in msg
    assert not [c for c in api.calls if c[0] == 'PUT']
    assert api.records['_acme-challenge'] == [{'data': 'other', 'ttl': 600}]


def test_cleanup_deletes_the_name_and_succeeds_twice(api):
    provider = _provider()
    for token in ('a', 'b'):
        provider.create_txt_record('example.com', NAME, token)
    for _ in range(2):
        ok, msg = provider.delete_txt_record('example.com', NAME)
        assert ok, msg
    assert api.records == {}
    assert ('DELETE', '/domains/example.com/records/TXT/_acme-challenge', None) in api.calls
