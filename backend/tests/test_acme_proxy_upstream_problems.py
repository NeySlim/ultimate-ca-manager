"""ACME proxy: upstream problem documents, statuses and Retry-After reach the
client (RFC 8555 §6.6, §6.7, §7.1.3), and the order passes profile and
notAfter upstream (RFC 8555 §7.4, ACME profiles)."""
import base64
import json
from types import SimpleNamespace

import pytest

from api.acme import acme_proxy_api
from models import db, AcmeAccount, AcmeClientOrder
from services.acme.acme_proxy_service import AcmeProxyService
from services.acme.upstream_problem import UpstreamProblem

UPSTREAM = 'https://ca-up.example'
DIRECTORY_URL = f'{UPSTREAM}/directory'
NEW_ORDER_URL = f'{UPSTREAM}/acme/new-order'
ORDER_URL = f'{UPSTREAM}/acme/order/up/1'
FINALIZE_URL = f'{ORDER_URL}/finalize'
AUTHZ_URL = f'{UPSTREAM}/acme/authz/up/1'
CHALL_URL = f'{UPSTREAM}/acme/chall/up/1/dns'
DOMAIN = 'up-problem.example.com'
RATE_LIMITED = {
    'type': 'urn:ietf:params:acme:error:rateLimited',
    'detail': 'too many certificates (5) already issued',
    'status': 429,
}


def _b64(url):
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


class _Resp:
    def __init__(self, payload, status_code=200, headers=None, text=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}
        self.text = text if text is not None else json.dumps(payload)
        self.content = self.text.encode()

    def json(self):
        if self._payload is None:
            raise ValueError('not JSON')
        return self._payload


class _Upstream:
    def __init__(self, answers):
        self.answers = dict(answers)
        self.calls = []

    def __call__(self, url, payload=None, *_a, **_k):
        self.calls.append((url, payload))
        if url not in self.answers:
            raise AssertionError(f'unexpected upstream call to {url}')
        return self.answers[url]


def _directory(**meta):
    return {'newNonce': f'{UPSTREAM}/acme/new-nonce', 'newAccount': f'{UPSTREAM}/acme/new-acct',
            'newOrder': NEW_ORDER_URL, 'revokeCert': f'{UPSTREAM}/acme/revoke',
            'keyChange': f'{UPSTREAM}/acme/key-change', 'meta': meta}


def _svc(monkeypatch, upstream, **meta):
    svc = AcmeProxyService('http://localhost/acme/proxy')
    svc.upstream_directory_url = DIRECTORY_URL
    svc.directory = _directory(**meta)
    svc.account = SimpleNamespace(id=None, preferred_chain='')
    monkeypatch.setattr(svc, '_post_with_account', upstream)
    monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                        lambda *_a, **_k: {'provider': SimpleNamespace(id=1, provider_type='manual')})
    return svc


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
        AcmeAccount.query.filter(AcmeAccount.jwk_thumbprint.like('up-%')).delete(
            synchronize_session=False)
        db.session.commit()


@pytest.fixture
def account(app):
    with app.app_context():
        row = AcmeAccount(jwk='{}', jwk_thumbprint='up-thumb', status='valid')
        db.session.add(row)
        db.session.commit()
        return SimpleNamespace(account_id=row.account_id, thumbprint='up-thumb')


@pytest.fixture
def route(monkeypatch):
    """Drive a proxy route with a verified JWS, a payload and the given service."""
    def _call(client, path, svc, payload, kid=None):
        monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws',
                            lambda: (True, payload, None, None))
        monkeypatch.setattr(acme_proxy_api, '_request_protected_header',
                            lambda: {'kid': kid} if kid else {})
        monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: svc)
        return client.post(path, data='{}', content_type='application/jose+json')
    return _call


def _order_row(account_id=None, thumbprint=None):
    row = AcmeClientOrder(
        domains=json.dumps([DOMAIN]), environment='staging', challenge_type='dns-01',
        status='pending', order_url=ORDER_URL, upstream_order_url=ORDER_URL,
        upstream_authz_urls=json.dumps([AUTHZ_URL]), is_proxy_order=True,
        account_id=account_id, client_jwk_thumbprint=thumbprint)
    db.session.add(row)
    db.session.commit()
    return row


def _kid(account):
    return f'http://localhost/acme/proxy/acct/{account.account_id}'


class TestUpstreamProblemRelayed:
    def test_new_order_rate_limit_reaches_the_client(self, app, client, route, monkeypatch,
                                                     account):
        with app.app_context():
            svc = _svc(monkeypatch, _Upstream({NEW_ORDER_URL: _Resp(
                RATE_LIMITED, 429, {'Retry-After': '3600'})}))
            response = route(client, '/acme/proxy/new-order', svc,
                             {'identifiers': [{'type': 'dns', 'value': DOMAIN}]},
                             kid=_kid(account))

        assert response.status_code == 429
        assert response.headers['Retry-After'] == '3600'
        assert response.headers['Content-Type'] == 'application/problem+json'
        problem = response.get_json()
        assert problem['type'] == RATE_LIMITED['type']
        assert problem['detail'] == RATE_LIMITED['detail']

    def test_new_order_rejected_identifier_keeps_its_subproblems(self, app, client, route,
                                                                 monkeypatch, account):
        rejected = {'type': 'urn:ietf:params:acme:error:rejectedIdentifier',
                    'detail': 'Error creating new order', 'status': 400,
                    'subproblems': [{'type': 'urn:ietf:params:acme:error:caa',
                                     'identifier': {'type': 'dns', 'value': DOMAIN}}]}
        with app.app_context():
            svc = _svc(monkeypatch, _Upstream({NEW_ORDER_URL: _Resp(rejected, 400)}))
            response = route(client, '/acme/proxy/new-order', svc,
                             {'identifiers': [{'type': 'dns', 'value': DOMAIN}]},
                             kid=_kid(account))

        assert response.status_code == 400
        problem = response.get_json()
        assert problem['type'] == rejected['type']
        assert problem['subproblems'] == rejected['subproblems']

    def test_finalize_bad_csr_reaches_the_client(self, app, client, route, monkeypatch):
        bad_csr = {'type': 'urn:ietf:params:acme:error:badCSR',
                   'detail': 'CSR contains unrequested names', 'status': 400}
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        key = ec.generate_private_key(ec.SECP256R1())
        csr = (x509.CertificateSigningRequestBuilder()
               .subject_name(x509.Name([]))
               .add_extension(x509.SubjectAlternativeName([x509.DNSName(DOMAIN)]), False)
               .sign(key, hashes.SHA256()))
        csr_b64 = base64.urlsafe_b64encode(
            csr.public_bytes(serialization.Encoding.DER)).rstrip(b'=').decode()
        with app.app_context():
            _order_row()
            svc = _svc(monkeypatch, _Upstream({
                ORDER_URL: _Resp({'status': 'ready', 'finalize': FINALIZE_URL}),
                FINALIZE_URL: _Resp(bad_csr, 400),
            }))
            response = route(client, f'/acme/proxy/order/{_b64(ORDER_URL)}/finalize', svc,
                             {'csr': csr_b64})

        assert response.status_code == 400
        assert response.get_json()['type'] == bad_csr['type']

    def test_order_read_failure_keeps_status_and_type(self, app, client, route, monkeypatch):
        with app.app_context():
            _order_row()
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _Resp(
                RATE_LIMITED, 429, {'Retry-After': '120'})}))
            response = route(client, f'/acme/proxy/order/{_b64(ORDER_URL)}', svc, '')

        assert response.status_code == 429
        assert response.headers['Retry-After'] == '120'
        assert response.get_json()['type'] == RATE_LIMITED['type']

    def test_authz_upstream_outage_is_not_a_not_found(self, app, client, route, monkeypatch):
        with app.app_context():
            _order_row()
            svc = _svc(monkeypatch, _Upstream({AUTHZ_URL: _Resp(
                None, 503, {'Retry-After': '30'}, text='<html>busy</html>')}))
            response = route(client, f'/acme/proxy/authz/{_b64(AUTHZ_URL)}', svc, '')

        assert response.status_code == 503
        assert response.headers['Retry-After'] == '30'
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:serverInternal'

    @pytest.mark.parametrize('status, name', [(400, 'badNonce'), (403, 'unauthorized')])
    def test_proxy_account_problem_is_not_blamed_on_the_client(self, status, name):
        problem = UpstreamProblem(status, {'type': f'urn:ietf:params:acme:error:{name}',
                                           'detail': 'Account is not valid, has status deactivated'})
        body, status = problem.client_problem()
        assert status == 500
        assert body['type'] == 'urn:ietf:params:acme:error:serverInternal'

    def test_revocation_already_revoked_is_typed(self, app, client, route, monkeypatch):
        already = {'type': 'urn:ietf:params:acme:error:alreadyRevoked',
                   'detail': 'Certificate already revoked', 'status': 400}
        svc = SimpleNamespace(
            account=SimpleNamespace(id=1),
            revoke_certificate=lambda *_a, **_k: _Resp(already, 400))
        cert = SimpleNamespace(id=7, revoked=False)
        monkeypatch.setattr(acme_proxy_api, '_resolve_proxy_certificate', lambda _c: cert)
        monkeypatch.setattr(acme_proxy_api, '_revocation_orders',
                            lambda *_a: [SimpleNamespace(account_id='owner')])
        monkeypatch.setattr(acme_proxy_api, '_decode_b64url', lambda _v: b'der')
        monkeypatch.setattr(acme_proxy_api.x509, 'load_der_x509_certificate',
                            lambda _d: SimpleNamespace())
        response = route(client, '/acme/proxy/revoke-cert', svc, {'certificate': 'x'},
                         kid='http://localhost/acme/proxy/acct/owner')

        assert response.status_code == 400
        assert response.get_json()['type'] == already['type']


class TestRetryAfterOnSuccess:
    def test_processing_order_relays_retry_after(self, app, client, route, monkeypatch):
        with app.app_context():
            _order_row()
            svc = _svc(monkeypatch, _Upstream({ORDER_URL: _Resp(
                {'status': 'processing', 'finalize': FINALIZE_URL}, 200,
                {'Retry-After': '10'})}))
            response = route(client, f'/acme/proxy/order/{_b64(ORDER_URL)}', svc, '')

        assert response.status_code == 200
        assert response.headers['Retry-After'] == '10'

    def test_invalid_retry_after_is_dropped(self):
        resp = _Resp({}, 200, {'Retry-After': 'soon'})
        from services.acme.upstream_problem import retry_after_of
        assert retry_after_of(resp) is None
        assert retry_after_of(_Resp({}, 200, {'Retry-After': 'Wed, 21 Oct 2026 07:28:00 GMT'}))


class TestProfileAndNotAfter:
    def test_profile_and_both_dates_are_forwarded(self, app, client, route, monkeypatch,
                                                  account):
        upstream = _Upstream({NEW_ORDER_URL: _Resp(
            {'status': 'pending', 'identifiers': [{'type': 'dns', 'value': DOMAIN}],
             'authorizations': [AUTHZ_URL], 'finalize': FINALIZE_URL,
             'profile': 'shortlived'}, 201, {'Location': ORDER_URL})})
        with app.app_context():
            svc = _svc(monkeypatch, upstream,
                       profiles={'classic': 'default', 'shortlived': '6 days'})
            response = route(client, '/acme/proxy/new-order', svc, {
                'identifiers': [{'type': 'dns', 'value': DOMAIN}],
                'profile': 'shortlived',
                'notBefore': '2026-11-10T00:00:00Z',
                'notAfter': '2026-11-16T00:00:00Z',
            }, kid=_kid(account))

        assert response.status_code == 201, response.data
        [(_url, sent)] = upstream.calls
        assert sent['profile'] == 'shortlived'
        assert sent['notBefore'].startswith('2026-11-10T00:00:00')
        assert sent['notAfter'].startswith('2026-11-16T00:00:00')

    @pytest.mark.parametrize('meta', [{}, {'profiles': {'classic': 'default'}}])
    def test_profile_the_upstream_does_not_offer_is_refused(self, app, client, route,
                                                            monkeypatch, account, meta):
        upstream = _Upstream({})
        with app.app_context():
            svc = _svc(monkeypatch, upstream, **meta)
            response = route(client, '/acme/proxy/new-order', svc, {
                'identifiers': [{'type': 'dns', 'value': DOMAIN}],
                'profile': 'shortlived',
            }, kid=_kid(account))

        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:invalidProfile'
        assert upstream.calls == []

    def test_non_string_not_after_is_malformed(self, app, client, route, monkeypatch, account):
        with app.app_context():
            svc = _svc(monkeypatch, _Upstream({}))
            response = route(client, '/acme/proxy/new-order', svc, {
                'identifiers': [{'type': 'dns', 'value': DOMAIN}], 'notAfter': 12,
            }, kid=_kid(account))
        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'

    def test_directory_advertises_only_the_upstream_profiles(self, app, monkeypatch):
        with app.app_context():
            svc = _svc(monkeypatch, _Upstream({}), profiles={'classic': 'default'})
            assert svc.get_directory()['meta']['profiles'] == {'classic': 'default'}
            assert 'profiles' not in _svc(monkeypatch, _Upstream({})).get_directory()['meta']

    def test_reused_pending_order_must_carry_the_requested_profile(self, app, monkeypatch):
        with app.app_context():
            _order_row(thumbprint='up-thumb')
            upstream = _Upstream({
                ORDER_URL: _Resp({'status': 'pending', 'profile': 'classic',
                                  'finalize': FINALIZE_URL}),
                NEW_ORDER_URL: _Resp({'status': 'pending', 'authorizations': [AUTHZ_URL],
                                      'finalize': FINALIZE_URL, 'profile': 'shortlived'},
                                     201, {'Location': f'{UPSTREAM}/acme/order/up/2'}),
            })
            svc = _svc(monkeypatch, upstream,
                       profiles={'classic': 'default', 'shortlived': '6 days'})
            svc.new_order([{'type': 'dns', 'value': DOMAIN}], client_thumbprint='up-thumb',
                          profile='shortlived')
            assert [url for url, _p in upstream.calls] == [ORDER_URL, NEW_ORDER_URL]

    def test_reused_pending_order_must_carry_the_requested_not_after(self, app, monkeypatch):
        from datetime import datetime as _dt, timezone as _tz
        with app.app_context():
            _order_row(thumbprint='up-thumb')
            upstream = _Upstream({
                ORDER_URL: _Resp({'status': 'pending', 'finalize': FINALIZE_URL}),
                NEW_ORDER_URL: _Resp({'status': 'pending', 'authorizations': [AUTHZ_URL],
                                      'finalize': FINALIZE_URL,
                                      'notAfter': '2026-12-01T00:00:00Z'},
                                     201, {'Location': f'{UPSTREAM}/acme/order/up/3'}),
            })
            svc = _svc(monkeypatch, upstream)
            order, _order_id = svc.new_order(
                [{'type': 'dns', 'value': DOMAIN}], client_thumbprint='up-thumb',
                not_after=_dt(2026, 12, 1, tzinfo=_tz.utc))
            assert [url for url, _p in upstream.calls] == [ORDER_URL, NEW_ORDER_URL]
            assert order['notAfter'] == '2026-12-01T00:00:00Z'
