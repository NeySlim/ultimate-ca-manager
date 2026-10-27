"""#422: RFC 8555 §7.5.2 authorization deactivation through the ACME proxy.

The proxy shares one upstream authorization between the orders of several
clients (#307). A deactivation is passed upstream only when no other pending
local order uses that authorization; otherwise only the requester's order sees
it deactivated. Either way the requester's order is invalid from then on.
"""
import json

import pytest

from models import db, AcmeAccount, AcmeClientOrder
from services.acme.acme_proxy_service import (
    AcmeProxyService,
    ProxyAuthzStateError,
    ProxyOrderNotReadyError,
)
from tests.test_acme_proxy_ownership import (
    _FakeResp,
    _b64,
    _build_jws,
    _generate_rsa_key_and_jwk,
    _get_nonce,
    _register_account,
    proxy_upstream_stub,  # noqa: F401  (fixture)
)

UPSTREAM = 'https://acme-stub.example'
DOMAIN = 'deact.example.com'
AUTHZ_URL = f'{UPSTREAM}/acme/authz/422'
CHALL_URL = f'{AUTHZ_URL}/dns'
ORDER_URL = f'{UPSTREAM}/acme/order/422/a'
OTHER_ORDER_URL = f'{UPSTREAM}/acme/order/422/b'


def _authz(status='pending', chall_status='pending'):
    return {
        'identifier': {'type': 'dns', 'value': DOMAIN},
        'status': status,
        'challenges': [
            {'type': 'dns-01', 'status': chall_status, 'url': CHALL_URL, 'token': 'tok'},
            {'type': 'http-01', 'status': chall_status, 'url': f'{AUTHZ_URL}/http',
             'token': 'tok'},
        ],
    }


def _csr_pem():
    import base64
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    der = base64.urlsafe_b64decode(_csr_b64() + '==')
    return x509.load_der_x509_csr(der).public_bytes(serialization.Encoding.PEM).decode()


def _csr_b64():
    import base64
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    csr = (x509.CertificateSigningRequestBuilder()
           .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, DOMAIN)]))
           .add_extension(x509.SubjectAlternativeName([x509.DNSName(DOMAIN)]), critical=False)
           .sign(ec.generate_private_key(ec.SECP256R1()), hashes.SHA256()))
    der = csr.public_bytes(serialization.Encoding.DER)
    return base64.urlsafe_b64encode(der).rstrip(b'=').decode()


def _seed(order_url=ORDER_URL, account='acct-a', thumb='thumb-a', status='pending',
          deactivated=None):
    order = AcmeClientOrder(
        domains=json.dumps([DOMAIN]),
        environment='staging',
        challenge_type='dns-01',
        status=status,
        order_url=order_url,
        upstream_order_url=order_url,
        upstream_authz_urls=json.dumps([AUTHZ_URL]),
        is_proxy_order=True,
        account_id=account,
        client_jwk_thumbprint=thumb,
        deactivated_authz_urls=json.dumps(deactivated) if deactivated else None,
    )
    db.session.add(order)
    db.session.commit()
    return order.id


@pytest.fixture(autouse=True)
def _drop_orders_created_here(app):
    """Orders a test creates leave with it: later suites check FK integrity."""
    with app.app_context():
        floor = db.session.query(db.func.max(AcmeClientOrder.id)).scalar() or 0
    yield
    with app.app_context():
        db.session.rollback()
        AcmeClientOrder.query.filter(AcmeClientOrder.id > floor).delete(
            synchronize_session=False)
        db.session.commit()


class _Upstream:
    """Records every upstream POST; answers the authz with its current state."""

    def __init__(self, status='pending'):
        self.status = status
        self.calls = []

    def __call__(self, url, payload, *_a, **_k):
        self.calls.append((url, payload))
        if url == AUTHZ_URL:
            if payload == {'status': 'deactivated'}:
                self.status = 'deactivated'
            return _FakeResp(_authz(self.status))
        if url.endswith('/finalize'):
            return _FakeResp({'status': 'processing', 'finalize': url,
                              'authorizations': [AUTHZ_URL]})
        if url in (ORDER_URL, OTHER_ORDER_URL):
            return _FakeResp({'status': 'pending', 'finalize': f'{url}/finalize',
                              'authorizations': [AUTHZ_URL]})
        raise AssertionError(f'unexpected upstream call {url}')

    @property
    def deactivations(self):
        return [c for c in self.calls if c[1] == {'status': 'deactivated'}]


@pytest.fixture
def svc(app, monkeypatch):
    with app.app_context():
        service = AcmeProxyService('https://ucm.example/acme/proxy')
    service.upstream_directory_url = f'{UPSTREAM}/directory'
    upstream = _Upstream()
    monkeypatch.setattr(service, '_post_with_account', upstream)
    monkeypatch.setattr(service, '_get_account_thumbprint', lambda: 'thumb-upstream')
    service.upstream = upstream
    return service


def _deactivate(svc, account='acct-a', thumb='thumb-a'):
    return svc.deactivate_authz(_b64(AUTHZ_URL), requester_account_id=account,
                                requester_thumbprint=thumb)


class TestPassedUpstream:
    def test_sole_order_deactivates_upstream_and_invalidates_the_order(self, app, svc):
        with app.app_context():
            order_id = _seed()
            authz, identifier = _deactivate(svc)
            order = db.session.get(AcmeClientOrder, order_id)
            assert order.status == 'invalid'
            assert order.deactivated_authz_list == [AUTHZ_URL]
        assert svc.upstream.deactivations == [(AUTHZ_URL, {'status': 'deactivated'})]
        assert authz['status'] == 'deactivated'
        assert identifier['value'] == DOMAIN
        # Only dns-01 is exposed, at a proxy URL
        assert [c['type'] for c in authz['challenges']] == ['dns-01']
        assert authz['challenges'][0]['url'].startswith('https://ucm.example/acme/proxy/challenge/')

    @pytest.mark.parametrize('sibling', [
        {'status': 'valid'},
        {'deactivated': [AUTHZ_URL], 'status': 'invalid'},
    ], ids=['sibling-finished', 'sibling-already-deactivated'])
    def test_a_sibling_that_no_longer_needs_the_authz_does_not_block(self, app, svc, sibling):
        with app.app_context():
            _seed()
            _seed(order_url=OTHER_ORDER_URL, account='acct-b', thumb='thumb-b', **sibling)
            _deactivate(svc)
        assert len(svc.upstream.deactivations) == 1

    def test_a_valid_authz_can_be_deactivated(self, app, svc):
        svc.upstream.status = 'valid'
        with app.app_context():
            _seed()
            authz, _ = _deactivate(svc)
        assert authz['status'] == 'deactivated'
        assert len(svc.upstream.deactivations) == 1


class TestSharedAuthorization:
    def test_another_pending_order_keeps_the_upstream_authz(self, app, svc, monkeypatch):
        with app.app_context():
            mine = _seed()
            theirs = _seed(order_url=OTHER_ORDER_URL, account='acct-b', thumb='thumb-b')
            authz, _ = _deactivate(svc)
            assert authz['status'] == 'deactivated'
            assert svc.upstream.deactivations == []
            assert db.session.get(AcmeClientOrder, mine).status == 'invalid'
            other = db.session.get(AcmeClientOrder, theirs)
            assert other.status == 'pending'
            assert other.deactivated_authz_list == []

            # The other client still sees the upstream authz, pending
            monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                                lambda _d: None)
            theirs_view, _ = svc.get_authz(_b64(AUTHZ_URL), requester_account_id='acct-b',
                                           requester_thumbprint='thumb-b')
            mine_view, _ = svc.get_authz(_b64(AUTHZ_URL), requester_account_id='acct-a',
                                         requester_thumbprint='thumb-a')
        assert theirs_view['status'] == 'pending'
        assert mine_view['status'] == 'deactivated'

    def test_reading_a_deactivated_authz_starts_no_dns_automation(self, app, svc, monkeypatch):
        import services.acme.acme_proxy_service as mod
        started = []
        monkeypatch.setattr(mod.threading.Thread, 'start', lambda self_: started.append(self_))
        monkeypatch.setattr('api.v2.acme_domains.find_provider_for_domain',
                            lambda _d: {'provider': object()})
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            _seed(order_url=OTHER_ORDER_URL, account='acct-b', thumb='thumb-b',
                  status='valid')
            view, _ = svc.get_authz(_b64(AUTHZ_URL), requester_account_id='acct-a',
                                    requester_thumbprint='thumb-a')
        assert view['status'] == 'deactivated'
        assert started == []

    def test_a_new_order_of_the_same_client_is_served_over_the_deactivated_one(self, app, svc):
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            fresh = _seed(order_url=OTHER_ORDER_URL)
            order = svc._find_order_by_authz_url(AUTHZ_URL, 'acct-a', 'thumb-a')
            assert order.id == fresh


class TestDnsUpdateRows:
    """The DNS UPDATE expected values of the invalidated order are closed."""

    def _row(self, order_id, thumb):
        from datetime import timedelta
        from models import AcmeProxyDnsChallenge
        from utils.datetime_utils import utc_now
        row = AcmeProxyDnsChallenge(
            order_id=order_id, client_jwk_thumbprint=thumb, identifier=DOMAIN,
            record_name=f'_acme-challenge.{DOMAIN}.', txt_value=thumb,
            zone_name='example.com.', upstream_challenge_url=CHALL_URL,
            expires_at=utc_now() + timedelta(hours=1))
        db.session.add(row)
        db.session.commit()
        return row.id

    def test_only_the_rows_of_the_deactivating_order_are_closed(self, app, svc):
        from models import AcmeProxyDnsChallenge
        with app.app_context():
            mine = self._row(_seed(), 'thumb-a')
            theirs = self._row(
                _seed(order_url=OTHER_ORDER_URL, account='acct-b', thumb='thumb-b'),
                'thumb-b')
            try:
                _deactivate(svc)
                db.session.expire_all()
                assert db.session.get(AcmeProxyDnsChallenge, mine).status == 'closed'
                assert db.session.get(AcmeProxyDnsChallenge, theirs).status == 'pending'
            finally:
                AcmeProxyDnsChallenge.query.filter(
                    AcmeProxyDnsChallenge.id.in_([mine, theirs])).delete(
                        synchronize_session=False)
                db.session.commit()


class TestRefusals:
    @pytest.mark.parametrize('status', ['invalid', 'expired', 'revoked'])
    def test_only_pending_or_valid_can_be_deactivated(self, app, svc, status):
        svc.upstream.status = status
        with app.app_context():
            order_id = _seed()
            with pytest.raises(ProxyAuthzStateError):
                _deactivate(svc)
            order = db.session.get(AcmeClientOrder, order_id)
            assert order.status == 'pending'
            assert order.deactivated_authz_list == []
        assert svc.upstream.deactivations == []

    def test_a_deactivation_already_recorded_answers_after_upstream_expiry(self, app, svc):
        """Kept for this client only, then the shared upstream authz expired."""
        svc.upstream.status = 'invalid'
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            authz, _ = _deactivate(svc)
        assert authz['status'] == 'deactivated'
        assert svc.upstream.deactivations == []

    def test_another_account_cannot_deactivate(self, app, svc):
        with app.app_context():
            _seed()
            with pytest.raises(PermissionError):
                _deactivate(svc, account='acct-x', thumb='thumb-x')
        assert svc.upstream.calls == []

    def test_a_second_deactivation_answers_without_calling_upstream_again(self, app, svc):
        with app.app_context():
            _seed()
            _deactivate(svc)
            authz, _ = _deactivate(svc)
        assert authz['status'] == 'deactivated'
        assert len(svc.upstream.deactivations) == 1


class TestOrderAfterDeactivation:
    def test_order_reads_invalid_while_upstream_is_pending(self, app, svc):
        with app.app_context():
            _seed(order_url=OTHER_ORDER_URL, account='acct-b', thumb='thumb-b')
            _seed()
            _deactivate(svc)
            order = svc.get_order(_b64(ORDER_URL), requester_account_id='acct-a',
                                  requester_thumbprint='thumb-a')
            other = svc.get_order(_b64(OTHER_ORDER_URL), requester_account_id='acct-b',
                                  requester_thumbprint='thumb-b')
        assert order['status'] == 'invalid'
        assert other['status'] == 'pending'

    def test_a_new_local_order_on_the_same_upstream_order_is_served(self, app, svc):
        """A CA hands its pending order back to the proxy's account: the client's
        retry gets a second local row on the same upstream URL."""
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            _seed()
            order = svc.get_order(_b64(ORDER_URL), requester_account_id='acct-a',
                                  requester_thumbprint='thumb-a')
            done = svc.finalize_order(_b64(ORDER_URL), _csr_pem(),
                                      requester_account_id='acct-a',
                                      requester_thumbprint='thumb-a')
        assert order['status'] == 'pending'
        assert done['status'] == 'processing'

    def test_each_client_gets_its_own_row_of_a_shared_upstream_order(self, app, svc):
        with app.app_context():
            _seed()
            _seed(account='acct-b', thumb='thumb-b')
            order = svc.get_order(_b64(ORDER_URL), requester_account_id='acct-b',
                                  requester_thumbprint='thumb-b')
        assert order['status'] == 'pending'

    def test_finalize_is_refused_before_upstream(self, app, svc):
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            with pytest.raises(ProxyOrderNotReadyError):
                svc.finalize_order(_b64(ORDER_URL), 'unused', requester_account_id='acct-a',
                                   requester_thumbprint='thumb-a')
        assert svc.upstream.calls == []

    def test_its_challenge_cannot_be_answered(self, app, svc):
        with app.app_context():
            _seed(deactivated=[AUTHZ_URL], status='invalid')
            with pytest.raises(ProxyAuthzStateError):
                svc.respond_challenge(_b64(CHALL_URL), requester_account_id='acct-a',
                                      requester_thumbprint='thumb-a')
        assert svc.upstream.calls == []


class TestEndpoint:
    """Through the Flask route, with a real signed JWS."""

    def _post(self, client, path, payload, key, kid):
        jws = _build_jws(f'http://localhost{path}', payload, None, key,
                         nonce=_get_nonce(client), use_kid=kid)
        return client.post(path, data=json.dumps(jws), content_type='application/jose+json')

    def _client_and_order(self, app, client):
        key, jwk = _generate_rsa_key_and_jwk()
        kid = _register_account(client, key, jwk)
        with app.app_context():
            account_id = kid.rstrip('/').rsplit('/', 1)[-1]
            account = AcmeAccount.query.filter_by(account_id=account_id).first()
            order_id = _seed(account=account_id, thumb=account.jwk_thumbprint)
        return key, kid, order_id

    def test_deactivation_payload_is_accepted(
            self, app, client, monkeypatch, proxy_upstream_stub):  # noqa: F811
        key, kid, order_id = self._client_and_order(app, client)
        upstream = _Upstream()
        monkeypatch.setattr(AcmeProxyService, '_post_with_account',
                            lambda self, url, payload, *a, **k: upstream(url, payload))
        path = f'/acme/proxy/authz/{_b64(AUTHZ_URL)}'

        r = self._post(client, path, {'status': 'deactivated'}, key, kid)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['status'] == 'deactivated'
        assert len(upstream.deactivations) == 1

        finalize = self._post(client, f'/acme/proxy/order/{_b64(ORDER_URL)}/finalize',
                              {'csr': _csr_b64()}, key, kid)
        assert finalize.status_code == 403
        assert finalize.get_json()['type'].endswith(':orderNotReady')
        with app.app_context():
            assert db.session.get(AcmeClientOrder, order_id).status == 'invalid'

    @pytest.mark.parametrize('payload', [{'status': 'valid'}, {'foo': 1}, {}])
    def test_any_other_payload_stays_malformed(
            self, app, client, monkeypatch, proxy_upstream_stub, payload):  # noqa: F811
        key, kid, order_id = self._client_and_order(app, client)
        upstream = _Upstream()
        monkeypatch.setattr(AcmeProxyService, '_post_with_account',
                            lambda self, url, p, *a, **k: upstream(url, p))
        r = self._post(client, f'/acme/proxy/authz/{_b64(AUTHZ_URL)}', payload, key, kid)
        if payload == {}:
            # An empty object is read as POST-as-GET by the proxy, as before
            assert r.get_json().get('status') == 'pending'
        else:
            assert r.status_code == 400
            assert r.get_json()['type'].endswith(':malformed')
        assert upstream.deactivations == []
        with app.app_context():
            assert db.session.get(AcmeClientOrder, order_id).status == 'pending'
