"""delete_txt_record removes the one value it is given: other challenges share the name."""
import json
import logging
import re
import time
from urllib.parse import parse_qs, urlsplit

import requests

from services.acme.dns_providers import create_provider
from services.acme.dns_providers import freedns as freedns_module

NAME = '_acme-challenge.example.com'


class _Resp:
    def __init__(self, status, body=None, text=None):
        self.status_code = status
        self.reason = ''
        self.text = text if text is not None else (json.dumps(body) if body is not None else '')
        self._body = body
        self.url = ''

    def json(self):
        return self._body


class _RecordApi:
    """Per-record API: list records, delete one by id."""

    def __init__(self, value_key, quote=False):
        self.records = []
        self.calls = []
        self.next_id = 1
        self.value_key = value_key
        self.quote = quote

    def add(self, **fields):
        rec = {'id': self.next_id, **fields}
        self.next_id += 1
        self.records.append(rec)
        return rec

    def delete(self, rid):
        before = len(self.records)
        self.records = [r for r in self.records if str(r['id']) != str(rid)]
        return before != len(self.records)

    def values(self):
        return [r[self.value_key] for r in self.records]


def _create_two_delete_one(p, domain='example.com'):
    for value in ('apex', 'wild'):
        ok, msg = p.create_txt_record(domain, NAME, value)
        assert ok, msg
    # The second value: a cleanup that takes the first record of the name fails this
    ok, msg = p.delete_txt_record(domain, NAME, 'wild')
    assert ok, msg


# --- Domeneshop ---------------------------------------------------------------

class FakeDomeneshop(_RecordApi):
    def __call__(self, method, url, auth=None, json=None, timeout=None, headers=None):
        path = url.split('/v0', 1)[1]
        self.calls.append((method, path))
        if path == '/domains':
            return _Resp(200, [{'id': 9, 'domain': 'example.com'}])
        if path == '/domains/9/dns' and method == 'GET':
            return _Resp(200, self.records)
        if path == '/domains/9/dns' and method == 'POST':
            return _Resp(201, {'id': self.add(**json)['id']})
        m = re.fullmatch(r'/domains/9/dns/(\d+)', path)
        if m and method == 'DELETE':
            return _Resp(204) if self.delete(m.group(1)) else _Resp(404, {'error': 'not found'})
        return _Resp(404, {'error': 'not found'})


def test_domeneshop_deletes_one_value(monkeypatch):
    api = FakeDomeneshop('data')
    monkeypatch.setattr(requests, 'request', api)
    _create_two_delete_one(create_provider('domeneshop', {'api_token': 't', 'api_secret': 's'}))
    assert api.values() == ['"apex"']
    assert ('DELETE', '/domains/9/dns/2') in api.calls


# --- DreamHost ----------------------------------------------------------------

class FakeDreamhost:
    """dns-remove_record removes the record whose record, type and value all match."""

    def __init__(self):
        self.records = []
        self.calls = []

    def __call__(self, url, params=None, timeout=None):
        cmd = params['cmd']
        self.calls.append((cmd, params.get('value')))
        if cmd == 'dns-list_records':
            return _Resp(200, {'result': 'success', 'data': list(self.records)})
        rec = {'record': params['record'], 'type': params['type'], 'value': params['value']}
        if cmd == 'dns-add_record':
            self.records.append(rec)
            return _Resp(200, {'result': 'success', 'data': 'record_added'})
        if cmd == 'dns-remove_record':
            if rec not in self.records:
                return _Resp(200, {'result': 'error', 'data': 'no_such_record'})
            self.records.remove(rec)
            return _Resp(200, {'result': 'success', 'data': 'record_removed'})
        return _Resp(200, {'result': 'error', 'data': 'no_such_cmd'})


def test_dreamhost_deletes_one_value(monkeypatch):
    api = FakeDreamhost()
    monkeypatch.setattr(requests, 'get', api)
    _create_two_delete_one(create_provider('dreamhost', {'api_key': 'k'}))
    assert [r['value'] for r in api.records] == ['apex']
    assert ('dns-remove_record', 'wild') in api.calls


# --- Dynu -----------------------------------------------------------------------

class FakeDynu(_RecordApi):
    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path = url.split('/v2', 1)[1]
        self.calls.append((method, path))
        if path == '/dns':
            return _Resp(200, {'domains': [{'id': 4, 'name': 'example.com'}]})
        if path == '/dns/4/record' and method == 'GET':
            return _Resp(200, {'dnsRecords': self.records})
        if path == '/dns/4/record' and method == 'POST':
            return _Resp(200, self.add(**json))
        m = re.fullmatch(r'/dns/4/record/(\d+)', path)
        if m and method == 'DELETE':
            return _Resp(200, {'statusCode': 200}) if self.delete(m.group(1)) else _Resp(404, {'message': 'nf'})
        return _Resp(404, {'message': 'not found'})


def test_dynu_deletes_one_value(monkeypatch):
    api = FakeDynu('textData')
    monkeypatch.setattr(requests, 'request', api)
    _create_two_delete_one(create_provider('dynu', {'api_key': 'k'}))
    assert api.values() == ['apex']
    assert ('DELETE', '/dns/4/record/2') in api.calls


# --- EasyDNS --------------------------------------------------------------------

class FakeEasyDns(_RecordApi):
    def __call__(self, method, url, json=None, timeout=None):
        path = urlsplit(url).path
        self.calls.append((method, path))
        if path == '/zones/records/all/example.com' and method == 'GET':
            return _Resp(200, {'data': self.records})
        if path == '/zones/records/add/example.com/TXT' and method == 'PUT':
            return _Resp(201, {'data': self.add(**json)})
        m = re.fullmatch(r'/zones/records/example\.com/(\d+)', path)
        if m and method == 'DELETE':
            return _Resp(200, {'msg': 'OK'}) if self.delete(m.group(1)) else _Resp(404, {'error': 'nf'})
        return _Resp(404, {'error': 'not found'})


def test_easydns_deletes_one_value(monkeypatch):
    api = FakeEasyDns('rdata')
    monkeypatch.setattr(requests, 'request', api)
    _create_two_delete_one(create_provider('easydns', {'api_token': 't', 'api_key': 'k'}))
    assert api.values() == ['apex']
    assert ('DELETE', '/zones/records/example.com/2') in api.calls


# --- Google Cloud DNS -------------------------------------------------------------

class FakeCloudDns:
    """A change applies atomically; a deletion must equal the stored RRset (else 412)."""

    def __init__(self):
        self.rrsets = {}
        self.changes = []
        self.list_status = None

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        parts = urlsplit(url)
        path = parts.path.split('/dns/v1', 1)[1]
        if path == '/projects/p/managedZones':
            # Paginated by nextPageToken / pageToken (managedZones.list).
            if parse_qs(parts.query).get('pageToken') == ['t2']:
                return _Resp(200, {'managedZones': [{'name': 'ex', 'dnsName': 'example.com.'}]})
            return _Resp(200, {'managedZones': [{'name': 'co', 'dnsName': 'com.'}], 'nextPageToken': 't2'})
        if path == '/projects/p/managedZones/ex/rrsets' and method == 'GET':
            if self.list_status:
                return _Resp(self.list_status, {'error': {'message': 'backend error'}})
            name = parse_qs(parts.query)['name'][0]
            found = [r for r in self.rrsets.values() if r['name'] == name]
            return _Resp(200, {'rrsets': found})
        if path == '/projects/p/managedZones/ex/changes' and method == 'POST':
            self.changes.append(json)
            for rrset in json.get('deletions', []):
                if self.rrsets.get(rrset['name']) != rrset:
                    return _Resp(412, {'error': {'message': 'conditionNotMet'}})
            for rrset in json.get('deletions', []):
                del self.rrsets[rrset['name']]
            for rrset in json.get('additions', []):
                if rrset['name'] in self.rrsets:
                    return _Resp(409, {'error': {'message': 'alreadyExists'}})
                self.rrsets[rrset['name']] = {**rrset, 'kind': 'dns#resourceRecordSet'}
            return _Resp(200, {'status': 'done'})
        return _Resp(404, {'error': {'message': 'not found'}})


def _gcloud():
    p = create_provider('gcloud', {'project_id': 'p', 'service_account_json': '{}'})
    p._access_token, p._token_expiry = 'tok', time.time() + 3600
    return p


def test_gcloud_deletes_one_value(monkeypatch):
    api = FakeCloudDns()
    monkeypatch.setattr(requests, 'request', api)
    _create_two_delete_one(_gcloud())
    assert api.rrsets[NAME + '.']['rrdatas'] == ['"apex"']
    assert api.rrsets[NAME + '.']['ttl'] == 300
    assert api.changes[-1]['additions'][0]['rrdatas'] == ['"apex"']


def test_gcloud_deletes_the_rrset_with_its_last_value(monkeypatch):
    api = FakeCloudDns()
    monkeypatch.setattr(requests, 'request', api)
    p = _gcloud()
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    assert p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert api.rrsets == {}
    assert 'additions' not in api.changes[-1]


def test_gcloud_failed_read_writes_nothing(monkeypatch, caplog):
    api = FakeCloudDns()
    monkeypatch.setattr(requests, 'request', api)
    p = _gcloud()
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.list_status = 500
    with caplog.at_level(logging.WARNING):
        ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'backend error' in msg
    assert any(r.levelno == logging.WARNING and 'backend error' in r.getMessage() for r in caplog.records)
    ok, msg = p.create_txt_record('example.com', NAME, 'wild')
    assert not ok and 'backend error' in msg
    assert len(api.changes) == 1
    assert api.rrsets[NAME + '.']['rrdatas'] == ['"apex"']


# --- DuckDNS and FreeDNS: no value to target ---------------------------------------

def test_duckdns_cleanup_warns_that_it_clears_the_name(monkeypatch, caplog):
    sent = []
    monkeypatch.setattr(requests, 'get', lambda url, params=None, timeout=None: sent.append(params) or _Resp(200, text='OK'))
    p = create_provider('duckdns', {'token': 'x' * 36})
    with caplog.at_level(logging.WARNING):
        ok, msg = p.delete_txt_record('me.duckdns.org', '_acme-challenge.me.duckdns.org', 'apex')
    assert ok, msg
    assert sent[0]['clear'] == 'true' and sent[0]['domains'] == 'me'
    assert any(r.levelno == logging.WARNING and 'clears' in r.getMessage() for r in caplog.records)


def test_freedns_cleanup_warns_that_it_removes_the_name(monkeypatch, caplog):
    class Session:
        def __init__(self):
            self.deleted = []

        def post(self, url, data=None, timeout=None):
            return _Resp(200, text='Logout')

        def get(self, url, params=None, timeout=None):
            if params:
                self.deleted.append(params['data_id[]'])
            if '5' in self.deleted:
                return _Resp(200, text='')
            return _Resp(200, text='<a href=edit.php?data_id=5>_acme-challenge.example.com</a>')

    session = Session()
    monkeypatch.setattr(freedns_module, 'create_session', lambda: session)
    p = create_provider('freedns', {'username': 'u', 'password': 'p'})
    with caplog.at_level(logging.WARNING):
        ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert session.deleted == ['5']
    assert any(r.levelno == logging.WARNING and 'whichever value' in r.getMessage() for r in caplog.records)


def test_freedns_cleanup_leaves_the_record_of_another_domain(monkeypatch):
    class Session:
        def __init__(self):
            self.deleted = []

        def post(self, url, data=None, timeout=None):
            return _Resp(200, text='Logout')

        def get(self, url, params=None, timeout=None):
            if params:
                self.deleted.append(params['data_id[]'])
            rows = [r for r in ('4', '5') if r not in self.deleted]
            names = {'4': '_acme-challenge.other.example', '5': '_acme-challenge.example.com'}
            return _Resp(200, text=''.join(f'<a href=edit.php?data_id={r}>{names[r]}</a>' for r in rows))

    session = Session()
    monkeypatch.setattr(freedns_module, 'create_session', lambda: session)
    p = create_provider('freedns', {'username': 'u', 'password': 'p'})
    assert p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert session.deleted == ['5']


def test_freedns_record_still_listed_is_false(monkeypatch):
    class Session:
        def post(self, url, data=None, timeout=None):
            return _Resp(200, text='Logout')

        def get(self, url, params=None, timeout=None):
            # The delete page answers 200 but the record stays.
            return _Resp(200, text='<a href=edit.php?data_id=5>_acme-challenge.example.com</a>')

    monkeypatch.setattr(freedns_module, 'create_session', lambda: Session())
    p = create_provider('freedns', {'username': 'u', 'password': 'p'})
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'kept the record' in msg


class _FreeDnsSession:
    """Login answers 'Logout'; the listing shows `rows`, or raises when `down`."""

    def __init__(self, rows=(), down=False):
        self.rows, self.down, self.saved = list(rows), down, []

    def post(self, url, data=None, timeout=None):
        if 'save.php' in url:
            self.saved.append(data)
        return _Resp(200, text='Logout')

    def get(self, url, params=None, timeout=None):
        if self.down:
            raise requests.ConnectionError('listing unreachable')
        return _Resp(200, text='<a href=edit.php?domain_id=9>example.com</a>' + ''.join(
            f'<a href=edit.php?data_id={i}>{n}</a>' for i, n in self.rows))


def test_freedns_create_not_listed_afterwards_is_false(monkeypatch):
    session = _FreeDnsSession()
    monkeypatch.setattr(freedns_module, 'create_session', lambda: session)
    p = create_provider('freedns', {'username': 'u', 'password': 'p'})
    ok, msg = p.create_txt_record('example.com', NAME, 'apex')
    assert not ok and 'did not list' in msg
    assert '<a' not in msg
    assert len(session.saved) == 1


def test_freedns_unreadable_listing_is_false_not_absent(monkeypatch):
    session = _FreeDnsSession(rows=[('5', NAME)], down=True)
    monkeypatch.setattr(freedns_module, 'create_session', lambda: session)
    p = create_provider('freedns', {'username': 'u', 'password': 'p'})
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'Could not read' in msg
