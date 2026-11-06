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
