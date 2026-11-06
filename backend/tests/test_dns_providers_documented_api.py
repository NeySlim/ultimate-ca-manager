"""DNS providers against fakes that answer as each provider's public API documentation says."""
import json
from urllib.parse import parse_qsl, urlsplit

import pytest
import requests

from services.acme.dns_providers import create_provider

NAME = '_acme-challenge.example.com'


class _Resp:
    def __init__(self, status, body=None, text=None, headers=None):
        self.status_code = status
        self.reason = 'Error' if status >= 400 else 'OK'
        self.text = text if text is not None else (json.dumps(body) if body is not None else '')
        self._body = body
        self.headers = headers or {}

    @property
    def ok(self):
        return self.status_code < 400

    def json(self):
        if self._body is None:
            return json.loads(self.text)
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'{self.status_code} Error', response=self)


def _split(url, base):
    parts = urlsplit(url.removeprefix(base))
    return parts.path, dict(parse_qsl(parts.query))


def _lifecycle(provider, values):
    """Create apex and wild, delete apex (wild stays), delete wild (name gone)."""
    for value in ('apex', 'wild'):
        ok, msg = provider.create_txt_record('example.com', NAME, value)
        assert ok, msg
    assert sorted(values()) == ['apex', 'wild']
    ok, msg = provider.delete_txt_record('example.com', NAME, 'apex')
    assert ok, msg
    assert values() == ['wild']
    ok, msg = provider.delete_txt_record('example.com', NAME, 'wild')
    assert ok, msg
    assert values() == []
    ok, msg = provider.delete_txt_record('example.com', NAME, 'wild')
    assert ok, msg


# --- Constellix v4 --------------------------------------------------------------
# https://api.dns.constellix.com/v4/docs : Authorization: Bearer key:hmac:ts,
# /domains/{id}/records paginated (meta.links.next), POST 202, PUT 200, DELETE 204,
# one TXT record per name holding every value in `value: [{value, enabled}]`.

class FakeConstellix:
    BASE = 'https://api.dns.constellix.com/v4'
    PER_PAGE = 2

    def __init__(self):
        self.domains = [{'id': i, 'name': f'other{i}.test'} for i in range(1, 4)]
        self.domains.append({'id': 4, 'name': 'example.com'})
        self.records = [{'id': 1, 'type': 'A', 'name': 'www', 'ttl': 60, 'mode': 'standard',
                         'value': [{'value': '192.0.2.1', 'enabled': True}]},
                        {'id': 2, 'type': 'TXT', 'name': '', 'ttl': 60, 'mode': 'standard',
                         'value': [{'value': 'v=spf1 -all', 'enabled': True}]},
                        {'id': 3, 'type': 'MX', 'name': '', 'ttl': 60, 'mode': 'standard',
                         'value': [{'server': 'mx.example.com', 'priority': 10}]}]
        self.next_id = 10
        self.fail = None

    def _page(self, items, query, path):
        page = int(query.get('page', 1))
        chunk = items[(page - 1) * self.PER_PAGE:page * self.PER_PAGE]
        last = max(1, -(-len(items) // self.PER_PAGE))
        nxt = f'{self.BASE}{path}?page={page + 1}' if page < last else None
        return _Resp(200, {'data': chunk, 'meta': {
            'links': {'self': f'{self.BASE}{path}?page={page}', 'next': nxt},
            'pagination': {'total': len(items), 'count': len(chunk), 'perPage': self.PER_PAGE,
                           'currentPage': page, 'totalPages': last}}})

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update({k: str(v) for k, v in (params or {}).items()})
        if not (headers or {}).get('Authorization', '').startswith('Bearer k:'):
            return _Resp(401, {'errors': ['Unauthorized']})
        if self.fail == method:
            return _Resp(500, {'errors': ['Internal error']})
        if method == 'GET' and path == '/domains':
            return self._page(self.domains, query, path)
        if path == '/domains/4/records':
            if method == 'GET':
                return self._page(self.records, query, path)
            if method == 'POST':
                if not isinstance(json.get('value'), list) or json.get('type') != 'TXT':
                    return _Resp(422, {'errors': ['value must be an array']})
                rec = {'id': self.next_id, **json}
                self.next_id += 1
                self.records.append(rec)
                loc = f'{self.BASE}/domains/4/records/{rec["id"]}'
                return _Resp(202, {'id': rec['id'], 'location': loc}, headers={'Location': loc})
        if path.startswith('/domains/4/records/'):
            rid = int(path.rsplit('/', 1)[1])
            if not any(r['id'] == rid for r in self.records):
                return _Resp(404, {'errors': ['Not found']})
            if method == 'PUT':
                self.records = [{'id': rid, **json} if r['id'] == rid else r for r in self.records]
                return _Resp(200, {'data': {'id': rid, **json}})
            if method == 'DELETE':
                self.records = [r for r in self.records if r['id'] != rid]
                return _Resp(204)
        return _Resp(404, {'errors': ['Not found']})

    def txt(self):
        return [r for r in self.records if r['type'] == 'TXT' and r['name'] == '_acme-challenge']

    def values(self):
        return [v['value'] for r in self.txt() for v in r['value']]


@pytest.fixture
def constellix(monkeypatch):
    api = FakeConstellix()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('constellix', {'api_key': 'k', 'secret_key': 's'})


def test_constellix_lifecycle(constellix):
    api, p = constellix
    _lifecycle(p, api.values)
    # The SPF record of the apex is never touched.
    assert [r['id'] for r in api.records] == [1, 2, 3]


def test_constellix_second_value_joins_the_one_record(constellix):
    api, p = constellix
    for value in ('apex', 'wild'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    assert len(api.txt()) == 1
    assert api.txt()[0]['value'] == [{'value': 'apex', 'enabled': True},
                                     {'value': 'wild', 'enabled': True}]


def test_constellix_failed_delete_is_false(constellix):
    api, p = constellix
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and '500' in msg
    assert api.values() == ['apex']


def test_constellix_failed_read_is_false(constellix):
    api, p = constellix
    api.fail = 'GET'
    assert not p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert not p.create_txt_record('example.com', NAME, 'apex')[0]


# --- Core Networks ----------------------------------------------------------------
# https://beta.api.core-networks.de/doc/ : POST /auth/token (JSON login/password),
# /dnszones/<zone>/records/ (GET with filters, POST adds, identical adds nothing),
# POST .../records/delete with a filter body (omitted fields match all, an empty body
# deletes the zone), POST .../records/commit publishes the changes.

class FakeCoreNetworks:
    BASE = 'https://beta.api.core-networks.de'

    def __init__(self):
        self.records = [{'name': '@', 'ttl': 3600, 'type': 'TXT', 'data': '"v=spf1 -all"'},
                        {'name': 'www', 'ttl': 3600, 'type': 'A', 'data': '192.0.2.1'}]
        self.live = [dict(r) for r in self.records]
        self.commits = 0
        self.fail = None

    def post(self, url, json=None, data=None, timeout=None):
        if url != f'{self.BASE}/auth/token' or json != {'login': 'u', 'password': 'p'}:
            return _Resp(401, {'error': 'invalid credentials'})
        return _Resp(200, {'token': 'tok', 'expires': 3600})

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update(params or {})
        if (headers or {}).get('Authorization') != 'Bearer tok':
            return _Resp(401, {'error': 'unauthorized'})
        if self.fail and self.fail in path:
            return _Resp(500, {'error': 'internal error'})
        if method == 'GET' and path == '/dnszones/':
            return _Resp(200, [{'name': 'example.com', 'type': 'master'}])
        if path == '/dnszones/example.com/records/':
            if method == 'GET':
                return _Resp(200, [r for r in self.records
                                   if all(r.get(k) == v for k, v in query.items())])
            if method == 'POST':
                rec = {'ttl': 3600, **json}
                if rec not in self.records:
                    self.records.append(rec)
                return _Resp(200, text='')
        if method == 'POST' and path == '/dnszones/example.com/records/delete':
            self.records = [r for r in self.records
                            if not all(r.get(k) == v for k, v in (json or {}).items())
                            or r['type'] == 'SOA']
            return _Resp(200, text='')
        if method == 'POST' and path == '/dnszones/example.com/records/commit':
            self.commits += 1
            self.live = [dict(r) for r in self.records]
            return _Resp(200, text='')
        return _Resp(404, {'error': 'not found'})

    def values(self):
        return [r['data'].strip('"') for r in self.live
                if r['type'] == 'TXT' and r['name'] == '_acme-challenge']


@pytest.fixture
def corenetworks(monkeypatch):
    api = FakeCoreNetworks()
    monkeypatch.setattr(requests, 'post', api.post)
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('corenetworks', {'username': 'u', 'password': 'p'})


def test_corenetworks_lifecycle(corenetworks):
    api, p = corenetworks
    _lifecycle(p, api.values)
    # Every change was committed, and the rest of the zone is intact.
    assert api.records == api.live
    assert [r['name'] for r in api.live] == ['@', 'www']


def test_corenetworks_failed_delete_is_false(corenetworks):
    api, p = corenetworks
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = '/records/delete'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and '500' in msg
    assert api.values() == ['apex']


def test_corenetworks_failed_commit_is_false(corenetworks):
    api, p = corenetworks
    api.fail = '/records/commit'
    ok, msg = p.create_txt_record('example.com', NAME, 'apex')
    assert not ok and 'Commit' in msg
    assert api.values() == []


def test_corenetworks_failed_login_is_false(monkeypatch):
    api = FakeCoreNetworks()
    monkeypatch.setattr(requests, 'post', api.post)
    monkeypatch.setattr(requests, 'request', api)
    p = create_provider('corenetworks', {'username': 'u', 'password': 'wrong'})
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok
