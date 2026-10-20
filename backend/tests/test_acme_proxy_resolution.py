"""ACME proxy: resource ownership, exact upstream URL resolution, the Link
header, the identifier a challenge validates, the process caches, the dns-01
thread and the upstream nonce pool."""
import base64
import json
import logging
import threading
from types import SimpleNamespace

import pytest

import services.acme.acme_proxy_service as proxy_mod
from api.acme import acme_proxy_api
from models import db, SystemConfig, AcmeAccount, AcmeClientAccount, AcmeClientOrder
from services.acme import outbound
from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY
from services.acme.acme_proxy_service import (
    AcmeProxyService,
    ProxyChallengeIdentifierError,
    ProxyResourceNotFoundError,
    reset_proxy_caches,
)

UPSTREAM = 'https://ca-c1.example'
DIRECTORY_URL = f'{UPSTREAM}/directory'
ORDER_URL = f'{UPSTREAM}/acme/order/c1/1'
AUTHZ_URL = f'{UPSTREAM}/acme/authz-v3/111'
CHALL_URL = f'{UPSTREAM}/acme/chall-v3/111/Tok'
DOMAIN = 'res-c1.example.com'


def _b64(url):
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


class _Resp:
    def __init__(self, payload, status_code=200, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        return self._payload


class _Upstream:
    """Signed upstream calls, answered per URL and recorded."""

    def __init__(self, answers=None):
        self.answers = dict(answers or {})
        self.calls = []

    def __call__(self, url, payload=None, *_a, **_k):
        self.calls.append(url)
        if url not in self.answers:
            raise AssertionError(f'unexpected upstream call to {url}')
        answer = self.answers[url]
        return answer() if callable(answer) else answer


class _ThreadRecorder:
    created = []

    def __init__(self, target=None, args=(), **_kw):
        _ThreadRecorder.created.append((target, args))
        self.name = ''
        self.daemon = False

    def start(self):
        pass


@pytest.fixture(autouse=True)
def _clean(app):
    with app.app_context():
        AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
        db.session.commit()
    _ThreadRecorder.created = []
    yield
    with app.app_context():
        AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
        AcmeAccount.query.filter(AcmeAccount.account_id.like('c1-%')).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture
def no_threads(monkeypatch):
    monkeypatch.setattr(threading, 'Thread', _ThreadRecorder)
    return _ThreadRecorder.created


def _order(**overrides):
    values = dict(
        domains=json.dumps([DOMAIN]),
        environment='staging',
        challenge_type='dns-01',
        status='pending',
        order_url=ORDER_URL,
        upstream_order_url=ORDER_URL,
        upstream_authz_urls=json.dumps([AUTHZ_URL]),
        is_proxy_order=True,
        account_id=None,
        client_jwk_thumbprint=None,
    )
    values.update(overrides)
    if values['account_id']:
        # PostgreSQL enforces the foreign key to acme_accounts.account_id.
        _local_account(values['account_id'], f"fk-{values['account_id']}")
    row = AcmeClientOrder(**values)
    db.session.add(row)
    db.session.commit()
    return row


def _local_account(account_id, thumbprint):
    """The AcmeAccount row behind account_id; an existing row is kept as is."""
    row = AcmeAccount.query.filter_by(account_id=account_id).first()
    if row is None:
        row = AcmeAccount(account_id=account_id, jwk='{}', jwk_thumbprint=thumbprint)
        db.session.add(row)
        db.session.commit()
    return row


def _svc(monkeypatch, upstream=None):
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = DIRECTORY_URL
    svc.account = SimpleNamespace(id=None, preferred_chain='')
    monkeypatch.setattr(svc, '_post_with_account', upstream or _Upstream())
    return svc


def _pending_authz(value=DOMAIN, chall_url=CHALL_URL):
    return _Resp({
        'status': 'pending',
        'identifier': {'type': 'dns', 'value': value},
        'challenges': [{'type': 'dns-01', 'url': chall_url, 'status': 'pending',
                        'token': 'tok'}],
    })


def _valid_order_view():
    return _Resp({'status': 'valid', 'finalize': f'{ORDER_URL}/finalize'})


# ---------------------------------------------------------------- ownership

class TestOwnership:
    def test_account_bound_order_denies_another_account(self, app, monkeypatch):
        with app.app_context():
            _order(account_id='c1-alice')
            upstream = _Upstream({ORDER_URL: _valid_order_view()})
            svc = _svc(monkeypatch, upstream)
            with pytest.raises(PermissionError):
                svc.get_order(_b64(ORDER_URL), requester_account_id='c1-bob',
                              requester_thumbprint='thumb-bob')
            assert upstream.calls == []
            data = svc.get_order(_b64(ORDER_URL), requester_account_id='c1-alice',
                                 requester_thumbprint='thumb-alice')
            assert data['status'] == 'valid'

    def test_thumbprint_only_order_reconciled_by_kid(self, app, monkeypatch):
        with app.app_context():
            _local_account('c1-alice', 'thumb-c1-alice')
            _local_account('c1-bob', 'thumb-c1-bob')
            _order(client_jwk_thumbprint='thumb-c1-alice')
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _valid_order_view()}))
            data = svc.get_order(_b64(ORDER_URL), requester_account_id='c1-alice')
            assert data['status'] == 'valid'
            with pytest.raises(PermissionError):
                svc.get_order(_b64(ORDER_URL), requester_account_id='c1-bob')

    def test_account_only_order_reconciled_by_thumbprint(self, app, monkeypatch):
        with app.app_context():
            _local_account('c1-alice', 'thumb-c1-alice')
            _local_account('c1-bob', 'thumb-c1-bob')
            _order(account_id='c1-alice')
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _valid_order_view()}))
            data = svc.get_order(_b64(ORDER_URL), requester_thumbprint='thumb-c1-alice')
            assert data['status'] == 'valid'
            with pytest.raises(PermissionError):
                svc.get_order(_b64(ORDER_URL), requester_thumbprint='thumb-c1-bob')

    def test_fully_bound_order_does_not_reconcile(self, app, monkeypatch):
        with app.app_context():
            _local_account('c1-alice', 'thumb-c1-alice')
            _order(account_id='c1-carol', client_jwk_thumbprint='thumb-c1-alice')
            svc = _svc(monkeypatch)
            # The thumbprint names alice, but neither recorded field matches.
            with pytest.raises(PermissionError):
                svc.get_order(_b64(ORDER_URL), requester_account_id='c1-alice')

    def test_unbound_order_served_to_anyone(self, app, monkeypatch):
        with app.app_context():
            _order()
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _valid_order_view()}))
            assert svc.get_order(_b64(ORDER_URL), requester_account_id='c1-x',
                                 requester_thumbprint='t-x')['status'] == 'valid'
            assert svc.get_order(_b64(ORDER_URL))['status'] == 'valid'

    def test_bound_order_without_identity_denied(self, app, monkeypatch):
        with app.app_context():
            _order(account_id='c1-alice', client_jwk_thumbprint='thumb-c1-alice')
            svc = _svc(monkeypatch)
            for resource_call in (
                lambda: svc.get_order(_b64(ORDER_URL)),
                lambda: svc.get_authz(_b64(AUTHZ_URL)),
                lambda: svc.respond_challenge(_b64(f'{AUTHZ_URL}/chall')),
            ):
                with pytest.raises(PermissionError):
                    resource_call()

    def test_denial_is_not_a_not_found(self):
        assert not issubclass(PermissionError, ProxyResourceNotFoundError)
        assert not issubclass(ProxyResourceNotFoundError, PermissionError)


class TestSharedAuthorization:
    def test_each_owner_gets_its_own_order_and_a_third_is_denied(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            _local_account('c1-alice', 'thumb-c1-alice')
            # Bob's order is the lower id; alice's is thumbprint-only and only
            # the reconciliation pass can pick it for a kid-only request.
            bob = _order(account_id='c1-bob', client_jwk_thumbprint='thumb-c1-bob',
                         order_url=f'{ORDER_URL}b', upstream_order_url=f'{ORDER_URL}b')
            alice = _order(client_jwk_thumbprint='thumb-c1-alice')
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: None)
            svc = _svc(monkeypatch, _Upstream({AUTHZ_URL: lambda: _pending_authz()}))
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')

            svc.get_authz(_b64(AUTHZ_URL), requester_account_id='c1-alice')
            svc.get_authz(_b64(AUTHZ_URL), requester_account_id='c1-bob',
                          requester_thumbprint='thumb-c1-bob')

            assert svc._resolve_challenge_order(
                CHALL_URL, 'c1-alice', None)[0].id == alice.id
            assert svc._resolve_challenge_order(
                CHALL_URL, 'c1-bob', 'thumb-c1-bob')[0].id == bob.id
            with pytest.raises(PermissionError):
                svc.get_authz(_b64(AUTHZ_URL), requester_account_id='c1-carol',
                              requester_thumbprint='thumb-c1-carol')


# ------------------------------------------------------- URL resolution

class TestExactResolution:
    def test_forged_prefix_of_a_recorded_authz_is_not_found(self, app, monkeypatch):
        with app.app_context():
            _order(upstream_authz_urls=json.dumps([f'{UPSTREAM}/acme/authz-v3/999']))
            upstream = _Upstream()
            svc = _svc(monkeypatch, upstream)
            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_authz(_b64(f'{UPSTREAM}/acme/authz-v3/99'))
            assert svc._orders_by_authz_url(f'{UPSTREAM}/acme/authz-v3/99') == []
            assert upstream.calls == []

    def test_like_wildcards_in_an_authz_url_do_not_match(self, app, monkeypatch):
        with app.app_context():
            _order(upstream_authz_urls=json.dumps([f'{UPSTREAM}/acme/authz-v3/a1b']))
            svc = _svc(monkeypatch)
            assert svc._orders_by_authz_url(f'{UPSTREAM}/acme/authz-v3/a_b') == []
            assert svc._orders_by_authz_url(f'{UPSTREAM}/acme/authz-v3/a%') == []

    def test_challenge_nested_under_its_authz_resolves_locally(self, app, monkeypatch):
        nested = f'{AUTHZ_URL}/dns-chall'
        with app.app_context():
            row = _order(account_id='c1-alice')
            order, domain, authz_url = _svc(monkeypatch)._resolve_challenge_order(
                nested, 'c1-alice', None)
            assert (order.id, domain, authz_url) == (row.id, DOMAIN, AUTHZ_URL)

    def test_no_approximate_fallback_for_an_unknown_challenge(
            self, app, monkeypatch, no_threads):
        """A pending order of the same requester on the same host is no match."""
        with app.app_context():
            _order(account_id='c1-alice')
            upstream = _Upstream({CHALL_URL: _Resp(
                {'type': 'dns-01', 'url': CHALL_URL, 'status': 'pending', 'token': 't'})})
            svc = _svc(monkeypatch, upstream)
            with pytest.raises(ProxyResourceNotFoundError, match='Link'):
                svc.respond_challenge(_b64(CHALL_URL), requester_account_id='c1-alice')
            assert no_threads == []

    def test_stale_cache_entry_is_ignored(self, app, monkeypatch, no_threads):
        """An entry whose order is gone is dropped whole: the Link fallback
        decides the order and the authorization."""
        with app.app_context():
            row = _order(account_id='c1-alice')
            key = AcmeProxyService._challenge_cache_key(CHALL_URL, 'c1-alice', None)
            proxy_mod._challenge_order_cache.put(
                key, (row.id + 1000, 'stale.example.org', f'{UPSTREAM}/acme/authz-v3/stale'))
            upstream = _Upstream({CHALL_URL: _Resp(
                {'type': 'dns-01', 'url': CHALL_URL, 'status': 'pending', 'token': 't'},
                headers={'Link': f'<{AUTHZ_URL}>;rel="up"'})})
            svc = _svc(monkeypatch, upstream)
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': object()})
            data, _link = svc.respond_challenge(
                _b64(CHALL_URL), requester_account_id='c1-alice')

            assert data['status'] == 'processing'
            [(_target, args)] = no_threads
            assert (args[3], args[4], args[5]) == (DOMAIN, row.id, AUTHZ_URL)
            assert proxy_mod._challenge_order_cache.get(key)[0] == row.id


class TestLinkHeader:
    @pytest.mark.parametrize('header, expected', [
        (f'<{UPSTREAM}/dir>;rel="index", <{AUTHZ_URL}>;rel="up"', AUTHZ_URL),
        (f'<{UPSTREAM}/dir>;rel="index", <{AUTHZ_URL}>;rel=up', AUTHZ_URL),
        (f"<{AUTHZ_URL}>; rel='UP'", AUTHZ_URL),
        (f'<{UPSTREAM}/dir>; title="a, b"; rel="index", <{AUTHZ_URL}>; rel="up"',
         AUTHZ_URL),
        (f'<{UPSTREAM}/dir>;rel="index"', None),
        (f'<{AUTHZ_URL}>;rel="upstream"', None),
        ('', None),
        (None, None),
    ])
    def test_rel_up_is_selected(self, header, expected):
        assert AcmeProxyService._upstream_authz_url_from_link(header) == expected


# ------------------------------------------------------ challenge identifier

class TestChallengeIdentifier:
    _MULTI = json.dumps(['one.res-c1.example.com', 'two.res-c1.example.com'])

    def _pending_challenge(self, link=True):
        headers = {'Link': f'<{AUTHZ_URL}>;rel="up"'} if link else {}
        return _Resp({'type': 'dns-01', 'url': CHALL_URL, 'status': 'pending',
                      'token': 'tok'}, headers=headers)

    def test_multi_domain_reads_the_upstream_authorization(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            _order(domains=self._MULTI)
            upstream = _Upstream({
                CHALL_URL: self._pending_challenge(),
                AUTHZ_URL: _pending_authz('two.res-c1.example.com'),
            })
            svc = _svc(monkeypatch, upstream)
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda *_a, **_k: {'provider': object()})
            data, _link = svc.respond_challenge(_b64(CHALL_URL))

            assert data['status'] == 'processing'
            assert upstream.calls == [CHALL_URL, AUTHZ_URL]
            assert [args[3] for _t, args in no_threads] == ['two.res-c1.example.com']

    def test_foreign_identifier_on_the_authorization_is_not_found(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            row = _order(domains=self._MULTI)
            upstream = _Upstream({
                CHALL_URL: self._pending_challenge(),
                AUTHZ_URL: _pending_authz('victim.example.org'),
            })
            svc = _svc(monkeypatch, upstream)
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
            with pytest.raises(ProxyResourceNotFoundError):
                svc.respond_challenge(_b64(CHALL_URL))
            assert no_threads == []
            db.session.refresh(row)
            assert row.challenges_dict == {}

    def test_unknown_authorization_raises_the_typed_error(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            row = _order(domains=self._MULTI)
            svc = _svc(monkeypatch, _Upstream({
                CHALL_URL: self._pending_challenge(link=False)}))
            monkeypatch.setattr(svc, '_resolve_challenge_order',
                                lambda *_a, **_k: (row, None, None))
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
            with pytest.raises(ProxyChallengeIdentifierError):
                svc.respond_challenge(_b64(CHALL_URL))
            assert no_threads == []

    def test_endpoint_reports_the_typed_error_as_server_internal(
            self, app, client, monkeypatch, no_threads):
        with app.app_context():
            row_id = _order(domains=self._MULTI).id
            svc = _svc(monkeypatch, _Upstream({
                CHALL_URL: self._pending_challenge(link=False)}))
            monkeypatch.setattr(
                svc, '_resolve_challenge_order',
                lambda *_a, **_k: (db.session.get(AcmeClientOrder, row_id), None, None))
            monkeypatch.setattr(svc, '_get_account_thumbprint', lambda: 'up')
        monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws',
                            lambda: (True, {}, None, None))
        monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: svc)

        response = client.post(f'/acme/proxy/challenge/{_b64(CHALL_URL)}', data='{}',
                               content_type='application/jose+json')
        assert response.status_code == 500
        problem = response.get_json()
        assert problem['type'] == 'urn:ietf:params:acme:error:serverInternal'
        assert 'identifier' in problem['detail']
        assert problem['detail'] != 'Internal server error'

    def test_authz_identifier_outside_the_order_is_not_found(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            row = _order()
            found = []
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda d, *_a, **_k: found.append(d))
            svc = _svc(monkeypatch, _Upstream({AUTHZ_URL: _pending_authz('other.example.org')}))
            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_authz(_b64(AUTHZ_URL))
            assert no_threads == [] and found == []
            db.session.refresh(row)
            assert row.challenges_dict == {}

    def test_wildcard_and_case_are_ignored_for_the_order_match(
            self, app, monkeypatch, no_threads):
        with app.app_context():
            _order(domains=json.dumps(['*.Res-C1.example.com']))
            svc = _svc(monkeypatch, _Upstream({AUTHZ_URL: _Resp({
                'status': 'valid', 'challenges': [],
                'identifier': {'type': 'dns', 'value': '*.res-c1.EXAMPLE.com'}})}))
            authz, _identifier = svc.get_authz(_b64(AUTHZ_URL))
            assert authz['status'] == 'valid'


# ------------------------------------------------------------- certificates

class TestCertificateFallback:
    CERT_URL = f'{UPSTREAM}/acme/cert/unpersisted'

    def test_scan_is_bounded_and_restricted_to_the_requester(self, app, monkeypatch):
        with app.app_context():
            rows = {}
            for index in range(40):
                owner = ('c1-req', 'thumb-req') if index % 4 == 0 else \
                    (None, None) if index % 4 == 1 else \
                    ('c1-other', 'thumb-other') if index % 4 == 2 else \
                    (None, 'thumb-req')
                url = f'{UPSTREAM}/acme/order/scan/{index}'
                rows[url] = _order(order_url=url, upstream_order_url=url,
                                   account_id=owner[0], client_jwk_thumbprint=owner[1])
            upstream = _Upstream({url: _Resp({'status': 'valid',
                                              'certificate': f'{self.CERT_URL}x'})
                                  for url in rows})
            svc = _svc(monkeypatch, upstream)

            with pytest.raises(ProxyResourceNotFoundError):
                svc.get_certificate(_b64(self.CERT_URL), requester_account_id='c1-req',
                                    requester_thumbprint='thumb-req')

            eligible = sorted((r for r in rows.values()
                               if r.account_id != 'c1-other'),
                              key=lambda r: r.id, reverse=True)[:25]
            assert len(upstream.calls) == 25
            assert upstream.calls == [r.upstream_order_url for r in eligible]

    def test_exact_upstream_match_is_returned_and_persisted(self, app, monkeypatch):
        with app.app_context():
            row = _order(account_id='c1-req')
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _Resp(
                {'status': 'valid', 'certificate': self.CERT_URL})}))
            found = svc._find_order_for_certificate(
                self.CERT_URL, requester_account_id='c1-req')
            assert found.id == row.id
            db.session.refresh(row)
            assert row.certificate_url == self.CERT_URL


# ------------------------------------------------------------------- caches

@pytest.fixture
def fake_pool(monkeypatch):
    pool = {}

    def _pop(directory_url):
        nonces = pool.get(directory_url) or []
        return nonces.pop() if nonces else None

    def _push(directory_url, nonce):
        pool.setdefault(directory_url, []).append(nonce)

    monkeypatch.setattr(outbound, 'nonce_pool_pop', _pop)
    monkeypatch.setattr(outbound, 'nonce_pool_push', _push)
    monkeypatch.setattr(outbound, 'reset_nonce_pool', pool.clear)
    return pool


@pytest.fixture
def stub_directory(app, monkeypatch):
    from tests.acme_proxy_upstream_stub import stub_acme_proxy_upstream

    gets = []
    directory = {'newNonce': f'{UPSTREAM}/acme/new-nonce',
                 'newOrder': f'{UPSTREAM}/acme/new-order', 'meta': {}}
    stub_acme_proxy_upstream(monkeypatch, directory)
    real_get = proxy_mod.ssrf_protection.safe_request_get

    def _counting_get(*args, **kwargs):
        gets.append(args[0] if args else kwargs.get('url'))
        return real_get(*args, **kwargs)

    monkeypatch.setattr('utils.ssrf_protection.safe_request_get', _counting_get)
    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(directory_url=DIRECTORY_URL).delete()
        account = AcmeClientAccount(directory_url=DIRECTORY_URL, label='C1 stub',
                                    email='c1@example.com')
        db.session.add(account)
        db.session.commit()
        db.session.add(SystemConfig(key=PROXY_ACCOUNT_ID_KEY, value=str(account.id),
                                    description='c1'))
        db.session.commit()
        account_id = account.id
    yield SimpleNamespace(gets=gets, account_id=account_id)
    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(directory_url=DIRECTORY_URL).delete()
        db.session.commit()


class TestCaches:
    def test_directory_cold_and_warm_answer_the_same(self, client, stub_directory):
        first = client.get('/acme/proxy/directory')
        second = client.get('/acme/proxy/directory')
        assert first.status_code == second.status_code == 200
        assert first.get_json() == second.get_json()
        assert stub_directory.gets == [DIRECTORY_URL]

        reset_proxy_caches()
        third = client.get('/acme/proxy/directory')
        assert third.get_json() == first.get_json()
        assert stub_directory.gets == [DIRECTORY_URL, DIRECTORY_URL]

    def test_directory_cache_is_keyed_by_directory_url(self, app, stub_directory):
        with app.app_context():
            svc = AcmeProxyService('https://ucm.example/acme/proxy')
            svc._ensure_directory()
            other = AcmeProxyService('https://ucm.example/acme/proxy')
            other.upstream_directory_url = f'{UPSTREAM}/other/directory'
            other._ensure_directory()
        assert stub_directory.gets == [DIRECTORY_URL, f'{UPSTREAM}/other/directory']

    def test_reset_twice_empties_everything(self, app, stub_directory, fake_pool):
        with app.app_context():
            svc = AcmeProxyService('https://ucm.example/acme/proxy')
            svc._ensure_directory()
        proxy_mod._finalize_url_cache.put(ORDER_URL, f'{ORDER_URL}/finalize')
        proxy_mod._challenge_order_cache.put('k', (1, DOMAIN, AUTHZ_URL))
        outbound.nonce_pool_push(DIRECTORY_URL, 'pooled')

        reset_proxy_caches()
        reset_proxy_caches()

        assert proxy_mod._directory_cache.get(DIRECTORY_URL) is None
        assert proxy_mod._finalize_url_cache.get(ORDER_URL) is None
        assert proxy_mod._challenge_order_cache.get('k') is None
        assert outbound.nonce_pool_pop(DIRECTORY_URL) is None

    def test_cache_bound_evicts_the_oldest(self):
        cache = proxy_mod._TtlCache(ttl_seconds=60, max_entries=2)
        cache.put('a', 1)
        cache.put('b', 2)
        cache.put('c', 3)
        assert (cache.get('a'), cache.get('b'), cache.get('c')) == (None, 2, 3)

    def test_cache_entries_expire(self, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(proxy_mod.time, 'monotonic', lambda: clock[0])
        cache = proxy_mod._TtlCache(ttl_seconds=10, max_entries=4)
        cache.put('a', 1)
        clock[0] += 9
        assert cache.get('a') == 1
        clock[0] += 2
        assert cache.get('a') is None

    def test_finalize_cold_and_warm_reach_the_same_finalize_url(
            self, app, monkeypatch):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        csr_pem = (x509.CertificateSigningRequestBuilder()
                   .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)]))
                   .sign(key, hashes.SHA256())
                   .public_bytes(serialization.Encoding.PEM).decode())
        finalize_url = f'{UPSTREAM}/acme/finalize/c1/1'
        processing = _Resp({'status': 'processing', 'finalize': finalize_url})
        with app.app_context():
            _order()
            upstream = _Upstream({ORDER_URL: processing, finalize_url: processing})
            svc = _svc(monkeypatch, upstream)

            cold = svc.finalize_order(_b64(ORDER_URL), csr_pem)
            assert upstream.calls == [ORDER_URL, finalize_url]
            upstream.calls.clear()
            warm = svc.finalize_order(_b64(ORDER_URL), csr_pem)
            assert upstream.calls == [finalize_url]
            assert cold == warm


class TestNoncePool:
    def _svc(self, monkeypatch):
        svc = AcmeProxyService.__new__(AcmeProxyService)
        svc.upstream_directory_url = DIRECTORY_URL
        svc.directory = {'newNonce': f'{UPSTREAM}/acme/new-nonce'}
        svc.verify_ssl = True
        svc._account = None
        monkeypatch.setattr(svc, '_detect_key_algorithm', lambda: 'ES256')
        monkeypatch.setattr(svc, '_sign_data', lambda _data: b'sig')
        return svc

    def test_empty_pool_fetches_a_fresh_nonce(self, app, monkeypatch, fake_pool):
        fetched = []
        monkeypatch.setattr(outbound, 'fetch_nonce',
                            lambda url, **_k: fetched.append(url) or 'fresh')
        with app.app_context():
            svc = self._svc(monkeypatch)
            assert svc._get_nonce() == 'fresh'
            outbound.nonce_pool_push(DIRECTORY_URL, 'pooled')
            assert svc._get_nonce() == 'pooled'
        assert fetched == [f'{UPSTREAM}/acme/new-nonce']

    @pytest.mark.parametrize('status, pooled', [(200, ['n2']), (201, ['n2']),
                                                (400, []), (404, ['n2'])])
    def test_reply_nonce_is_pooled_except_on_400(self, app, monkeypatch, fake_pool,
                                                 status, pooled):
        monkeypatch.setattr(
            proxy_mod.ssrf_protection, 'safe_request_post',
            lambda *_a, **_k: _Resp({}, status_code=status,
                                    headers={'Replay-Nonce': 'n2'}))
        with app.app_context():
            svc = self._svc(monkeypatch)
            svc._sign_and_post(f'{UPSTREAM}/acme/order/x', '', 'n1', kid='k')
        assert fake_pool.get(DIRECTORY_URL, []) == pooled


# ----------------------------------------------------------------- thread

class TestDns01Thread:
    def _patch_dns(self, monkeypatch):
        from unittest.mock import MagicMock

        provider_model = SimpleNamespace(id=1, provider_type='manual', credentials='{}')
        monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                            lambda *_a, **_k: {'provider': provider_model})
        provider = MagicMock()
        provider.get_acme_challenge_name.side_effect = lambda d: f'_acme-challenge.{d}'
        monkeypatch.setattr('services.acme.dns_providers.create_provider',
                            lambda *_a, **_k: provider)
        monkeypatch.setattr(proxy_mod, 'wait_for_txt',
                            lambda *_a, **_k: {'ok': True, 'missing': [], 'waited': 0})
        return provider

    def test_thread_signs_with_its_own_service(self, app, monkeypatch, stub_directory):
        self._patch_dns(monkeypatch)
        signers = []

        def _post(service, url, payload):
            signers.append((service, url))
            return _Resp({'status': 'processing'})

        monkeypatch.setattr(AcmeProxyService, '_post_with_account', _post)
        with app.app_context():
            row = _order()
            svc = AcmeProxyService('https://ucm.example/acme/proxy')
            order_id = row.id
        svc._bg_respond_challenge(app, CHALL_URL, 'tok.up', DOMAIN, order_id, AUTHZ_URL)

        assert len(signers) == 1
        worker, url = signers[0]
        assert url == CHALL_URL
        assert worker is not svc
        assert worker.base_url == svc.base_url
        assert worker._account_id == stub_directory.account_id
        with app.app_context():
            entry = db.session.get(AcmeClientOrder, order_id).challenges_dict[CHALL_URL]
            assert entry['status'] == 'submitted'

    def test_interleaved_threads_on_the_same_domain(self, app, monkeypatch, caplog,
                                                    stub_directory):
        """The first thread pauses inside its upstream call while the second runs
        to completion. The test SQLite engine shares one connection, so the two
        threads interleave between statements rather than run truly at once."""
        self._patch_dns(monkeypatch)
        challenges = [f'{UPSTREAM}/acme/chall-v3/p{index}/x' for index in range(2)]
        sessions, paused, resume = {}, threading.Event(), threading.Event()

        def _post(service, url, _payload):
            sessions[url] = (db.session(), service)
            if url == challenges[0]:
                paused.set()
                assert resume.wait(30)
            return _Resp({'status': 'processing'})

        monkeypatch.setattr(AcmeProxyService, '_post_with_account', _post)
        with app.app_context():
            ids = [_order(order_url=f'{ORDER_URL}p{index}',
                          upstream_order_url=f'{ORDER_URL}p{index}').id
                   for index in range(2)]
            svc = AcmeProxyService('https://ucm.example/acme/proxy')

        caplog.set_level(logging.ERROR, logger=proxy_mod.__name__)
        first, second = (threading.Thread(target=svc._bg_respond_challenge,
                                          args=(app, chall, 'tok.up', DOMAIN, order_id))
                         for chall, order_id in zip(challenges, ids))
        first.start()
        assert paused.wait(30)
        second.start()
        second.join(30)
        resume.set()
        first.join(30)

        assert not [r for r in caplog.records if 'ACME Proxy BG' in r.getMessage()]
        (session_a, worker_a), (session_b, worker_b) = (sessions[c] for c in challenges)
        assert session_a is not session_b
        assert worker_a is not worker_b and svc not in (worker_a, worker_b)
        with app.app_context():
            for chall, order_id in zip(challenges, ids):
                state = db.session.get(AcmeClientOrder, order_id).challenges_dict
                assert state[chall]['status'] == 'submitted'


class TestOrderUrlRewrite:
    CERT_URL = f'{UPSTREAM}/acme/cert/rewrite'

    def _csr(self):
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.x509.oid import NameOID

        key = ec.generate_private_key(ec.SECP256R1())
        return (x509.CertificateSigningRequestBuilder()
                .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)]))
                .sign(key, hashes.SHA256())
                .public_bytes(serialization.Encoding.PEM).decode())

    @pytest.mark.parametrize('call', ['get_order', 'finalize_order'])
    def test_order_view_points_at_the_proxy(self, app, monkeypatch, call):
        finalize_url = f'{ORDER_URL}/finalize'
        view = {'status': 'valid', 'finalize': finalize_url,
                'certificate': self.CERT_URL, 'authorizations': [AUTHZ_URL]}
        with app.app_context():
            row = _order()
            upstream = _Upstream({ORDER_URL: lambda: _Resp(dict(view)),
                                  finalize_url: lambda: _Resp(dict(view))})
            svc = _svc(monkeypatch, upstream)
            if call == 'get_order':
                data = svc.get_order(_b64(ORDER_URL))
            else:
                data = svc.finalize_order(_b64(ORDER_URL), self._csr())

            base = 'https://ucm.example/acme/proxy'
            assert data['finalize'] == f'{base}/order/{_b64(ORDER_URL)}/finalize'
            assert data['certificate'] == f'{base}/cert/{_b64(self.CERT_URL)}'
            assert data['authorizations'] == [f'{base}/authz/{_b64(AUTHZ_URL)}']
            db.session.refresh(row)
            assert row.certificate_url == self.CERT_URL

    def test_new_order_view_points_at_the_proxy(self, app, monkeypatch):
        with app.app_context():
            svc = _svc(monkeypatch)
            data, order_id = svc._rewrite_order_response(
                {'status': 'pending', 'finalize': f'{ORDER_URL}/finalize',
                 'authorizations': [AUTHZ_URL]}, ORDER_URL)
        assert order_id == _b64(ORDER_URL)
        assert data['authorizations'] == [
            f'https://ucm.example/acme/proxy/authz/{_b64(AUTHZ_URL)}']
        assert data['finalize'] == f'https://ucm.example/acme/proxy/order/{order_id}/finalize'


def test_proxy_id_is_the_inverse_of_decode(app):
    with app.app_context():
        svc = AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = DIRECTORY_URL
    for url in (f'{UPSTREAM}/a', f'{UPSTREAM}/ab', f'{UPSTREAM}/abc', f'{UPSTREAM}/é'):
        encoded = svc._proxy_id(url)
        assert '=' not in encoded
        assert svc._decode_proxy_id(encoded) == url
