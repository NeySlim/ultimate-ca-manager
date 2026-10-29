"""Azure DNS: PUT replaces the whole TXT record set, so create_txt_record must merge the existing values."""
import json
import re

import pytest
import requests

from services.acme.dns_providers.azure import AzureDnsProvider

BASE = AzureDnsProvider.BASE_URL
ZONES = '/subscriptions/sub/resourceGroups/rg/providers/Microsoft.Network/dnsZones'


class _Response:
    def __init__(self, status, body=None):
        self.status_code = status
        self.reason = 'error'
        self.text = json.dumps(body) if body is not None else ''
        self._body = body

    def json(self):
        return self._body


class FakeAzure:
    """Routes from the DNS REST spec (2018-05-01): GET of a missing set is 404 ResourceNotFound."""

    def __init__(self):
        self.sets = {}
        self.calls = []
        self.get_status = None

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path, _, query = url.removeprefix(BASE).partition('?')
        assert query == 'api-version=2018-05-01'
        self.calls.append(method)
        if method == 'GET' and path == ZONES:
            return _Response(200, {'value': [{'name': 'example.com'}]})
        m = re.fullmatch(ZONES + r'/example\.com/TXT/([^/]+)', path)
        if not m:
            return _Response(404, {'error': {'code': 'NotFound', 'message': 'bad route'}})
        name = m.group(1)
        if method == 'GET':
            if self.get_status:
                return _Response(self.get_status, {'error': {'code': 'TooManyRequests', 'message': 'slow down'}})
            if name not in self.sets:
                return _Response(404, {'error': {'code': 'ResourceNotFound', 'message': f"The Resource '{name}' under resource group 'rg' was not found."}})
            return _Response(200, {'name': name, 'etag': 'e', 'properties': self.sets[name]})
        if method == 'PUT':
            created = name not in self.sets
            self.sets[name] = json['properties']
            return _Response(201 if created else 200, {'name': name, 'properties': json['properties']})
        if method == 'DELETE':
            if name not in self.sets:
                return _Response(204)
            del self.sets[name]
            return _Response(200)
        return _Response(405, {'error': {'message': 'method not allowed'}})


@pytest.fixture
def api(monkeypatch):
    fake = FakeAzure()
    monkeypatch.setattr(requests, 'request', fake)
    provider = AzureDnsProvider({
        'tenant_id': 't', 'client_id': 'c', 'client_secret': 's',
        'subscription_id': 'sub', 'resource_group': 'rg'})
    provider._access_token = 'token'
    return provider, fake


def _values(fake, name='_acme-challenge'):
    return [r['value'] for r in fake.sets[name]['TXTRecords']]


def test_first_call_creates(api):
    provider, fake = api
    assert provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok1', 120)[0]
    assert _values(fake) == [['tok1']]
    assert fake.sets['_acme-challenge']['TTL'] == 120


def test_second_value_keeps_the_first_ttl_and_metadata(api):
    provider, fake = api
    fake.sets['_acme-challenge'] = {'TTL': 120, 'metadata': {'k': 'v'}, 'TXTRecords': [{'value': ['tok1']}]}
    assert provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok2', 300)[0]
    assert _values(fake) == [['tok1'], ['tok2']]
    assert fake.sets['_acme-challenge']['TTL'] == 120
    assert fake.sets['_acme-challenge']['metadata'] == {'k': 'v'}


def test_value_already_present_is_not_rewritten(api):
    provider, fake = api
    provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    fake.calls.clear()
    assert provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')[0]
    assert 'PUT' not in fake.calls
    assert _values(fake) == [['tok1']]


def test_read_failure_does_not_overwrite(api):
    provider, fake = api
    provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    fake.get_status = 429
    fake.calls.clear()
    ok, _ = provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok2')
    assert not ok
    assert 'PUT' not in fake.calls
    assert _values(fake) == [['tok1']]


def test_cleanup_removes_the_set_and_second_call_succeeds(api):
    provider, fake = api
    provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok1')
    provider.create_txt_record('example.com', '_acme-challenge.example.com', 'tok2')
    assert provider.delete_txt_record('example.com', '_acme-challenge.example.com')[0]
    assert 'tok1' not in json.dumps(fake.sets)
    assert provider.delete_txt_record('example.com', '_acme-challenge.example.com')[0]
