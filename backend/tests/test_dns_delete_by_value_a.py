"""delete_txt_record removes only its value: a wildcard and its apex share the challenge name."""
import json
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests

from services.acme.dns_providers import create_provider

NAME = '_acme-challenge.example.com'


class _Resp:
    def __init__(self, status, body=None, text=None):
        self.status_code = status
        self.reason = 'error' if status >= 400 else 'OK'
        self.text = text if text is not None else (json.dumps(body) if body is not None else '')
        self._body = body

    def json(self):
        if self._body is None:
            return json.loads(self.text)
        return self._body


def _split(url, base):
    parts = urlsplit(url.removeprefix(base))
    return parts.path, dict(parse_qsl(parts.query))


def _two_values_then_delete_apex(provider):
    for value in ('apex', 'wild'):
        ok, msg = provider.create_txt_record('example.com', NAME, value)
        assert ok, msg
    ok, msg = provider.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg


class _PerRecordFake:
    """Records with ids; `deletes` keeps every DELETE path that hit the fake."""

    value_key = 'value'

    def __init__(self):
        self.records = []
        self.deletes = []
        self.next_id = 1

    def add(self, rec):
        rec = {'id': self.next_id, **rec}
        self.next_id += 1
        self.records.append(rec)
        return rec

    def drop(self, rid):
        self.records = [r for r in self.records if str(r['id']) != str(rid)]

    def values(self):
        return [r[self.value_key] for r in self.records]


# --- Alwaysdata ---------------------------------------------------------------

class FakeAlwaysdata(_PerRecordFake):
    def __call__(self, method, url, auth=None, json=None, timeout=None, headers=None):
        path, query = _split(url, 'https://api.alwaysdata.com/v1')
        if method == 'GET' and path == '/domain/':
            return _Resp(200, [{'id': 7, 'name': 'example.com'}])
        if method == 'POST' and path == '/record/':
            self.add(dict(json))
            return _Resp(201, text='')
        if method == 'GET' and path == '/record/':
            return _Resp(200, [r for r in self.records
                               if r['name'] == query['name'] and r['type'] == query['type']])
        if method == 'DELETE' and path.startswith('/record/'):
            self.deletes.append(path)
            self.drop(path.strip('/').rsplit('/', 1)[1])
            return _Resp(204, text='')
        return _Resp(404, {'detail': 'Not found'})


def test_alwaysdata_deletes_one_value(monkeypatch):
    api = FakeAlwaysdata()
    monkeypatch.setattr(requests, 'request', api)
    _two_values_then_delete_apex(create_provider('alwaysdata', {'api_key': 'k', 'account': 'a'}))
    assert api.values() == ['"wild"']
    assert api.deletes == ['/record/1/']


# --- BookMyName ---------------------------------------------------------------

class FakeBookMyName:
    """DynDNS endpoint: do=add adds a value, do=remove removes the exact value given."""

    def __init__(self):
        self.values = {}
        self.removes = []

    def __call__(self, url, params=None, auth=None, timeout=None):
        values = self.values.setdefault(params['hostname'], [])
        if params['do'] == 'add':
            values.append(params['value'])
            return _Resp(200, text='good: update done')
        if params['do'] == 'remove':
            self.removes.append(params['value'])
            if params['value'] in values:
                values.remove(params['value'])
            return _Resp(200, text='good: remove done')
        return _Resp(200, text='error: bad request')


def test_bookmyname_removes_the_exact_value(monkeypatch):
    api = FakeBookMyName()
    monkeypatch.setattr(requests, 'get', api)
    _two_values_then_delete_apex(create_provider('bookmyname', {'username': 'u', 'password': 'p'}))
    assert api.values[NAME] == ['"wild"']
    assert api.removes == ['"apex"']


# --- Bunny --------------------------------------------------------------------

class FakeBunny(_PerRecordFake):
    value_key = 'Value'

    def __call__(self, method, url, headers=None, json=None, timeout=None, allow_redirects=True):
        path, _ = _split(url, 'https://api.bunny.net')
        if method == 'GET' and path == '/dnszone':
            return _Resp(200, {'Items': [{'Id': 3, 'Domain': 'example.com'}]})
        if method == 'PUT' and path == '/dnszone/3/records':
            rec = self.add(dict(json))
            rec['Id'] = rec['id']
            return _Resp(201, rec)
        if method == 'GET' and path == '/dnszone/3':
            return _Resp(200, {'Id': 3, 'Records': self.records})
        if method == 'DELETE' and path.startswith('/dnszone/3/records/'):
            self.deletes.append(path)
            self.drop(path.rsplit('/', 1)[1])
            return _Resp(204, text='')
        return _Resp(404, {'Message': 'Not found'})


def test_bunny_deletes_one_value(monkeypatch):
    api = FakeBunny()
    monkeypatch.setattr(requests, 'request', api)
    _two_values_then_delete_apex(create_provider('bunny', {'api_key': 'k'}))
    assert api.values() == ['wild']
    assert api.deletes == ['/dnszone/3/records/1']


# --- ClouDNS ------------------------------------------------------------------

class FakeClouDns(_PerRecordFake):
    """records.json answers a dict keyed by record id; writes are form POSTs."""

    value_key = 'record'
    BASE = 'https://api.cloudns.net'

    def get(self, url, params=None, timeout=None):
        path, _ = _split(url, self.BASE)
        if path == '/dns/list-zones.json':
            return _Resp(200, [{'name': 'example.com', 'type': 'master'}])
        if path == '/dns/records.json':
            return _Resp(200, {str(r['id']): {**r, 'id': str(r['id'])} for r in self.records
                               if r['host'] == params['host'] and r['type'] == params['type']})
        return _Resp(200, {'status': 'Failed', 'statusDescription': 'Invalid request'})

    def post(self, url, data=None, timeout=None, allow_redirects=True):
        path, _ = _split(url, self.BASE)
        if path == '/dns/add-record.json':
            self.add({'type': data['record-type'], 'host': data['host'], 'record': data['record']})
            return _Resp(200, {'status': 'Success', 'statusDescription': 'The record was added successfully.'})
        if path == '/dns/delete-record.json':
            self.deletes.append(data['record-id'])
            self.drop(data['record-id'])
            return _Resp(200, {'status': 'Success', 'statusDescription': 'The record was deleted successfully.'})
        return _Resp(200, {'status': 'Failed', 'statusDescription': 'Invalid request'})


def test_cloudns_deletes_one_value(monkeypatch):
    api = FakeClouDns()
    monkeypatch.setattr(requests, 'get', api.get)
    monkeypatch.setattr(requests, 'post', api.post)
    _two_values_then_delete_apex(create_provider('cloudns', {'auth_id': '1', 'auth_password': 'p'}))
    assert api.values() == ['wild']
    assert api.deletes == ['1']


# --- DigitalOcean ---------------------------------------------------------------

class FakeDigitalOcean(_PerRecordFake):
    value_key = 'data'

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, _ = _split(url, 'https://api.digitalocean.com/v2')
        if method == 'GET' and path == '/domains/example.com':
            return _Resp(200, {'domain': {'name': 'example.com'}})
        if path == '/domains/example.com/records' and method == 'POST':
            return _Resp(201, {'domain_record': self.add(dict(json))})
        if path == '/domains/example.com/records' and method == 'GET':
            return _Resp(200, {'domain_records': self.records})
        if method == 'DELETE' and path.startswith('/domains/example.com/records/'):
            self.deletes.append(path)
            self.drop(path.rsplit('/', 1)[1])
            return _Resp(204, text='')
        return _Resp(404, {'id': 'not_found', 'message': 'The resource you were accessing could not be found.'})


def test_digitalocean_deletes_one_value(monkeypatch):
    api = FakeDigitalOcean()
    monkeypatch.setattr(requests, 'request', api)
    _two_values_then_delete_apex(create_provider('digitalocean', {'api_token': 't'}))
    assert api.values() == ['wild']
    assert api.deletes == ['/domains/example.com/records/1']


# --- DNSimple -----------------------------------------------------------------

class FakeDnsimple(_PerRecordFake):
    """TXT content comes back quoted, as the v2 API normalises it."""

    value_key = 'content'

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path, query = _split(url, 'https://api.dnsimple.com/v2/42')
        if method == 'GET' and path == '/zones':
            return _Resp(200, {'data': [{'name': 'example.com'}]})
        if path == '/zones/example.com/records' and method == 'POST':
            return _Resp(201, {'data': self.add({**json, 'content': f'"{json["content"]}"'})})
        if path == '/zones/example.com/records' and method == 'GET':
            return _Resp(200, {'data': [r for r in self.records
                                        if r['type'] == query['type'] and r['name'] == query['name']]})
        if method == 'DELETE' and path.startswith('/zones/example.com/records/'):
            self.deletes.append(path)
            self.drop(path.rsplit('/', 1)[1])
            return _Resp(204, text='')
        return _Resp(404, {'message': 'Not found'})


def test_dnsimple_deletes_one_value(monkeypatch):
    api = FakeDnsimple()
    monkeypatch.setattr(requests, 'request', api)
    _two_values_then_delete_apex(create_provider('dnsimple', {'api_token': 't', 'account_id': '42'}))
    assert api.values() == ['"wild"']
    assert api.deletes == ['/zones/example.com/records/1']


# --- DNS Made Easy --------------------------------------------------------------

class FakeDnsMadeEasy(_PerRecordFake):
    def __call__(self, method, url, headers=None, json=None, timeout=None, allow_redirects=True):
        path, query = _split(url, 'https://api.dnsmadeeasy.com/V2.0')
        if method == 'GET' and path == '/dns/managed/':
            return _Resp(200, {'data': [{'id': 6, 'name': 'example.com'}]})
        if method == 'POST' and path == '/dns/managed/6/records/':
            return _Resp(201, self.add(dict(json)))
        if method == 'GET' and path == '/dns/managed/6/records':
            return _Resp(200, {'data': [r for r in self.records
                                        if r['type'] == query['type'] and r['name'] == query['recordName']]})
        if method == 'DELETE' and path.startswith('/dns/managed/6/records/'):
            self.deletes.append(path)
            self.drop(path.rsplit('/', 1)[1])
            return _Resp(200, text='')
        return _Resp(404, {'error': ['Not found']})


def test_dnsmadeeasy_deletes_one_value(monkeypatch):
    api = FakeDnsMadeEasy()
    monkeypatch.setattr(requests, 'request', api)
    _two_values_then_delete_apex(create_provider('dnsmadeeasy', {'api_key': 'k', 'secret_key': 's'}))
    assert api.values() == ['"wild"']
    assert api.deletes == ['/dns/managed/6/records/1']
