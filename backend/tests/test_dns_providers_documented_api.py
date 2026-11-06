"""DNS providers against fakes that answer as each provider's public API documentation says."""
import json
import re
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


# --- Hostinger ----------------------------------------------------------------------
# https://developers.hostinger.com/ (openapi/openapi.json, DNS Zone): GET/PUT/DELETE
# /api/dns/v1/zones/{domain}; records grouped by name and type; PUT overwrite=false
# appends, overwrite=true replaces the name+type set; DELETE takes {filters:[{name,type}]}
# and removes the whole set.

class FakeHostinger:
    BASE = 'https://developers.hostinger.com'

    def __init__(self):
        self.zone = [{'name': '@', 'type': 'TXT', 'ttl': 14400,
                      'records': [{'content': 'v=spf1 -all', 'is_disabled': False}]},
                     {'name': 'www', 'type': 'A', 'ttl': 14400,
                      'records': [{'content': '192.0.2.1', 'is_disabled': False}]}]
        self.fail = None

    def _set(self, name, rtype):
        return next((s for s in self.zone if s['name'] == name and s['type'] == rtype), None)

    def __call__(self, method, url, headers=None, json=None, timeout=None):
        path, _ = _split(url, self.BASE)
        if (headers or {}).get('Authorization') != 'Bearer t':
            return _Resp(401, {'message': 'Unauthenticated'})
        if self.fail == method:
            return _Resp(500, {'message': 'Error message'})
        if path == '/api/domains/v1/portfolio' and method == 'GET':
            return _Resp(200, [{'id': 1, 'domain': 'example.com', 'type': 'domain'}])
        if path != '/api/dns/v1/zones/example.com':
            return _Resp(404, {'message': 'Not found'})
        if method == 'GET':
            return _Resp(200, self.zone)
        if method == 'PUT':
            for rr in json['zone']:
                if not rr.get('name') or not rr.get('type') or not rr.get('records'):
                    return _Resp(422, {'message': 'The name field is required.'})
                current = self._set(rr['name'], rr['type'])
                fresh = [{'content': r['content'], 'is_disabled': False} for r in rr['records']]
                if current is None:
                    self.zone.append({'name': rr['name'], 'type': rr['type'],
                                      'ttl': rr.get('ttl', 14400), 'records': fresh})
                elif json.get('overwrite', True):
                    current['records'] = fresh
                else:
                    current['records'] += fresh
                    current['ttl'] = rr.get('ttl', current['ttl'])
            return _Resp(200, {'message': 'Request accepted'})
        if method == 'DELETE':
            for f in json['filters']:
                self.zone = [s for s in self.zone if (s['name'], s['type']) != (f['name'], f['type'])]
            return _Resp(200, {'message': 'Request accepted'})
        return _Resp(405, {'message': 'Method not allowed'})

    def values(self):
        s = self._set('_acme-challenge', 'TXT')
        return [r['content'] for r in s['records']] if s else []


@pytest.fixture
def hostinger(monkeypatch):
    api = FakeHostinger()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('hostinger', {'api_token': 't'})


def test_hostinger_lifecycle(hostinger):
    api, p = hostinger
    _lifecycle(p, api.values)
    assert [(s['name'], s['type']) for s in api.zone] == [('@', 'TXT'), ('www', 'A')]
    assert p.test_connection()[0]


def test_hostinger_failed_delete_is_false(hostinger):
    api, p = hostinger
    for value in ('apex', 'wild'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    api.fail = 'PUT'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and '500' in msg
    api.fail = None
    assert p.delete_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'wild')
    assert not ok and '500' in msg
    assert api.values() == ['wild']


def test_hostinger_failed_read_is_false(hostinger):
    api, p = hostinger
    api.fail = 'GET'
    assert not p.delete_txt_record('example.com', NAME, 'apex')[0]


# --- Epik -----------------------------------------------------------------------------
# https://usersapiv2.epik.com/v2 (embedded OpenAPI 3.1): Authorization: Bearer <key>,
# POST /domains/{D}/records {create_host_records_payload: {HOST, TYPE, DATA, AUX, TTL}},
# GET answers data.records[{id, name, type, data, aux, ttl}] (a registry error in the
# 200 answer carries data.code/description and no records), DELETE ?ID=<id>, errors 4xx.

class FakeEpik:
    BASE = 'https://usersapiv2.epik.com/v2'
    REFUSED = {'errors': [{'code': 3, 'message': 'Unable to perform this operation',
                           'description': 'Error API'}]}

    def __init__(self):
        self.records = [{'id': '1', 'name': '@', 'type': 'TXT', 'data': 'v=spf1 -all', 'aux': 0, 'ttl': 3600}]
        self.next_id = 2
        self.fail = None

    def __call__(self, method, url, params=None, json=None, headers=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update(params or {})
        if (headers or {}).get('Authorization') != 'Bearer k':
            return _Resp(401, {'errors': [{'code': 1, 'message': 'Unauthorized',
                                           'description': 'Signature was not provided or was invalid'}]})
        if self.fail == method:
            return _Resp(400, self.REFUSED)
        if path == '/domains' and method == 'GET':
            return _Resp(200, {'data': [{'name': 'example.com'}]})
        if path != '/domains/example.com/records':
            return _Resp(400, {'errors': [{'code': 2, 'message': 'Invalid parameter',
                                           'description': 'Wrong param DOMAIN'}]})
        if method == 'GET':
            if self.fail == 'registry':
                return _Resp(200, {'data': {'name': 'example.com', 'code': 2400,
                                            'description': 'Registry unavailable'}})
            return _Resp(200, {'data': {'name': 'example.com', 'code': 1000, 'records': self.records}})
        if method == 'POST':
            rec = (json or {}).get('create_host_records_payload')
            if not rec or not rec.get('TYPE') or not rec.get('DATA'):
                return _Resp(400, {'errors': [{'code': 2, 'message': 'Invalid parameter',
                                               'description': 'Wrong param TYPE'}]})
            self.records.append({'id': str(self.next_id), 'name': rec.get('HOST') or '@',
                                 'type': rec['TYPE'], 'data': rec['DATA'],
                                 'aux': rec.get('AUX', 0), 'ttl': rec.get('TTL', 3600)})
            self.next_id += 1
            return _Resp(200, {'code': 1000, 'message': 'Command completed successfully', 'description': None})
        if method == 'DELETE':
            rid = query.get('ID')
            if not any(r['id'] == rid for r in self.records):
                return _Resp(400, self.REFUSED)
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(200, {'code': 1000, 'message': 'Command completed successfully', 'description': None})
        return _Resp(405, self.REFUSED)

    def values(self):
        return [r['data'] for r in self.records if r['type'] == 'TXT' and r['name'] == '_acme-challenge']


@pytest.fixture
def epik(monkeypatch):
    api = FakeEpik()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('epik', {'api_key': 'k'})


def test_epik_lifecycle(epik):
    api, p = epik
    _lifecycle(p, api.values)
    assert [r['id'] for r in api.records] == ['1']


def test_epik_failed_delete_is_false(epik):
    api, p = epik
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and '400' in msg
    assert api.values() == ['apex']


def test_epik_registry_error_in_the_listing_is_false(epik):
    api, p = epik
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'registry'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'Registry unavailable' in msg


def test_epik_key_never_in_the_url(monkeypatch):
    seen = []
    api = FakeEpik()

    def spy(method, url, params=None, **kw):
        seen.append((url, dict(params or {})))
        return api(method, url, params=params, **kw)

    monkeypatch.setattr(requests, 'request', spy)
    p = create_provider('epik', {'api_key': 'k'})
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    assert all('SIGNATURE' not in q for _, q in seen)


# --- Mythic Beasts ------------------------------------------------------------------------
# https://www.mythic-beasts.com/support/api/dnsv2 and /support/api/auth: token from
# POST auth.mythic-beasts.com/login (Basic key:secret, grant_type=client_credentials);
# POST /zones/{z}/records takes zone-file text; GET /zones/{z}/records/{host}/{type} answers
# {records: [{host, ttl, type, data}]}; DELETE on the same path removes every record the
# path and filters (`data`, `ttl`) select, 200 {records_removed: n} even when n is 0.

class FakeMythicBeasts:
    BASE = 'https://api.mythic-beasts.com/dns/v2'
    JSON = {'content-type': 'application/json'}

    def __init__(self, stored_quoted=False):
        self.records = [{'host': '@', 'ttl': 300, 'type': 'TXT', 'data': 'v=spf1 -all'}]
        self.stored_quoted = stored_quoted
        self.fail = None

    def token(self, url, data=None, auth=None, timeout=None):
        if url != 'https://auth.mythic-beasts.com/login' or auth != ('k', 's') \
                or (data or {}).get('grant_type') != 'client_credentials':
            return _Resp(401, {'error': 'invalid_client', 'error_description': 'Invalid credentials.'})
        return _Resp(200, {'access_token': 'bearer-token-value', 'expires_in': 300, 'token_type': 'bearer'})

    def __call__(self, method, url, headers=None, data=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update(params or {})
        if (headers or {}).get('Authorization') != 'Bearer bearer-token-value':
            return _Resp(401, {'error': 'Unauthorized'}, headers=self.JSON)
        if self.fail == method:
            return _Resp(403, {'error': 'Permission denied'}, headers=self.JSON)
        if path == '/zones/example.com/records' and method == 'POST':
            host, ttl, rtype, value = data.split(None, 3)
            if self.stored_quoted:
                value = f'"{value}"'
            self.records.append({'host': host, 'ttl': int(ttl), 'type': rtype, 'data': value})
            return _Resp(200, {'records_added': 1, 'message': '1 records added'}, headers=self.JSON)
        m = re.fullmatch(r'/zones/example\.com/records/([^/]+)/([^/]+)', path)
        if m:
            host, rtype = m.groups()
            sel = [r for r in self.records if r['host'] == host and r['type'] == rtype
                   and all(str(r[k]) == v for k, v in query.items() if k in ('data', 'ttl'))]
            if method == 'GET':
                return _Resp(200, {'records': sel}, headers=self.JSON)
            if method == 'DELETE':
                self.records = [r for r in self.records if r not in sel]
                return _Resp(200, {'records_removed': len(sel),
                                   'message': f'{len(sel)} records removed'}, headers=self.JSON)
        return _Resp(404, {'error': 'Not found'}, headers=self.JSON)

    def values(self):
        return [r['data'].strip('"') for r in self.records if r['host'] == '_acme-challenge']


def _mythicbeasts(monkeypatch, api):
    monkeypatch.setattr(requests, 'post', api.token)
    monkeypatch.setattr(requests, 'request', api)
    return create_provider('mythicbeasts', {'api_key': 'k', 'api_secret': 's'})


@pytest.mark.parametrize('stored_quoted', [False, True])
def test_mythicbeasts_lifecycle(monkeypatch, stored_quoted):
    api = FakeMythicBeasts(stored_quoted)
    _lifecycle(_mythicbeasts(monkeypatch, api), api.values)
    assert [r['host'] for r in api.records] == ['@']


def test_mythicbeasts_failed_delete_is_false(monkeypatch):
    api = FakeMythicBeasts()
    p = _mythicbeasts(monkeypatch, api)
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and '403' in msg
    assert api.values() == ['apex']


def test_mythicbeasts_nothing_removed_is_false(monkeypatch):
    """A 200 removing zero records left the value in the zone."""
    api = FakeMythicBeasts()
    p = _mythicbeasts(monkeypatch, api)
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    real = api.__call__

    def ignore_filter(method, url, params=None, **kw):
        if method == 'DELETE':
            return _Resp(200, {'records_removed': 0, 'message': '0 records removed'}, headers=api.JSON)
        return real(method, url, params=params, **kw)

    monkeypatch.setattr(requests, 'request', ignore_filter)
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'no record removed' in msg


# --- RcodeZero ----------------------------------------------------------------------------
# https://my.rcodezero.at/openapi/rcode0api-v2.json: /api/v2 (v1 deprecated but for ACME),
# GET /zones and /zones/{z}/rrsets paginated (current_page/last_page, names/types filters),
# PATCH rrsets with changetype add|update|delete and records [{content, disabled}];
# only complete rrsets are written; a refusal can answer 200 {status: "failed"}.

class FakeRcodeZero:
    BASE = 'https://my.rcodezero.at/api/v2'

    def __init__(self):
        self.zones = [{'id': i, 'domain': f'zone{i}.test', 'type': 'MASTER'} for i in range(150)]
        self.zones.append({'id': 999, 'domain': 'example.com', 'type': 'MASTER'})
        self.rrsets = [{'name': f'h{i}.example.com.', 'type': 'A', 'ttl': 60,
                        'records': [{'content': '192.0.2.1', 'disabled': False}]} for i in range(3)]
        self.patches = []
        self.fail = None

    def _page(self, items, query):
        size = int(query.get('page_size', 100))
        page = int(query.get('page', 1))
        last = max(1, -(-len(items) // size))
        return _Resp(200, {'current_page': page, 'last_page': last, 'per_page': size, 'total': len(items),
                           'data': items[(page - 1) * size:page * size]})

    def _find(self, name, rtype):
        return next((r for r in self.rrsets if r['name'] == name and r['type'] == rtype), None)

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update({k: str(v) for k, v in (params or {}).items()})
        if (headers or {}).get('Authorization') != 'Bearer tokentoken':
            return _Resp(401, {'message': 'Unauthenticated.'})
        if self.fail == method:
            return _Resp(500, {'message': 'backend down'})
        if method == 'GET' and path == '/zones':
            return self._page(self.zones, query)
        if path == '/zones/example.com/rrsets':
            if method == 'GET':
                sel = [r for r in self.rrsets
                       if ('names' not in query or r['name'] == query['names'])
                       and ('types' not in query or r['type'] == query['types'])]
                return self._page(sel, query)
            if method == 'PATCH':
                self.patches.append(json)
                for rr in json:
                    if rr.get('changetype') not in ('add', 'update', 'delete') or 'ttl' not in rr:
                        return _Resp(422, {'message': 'The given data was invalid.'})
                    if any(not isinstance(r, dict) for r in rr.get('records', [])):
                        return _Resp(422, {'message': 'records.0 must be an object'})
                    current = self._find(rr['name'], rr['type'])
                    if rr['changetype'] == 'add' and current is not None:
                        # Undocumented for an existing rrset: refused so the provider never relies on it.
                        return _Resp(200, {'status': 'failed', 'message': 'RRset already exists'})
                    if current is not None:
                        self.rrsets.remove(current)
                    if rr['changetype'] != 'delete':
                        self.rrsets.append({'name': rr['name'], 'type': rr['type'], 'ttl': rr['ttl'],
                                            'records': [{'disabled': False, **r} for r in rr['records']]})
                return _Resp(200, {'status': 'ok', 'message': 'RRsets updated'})
        return _Resp(404, {'message': 'not found'})

    def values(self):
        rr = self._find(NAME + '.', 'TXT')
        return [r['content'].strip('"') for r in rr['records']] if rr else []


@pytest.fixture
def rcodezero(monkeypatch):
    api = FakeRcodeZero()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('rcodezero', {'api_token': 'tokentoken'})


def test_rcodezero_lifecycle(rcodezero):
    api, p = rcodezero
    _lifecycle(p, api.values)
    assert [c['changetype'] for (c,) in api.patches] == ['add', 'update', 'update', 'delete']
    assert len(api.rrsets) == 3


def test_rcodezero_refused_change_is_false(rcodezero, monkeypatch):
    api, p = rcodezero
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    monkeypatch.setattr(requests, 'request', lambda method, url, **kw: (
        _Resp(200, {'status': 'failed', 'message': 'zone is locked'}) if method == 'PATCH'
        else api(method, url, **kw)))
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'zone is locked' in msg
    assert api.values() == ['apex']


def test_rcodezero_failed_read_writes_nothing(rcodezero):
    api, p = rcodezero
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'GET'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok
    assert len(api.patches) == 1


# --- Vultr ----------------------------------------------------------------------------------
# Vultr API v2 (official generated client docs, vultr/vultr-python-client DnsApi.md and
# models Meta/Links): GET /domains and /domains/{d}/records take per_page and cursor, answer
# meta.links.next (empty on the last page); POST records 201 {record}; DELETE 204.

class _CursorPages:
    CAP = 2  # the server returns at most this many items, whatever per_page asks

    def _page(self, key, items, query):
        start = int(query.get('cursor') or 0)
        chunk = items[start:start + min(self.CAP, int(query.get('per_page', 100)))]
        nxt = str(start + len(chunk)) if start + len(chunk) < len(items) else ''
        return _Resp(200, {key: chunk, 'meta': {'total': len(items), 'links': {'next': nxt, 'prev': ''}}})


class FakeVultr(_CursorPages):
    BASE = 'https://api.vultr.com/v2'

    def __init__(self):
        self.domains = [{'domain': f'other{i}.test'} for i in range(5)] + [{'domain': 'example.com'}]
        self.records = [{'id': f'a-{i}', 'type': 'A', 'name': f'h{i}', 'data': '192.0.2.1', 'ttl': 60}
                        for i in range(5)]
        self.next_id = 1
        self.fail = None

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update({k: str(v) for k, v in (params or {}).items()})
        if (headers or {}).get('Authorization') != 'Bearer k':
            return _Resp(401, {'error': 'Invalid API token.', 'status': 401})
        if self.fail == method:
            return _Resp(500, {'error': 'Internal error', 'status': 500})
        if method == 'GET' and path == '/domains':
            return self._page('domains', self.domains, query)
        if path == '/domains/example.com/records':
            if method == 'GET':
                return self._page('records', self.records, query)
            if method == 'POST':
                rec = {'id': f'id-{self.next_id}', 'priority': 0, **json}
                self.next_id += 1
                self.records.append(rec)
                return _Resp(201, {'record': rec})
        if method == 'DELETE' and path.startswith('/domains/example.com/records/'):
            rid = path.rsplit('/', 1)[1]
            if not any(r['id'] == rid for r in self.records):
                return _Resp(404, {'error': 'Invalid record.', 'status': 404})
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(204)
        return _Resp(404, {'error': 'Not found', 'status': 404})

    def values(self):
        return [r['data'].strip('"') for r in self.records if r['name'] == '_acme-challenge']


@pytest.fixture
def vultr(monkeypatch):
    api = FakeVultr()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('vultr', {'api_key': 'k'})


def test_vultr_lifecycle_reads_every_page(vultr):
    api, p = vultr
    _lifecycle(p, api.values)
    assert len(api.records) == 5


def test_vultr_failed_delete_is_false(vultr):
    api, p = vultr
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'Internal error' in msg
    assert api.values() == ['apex']


def test_vultr_page_bound(vultr, monkeypatch):
    api, p = vultr
    monkeypatch.setattr(type(p), 'MAX_PAGES', 2)
    assert not p.test_connection()[0]


# --- Vercel -----------------------------------------------------------------------------------
# https://vercel.com/docs/rest-api (openapi.json): GET /v5/domains/{d}/records answers
# {records, pagination: {count, next, prev}}, `next` a timestamp for `until` (records created
# before it), 20 per page by default; POST /v2/domains/{d}/records {name, type, value, ttl}
# answers {uid}; DELETE /v2/domains/{d}/records/{id} answers 200 {}.

class FakeVercel:
    BASE = 'https://api.vercel.com'
    CAP = 2

    def __init__(self):
        self.clock = 1_700_000_000_000
        self.records = []
        for i in range(5):
            self._add({'name': f'h{i}', 'type': 'A', 'value': '192.0.2.1', 'ttl': 60})
        self.fail = None

    def _add(self, rec):
        self.clock += 1000
        rec = {'id': f'rec_{self.clock}', 'slug': '', 'creator': 'u', 'created': self.clock,
               'createdAt': self.clock, 'updated': self.clock, 'updatedAt': self.clock, **rec}
        self.records.append(rec)
        return rec

    def __call__(self, method, url, headers=None, json=None, params=None, timeout=None):
        path, query = _split(url, self.BASE)
        query.update({k: str(v) for k, v in (params or {}).items()})
        if (headers or {}).get('Authorization') != 'Bearer tokentoken':
            return _Resp(401, {'error': {'code': 'forbidden', 'message': 'Not authorized'}})
        if self.fail == method:
            return _Resp(500, {'error': {'code': 'internal', 'message': 'Internal error'}})
        if method == 'GET' and path == '/v5/domains':
            return _Resp(200, {'domains': [{'name': 'example.com'}], 'pagination': {'count': 1, 'next': None, 'prev': None}})
        if method == 'GET' and path == '/v5/domains/example.com/records':
            ordered = sorted(self.records, key=lambda r: -r['createdAt'])
            if 'until' in query:
                ordered = [r for r in ordered if r['createdAt'] < int(query['until'])]
            page = ordered[:min(self.CAP, int(query.get('limit', 20)))]
            more = len(ordered) > len(page)
            return _Resp(200, {'records': page, 'pagination': {
                'count': len(page), 'next': page[-1]['createdAt'] if more else None, 'prev': None}})
        if method == 'POST' and path == '/v2/domains/example.com/records':
            if json.get('type') != 'TXT' or 'value' not in json or 'name' not in json:
                return _Resp(400, {'error': {'code': 'bad_request', 'message': 'Invalid request'}})
            return _Resp(200, {'uid': self._add(dict(json))['id']})
        if method == 'DELETE' and path.startswith('/v2/domains/example.com/records/'):
            rid = path.rsplit('/', 1)[1]
            if not any(r['id'] == rid for r in self.records):
                return _Resp(404, {'error': {'code': 'not_found', 'message': 'Record not found'}})
            self.records = [r for r in self.records if r['id'] != rid]
            return _Resp(200, {})
        return _Resp(404, {'error': {'code': 'not_found', 'message': 'Not found'}})

    def values(self):
        return [r['value'] for r in self.records if r['name'] == '_acme-challenge']


@pytest.fixture
def vercel(monkeypatch):
    api = FakeVercel()
    monkeypatch.setattr(requests, 'request', api)
    return api, create_provider('vercel', {'api_token': 'tokentoken'})


def test_vercel_lifecycle_reads_every_page(vercel, monkeypatch):
    api, p = vercel
    for value in ('apex', 'wild'):
        assert p.create_txt_record('example.com', NAME, value)[0]
    # The challenge values come first, newest first: push them past the first page.
    for i in range(3):
        api._add({'name': f'later{i}', 'type': 'A', 'value': '192.0.2.2', 'ttl': 60})
    assert p.delete_txt_record('example.com', NAME, 'apex')[0]
    assert api.values() == ['wild']
    assert p.delete_txt_record('example.com', NAME, 'wild')[0]
    assert api.values() == []
    assert len(api.records) == 8


def test_vercel_failed_delete_is_false(vercel):
    api, p = vercel
    assert p.create_txt_record('example.com', NAME, 'apex')[0]
    api.fail = 'DELETE'
    ok, msg = p.delete_txt_record('example.com', NAME, 'apex')
    assert not ok and 'Internal error' in msg
    assert api.values() == ['apex']
