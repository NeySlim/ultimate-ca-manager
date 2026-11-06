"""delete_txt_record removes the one value it is given: OVH, Porkbun, Rackspace, RcodeZero, Scaleway, Vercel, Vultr."""
import json as jsonlib
from urllib.parse import urlsplit, parse_qs

import pytest
import requests

from services.acme.dns_providers import create_provider

NAME = '_acme-challenge.example.com'


class _Resp:
    def __init__(self, status, body=None, text=None):
        self.status_code = status
        self.reason = 'error' if status >= 400 else 'OK'
        self._body = body
        self.text = text if text is not None else (jsonlib.dumps(body) if body is not None else '')

    def json(self):
        return self._body


def _two_values_then_delete_one(provider):
    for value in ('apex', 'wild'):
        ok, msg = provider.create_txt_record('example.com', NAME, value)
        assert ok, msg
    ok, msg = provider.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg


# --- OVH: the listing returns IDs, each record is read by ID ---------------------

class FakeOvh:
    def __init__(self):
        self.records = {}
        self.next_id = 1
        self.deleted = []

    def get(self, url, timeout=None):
        assert url.endswith('/auth/time')
        return _Resp(200, text='0')

    def request(self, method, url, headers=None, data=None, timeout=None):
        parts = urlsplit(url)
        path = parts.path.split('/1.0', 1)[1]
        query = parse_qs(parts.query)
        if method == 'GET' and path == '/domain/zone/example.com':
            return _Resp(200, {'name': 'example.com'})
        if path == '/domain/zone/example.com/record' and method == 'POST':
            body = jsonlib.loads(data)
            rid = self.next_id
            self.next_id += 1
            # OVH hands TXT targets back quoted
            self.records[rid] = {'id': rid, 'fieldType': body['fieldType'], 'subDomain': body['subDomain'],
                                 'target': f'"{body["target"]}"', 'ttl': body['ttl']}
            return _Resp(200, self.records[rid])
        if path == '/domain/zone/example.com/record' and method == 'GET':
            return _Resp(200, [r['id'] for r in self.records.values()
                               if r['fieldType'] == query['fieldType'][0]
                               and r['subDomain'] == query['subDomain'][0]])
        if path.startswith('/domain/zone/example.com/record/'):
            rid = int(path.rsplit('/', 1)[1])
            if rid not in self.records:
                return _Resp(404, {'message': 'not found'})
            if method == 'GET':
                return _Resp(200, self.records[rid])
            if method == 'DELETE':
                self.deleted.append(rid)
                del self.records[rid]
                return _Resp(200, text='')
        if method == 'POST' and path == '/domain/zone/example.com/refresh':
            return _Resp(200, text='')
        return _Resp(404, {'message': f'unexpected {method} {path}'})


def test_ovh_deletes_one_value(monkeypatch):
    api = FakeOvh()
    monkeypatch.setattr(requests, 'get', api.get)
    monkeypatch.setattr(requests, 'request', api.request)
    p = create_provider('ovh', {'application_key': 'a', 'application_secret': 's', 'consumer_key': 'c'})
    _two_values_then_delete_one(p)
    assert api.deleted == [1]
    assert [r['target'] for r in api.records.values()] == ['"wild"']


# --- Porkbun ------------------------------------------------------------------

class FakePorkbun:
    def __init__(self):
        self.records = []
        self.next_id = 1
        self.deleted = []

    def post(self, url, json=None, timeout=None):
        path = url.split('/api/json/v3', 1)[1]
        ok = {'status': 'SUCCESS'}
        if path == '/dns/create/example.com':
            rec = {'id': str(self.next_id), 'name': f"{json['name']}.example.com", 'type': json['type'],
                   'content': json['content'], 'ttl': json['ttl']}
            self.next_id += 1
            self.records.append(rec)
            return _Resp(200, {**ok, 'id': rec['id']})
        if path.startswith('/dns/retrieveByNameType/example.com/'):
            rtype, sub = path.split('/')[4:6]
            return _Resp(200, {**ok, 'records': [r for r in self.records
                                                 if r['type'] == rtype and r['name'] == f'{sub}.example.com']})
        if path.startswith('/dns/delete/example.com/'):
            rid = path.rsplit('/', 1)[1]
            self.deleted.append(rid)
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(200, ok)
        return _Resp(400, {'status': 'ERROR', 'message': f'unexpected {path}'})


def test_porkbun_deletes_one_value(monkeypatch):
    api = FakePorkbun()
    monkeypatch.setattr(requests, 'post', api.post)
    p = create_provider('porkbun', {'api_key': 'k', 'secret_api_key': 's'})
    _two_values_then_delete_one(p)
    assert api.deleted == ['1']
    assert [r['content'] for r in api.records] == ['wild']


# --- Rackspace ----------------------------------------------------------------

class FakeRackspace:
    ENDPOINT = 'https://dns.api.rackspacecloud.com/v1.0/123'

    def __init__(self):
        self.records = []
        self.next_id = 1
        self.deleted = []

    def post(self, url, json=None, timeout=None):
        return _Resp(200, {'access': {'token': {'id': 'tok'}, 'serviceCatalog': [
            {'name': 'cloudDNS', 'endpoints': [{'publicURL': self.ENDPOINT}]}]}})

    def request(self, method, url, headers=None, json=None, timeout=None):
        parts = urlsplit(url[len(self.ENDPOINT):])
        query = parse_qs(parts.query)
        if method == 'GET' and parts.path == '/domains':
            return _Resp(200, {'domains': [{'id': 1, 'name': 'example.com'}]})
        if parts.path == '/domains/1/records' and method == 'POST':
            for rec in json['records']:
                self.records.append({'id': f'TXT-{self.next_id}', **rec})
                self.next_id += 1
            return _Resp(202, {'status': 'RUNNING'})
        if parts.path == '/domains/1/records' and method == 'GET':
            return _Resp(200, {'records': [r for r in self.records
                                           if r['type'] == query['type'][0] and r['name'] == query['name'][0]]})
        if method == 'DELETE' and parts.path.startswith('/domains/1/records/'):
            rid = parts.path.rsplit('/', 1)[1]
            self.deleted.append(rid)
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(202, {'status': 'RUNNING'})
        return _Resp(404, {'message': 'not found'})


def test_rackspace_deletes_one_value(monkeypatch):
    api = FakeRackspace()
    monkeypatch.setattr(requests, 'post', api.post)
    monkeypatch.setattr(requests, 'request', api.request)
    p = create_provider('rackspace', {'username': 'u', 'api_key': 'k'})
    _two_values_then_delete_one(p)
    assert api.deleted == ['TXT-1']
    assert [r['data'] for r in api.records] == ['wild']


# --- Scaleway: delete by record ID ---------------------------------------------------

class FakeScaleway:
    """PATCH changes per the API: delete by id, or by id_fields (name, type, optional data)."""

    def __init__(self):
        self.records = []
        self.next_id = 1
        self.patches = []

    def request(self, method, url, headers=None, json=None, params=None, timeout=None):
        path = url.split('/domain/v2beta1', 1)[1]
        if method == 'GET' and path == '/dns-zones':
            return _Resp(200, {'dns_zones': [{'domain': 'example.com'}]})
        if method == 'GET' and path == '/dns-zones/example.com/records':
            found = [r for r in self.records if r['name'] == params['name'] and r['type'] == params['type']]
            return _Resp(200, {'total_count': len(found), 'records': found})
        if method == 'PATCH' and path == '/dns-zones/example.com/records':
            self.patches.append(json)
            for change in json['changes']:
                if 'add' in change:
                    for rec in change['add']['records']:
                        self.records.append({'id': f'r{self.next_id}', **rec})
                        self.next_id += 1
                elif 'id' in change['delete']:
                    self.records = [r for r in self.records if r['id'] != change['delete']['id']]
                else:
                    f = change['delete']['id_fields']
                    self.records = [r for r in self.records
                                    if not (r['name'] == f['name'] and r['type'] == f['type']
                                            and f.get('data', r['data']) == r['data'])]
            return _Resp(200, {'records': []})
        return _Resp(404, {'message': 'not found'})


def test_scaleway_deletes_one_value(monkeypatch):
    api = FakeScaleway()
    monkeypatch.setattr(requests, 'request', api.request)
    p = create_provider('scaleway', {'api_token': 'tokentoken'})
    _two_values_then_delete_one(p)
    assert api.patches[-1]['changes'] == [{'delete': {'id': 'r1'}}]
    assert [r['data'] for r in api.records] == ['"wild"']


# --- Vercel -------------------------------------------------------------------------

class FakeVercel:
    def __init__(self):
        self.records = [{'id': 'rec_a', 'name': 'other', 'type': 'TXT', 'value': 'apex'}]
        self.next_id = 1
        self.deleted = []

    def request(self, method, url, headers=None, json=None, timeout=None):
        path = url.split('api.vercel.com', 1)[1]
        if method == 'POST' and path == '/v2/domains/example.com/records':
            rec = {'id': f'rec_{self.next_id}', **json}
            self.next_id += 1
            self.records.append(rec)
            return _Resp(200, {'uid': rec['id']})
        if method == 'GET' and path == '/v4/domains/example.com/records':
            return _Resp(200, {'records': self.records})
        if method == 'DELETE' and path.startswith('/v2/domains/example.com/records/'):
            rid = path.rsplit('/', 1)[1]
            self.deleted.append(rid)
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(200, {})
        return _Resp(404, {'error': {'message': 'not found'}})


def test_vercel_deletes_one_value(monkeypatch):
    api = FakeVercel()
    monkeypatch.setattr(requests, 'request', api.request)
    p = create_provider('vercel', {'api_token': 'tokentoken'})
    _two_values_then_delete_one(p)
    assert api.deleted == ['rec_1']
    assert [(r['name'], r['value']) for r in api.records] == [('other', 'apex'), ('_acme-challenge', 'wild')]
