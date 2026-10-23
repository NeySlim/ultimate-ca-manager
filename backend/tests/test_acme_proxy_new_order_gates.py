"""Order of the proxy new-order gates: shape, identifiers, wildcard policy and
challenge type first, then the kid signature, then the account status, and
only then the upstream service."""
import base64
import json
from unittest.mock import MagicMock

import pytest

from api.acme import acme_proxy_api
from models import db, AcmeAccount, AcmeClientOrder, AcmeDomain, DnsProvider

_DOMAIN = 'gates-wc.test'
_GHOST_KID = 'http://localhost/acme/proxy/acct/ghost-account-id'


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b'=').decode()


def _rsa_key_and_jwk():
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    numbers = key.public_key().public_numbers()

    def as_b64(value):
        return _b64(value.to_bytes((value.bit_length() + 7) // 8, 'big'))

    return key, {'kty': 'RSA', 'n': as_b64(numbers.n), 'e': as_b64(numbers.e)}


def _signed_jws(url, payload, key, jwk=None, kid=None, nonce='n'):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import padding

    protected = {'alg': 'RS256', 'nonce': nonce, 'url': url}
    if kid:
        protected['kid'] = kid
    else:
        protected['jwk'] = jwk
    protected_b64 = _b64(json.dumps(protected).encode())
    payload_b64 = _b64(json.dumps(payload).encode())
    signature = key.sign(f'{protected_b64}.{payload_b64}'.encode(),
                         padding.PKCS1v15(), hashes.SHA256())
    return {'protected': protected_b64, 'payload': payload_b64,
            'signature': _b64(signature)}


def _fresh_nonce(app):
    from services.acme import AcmeService
    with app.app_context():
        return AcmeService().generate_nonce()


def _post(client, body):
    return client.post('/acme/proxy/new-order', data=json.dumps(body),
                       content_type='application/jose+json')


@pytest.fixture
def service_factory(monkeypatch):
    """Stands in for the upstream service; a gate that holds never reaches it."""
    svc = MagicMock()
    svc.new_order.return_value = ({'status': 'pending'}, 'order-id')
    factory = MagicMock(return_value=svc)
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', factory)
    return factory


@pytest.fixture
def verified(monkeypatch):
    """Pretend the JWS verified, with the given payload and protected header."""
    def _set(payload, protected=None):
        monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws',
                            lambda: (True, payload, None, None))
        monkeypatch.setattr(acme_proxy_api, '_request_protected_header',
                            lambda: dict(protected or {}))
    return _set


@pytest.fixture
def local_account(app):
    created = []

    def _make(status='valid'):
        _key, jwk = _rsa_key_and_jwk()
        from services.acme.jwk_thumbprint import jwk_thumbprint
        account = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=jwk_thumbprint(jwk),
                              status=status)
        db.session.add(account)
        db.session.commit()
        created.append(account.id)
        return account

    with app.app_context():
        yield _make
        for account_id in created:
            row = db.session.get(AcmeAccount, account_id)
            if row is not None:
                db.session.delete(row)
        db.session.commit()


@pytest.fixture
def wildcard_entry(app):
    """acme_domains entry for _DOMAIN with the wildcard switch set by the test."""
    with app.app_context():
        provider = DnsProvider(name='gates-wc', provider_type='manual',
                               zones=json.dumps([_DOMAIN]))
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id

    def _set(allowed):
        with app.app_context():
            AcmeDomain.query.filter_by(domain=_DOMAIN).delete()
            if allowed is not None:
                db.session.add(AcmeDomain(domain=_DOMAIN, dns_provider_id=provider_id,
                                          is_wildcard_allowed=allowed))
            db.session.commit()

    yield _set
    with app.app_context():
        AcmeDomain.query.filter_by(domain=_DOMAIN).delete()
        DnsProvider.query.filter_by(id=provider_id).delete()
        db.session.commit()


class TestKidIsRequired:
    def test_jwk_signed_new_order_is_malformed_and_creates_nothing(
            self, app, client, service_factory):
        key, jwk = _rsa_key_and_jwk()
        with app.app_context():
            before = AcmeClientOrder.query.count()
        body = _signed_jws('http://localhost/acme/proxy/new-order',
                           {'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                           key, jwk=jwk, nonce=_fresh_nonce(app))
        response = _post(client, body)

        assert response.status_code == 400
        problem = response.get_json()
        assert problem['type'] == 'urn:ietf:params:acme:error:malformed'
        assert 'kid' in problem['detail']
        service_factory.assert_not_called()
        with app.app_context():
            assert AcmeClientOrder.query.count() == before

    def test_kid_of_a_valid_account_reaches_the_service(
            self, app, client, service_factory, verified, local_account):
        account = local_account('valid')
        verified({'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                 {'kid': f'http://localhost/acme/proxy/acct/{account.account_id}'})
        response = _post(client, {})

        assert response.status_code == 201, response.data
        service_factory.assert_called_once()
        kwargs = service_factory.return_value.new_order.call_args.kwargs
        assert kwargs['client_thumbprint'] == account.jwk_thumbprint


class TestWildcardPolicyComesBeforeKid:
    @pytest.mark.parametrize('allowed, refused', [
        (False, True), (True, False), (None, False),
    ])
    def test_jwk_signed_wildcard(self, app, client, service_factory, wildcard_entry,
                                 allowed, refused):
        wildcard_entry(allowed)
        key, jwk = _rsa_key_and_jwk()
        body = _signed_jws('http://localhost/acme/proxy/new-order',
                           {'identifiers': [{'type': 'dns', 'value': f'*.{_DOMAIN}'}]},
                           key, jwk=jwk, nonce=_fresh_nonce(app))
        problem = _post(client, body).get_json()

        assert problem['status'] == 400
        if refused:
            assert problem['type'] == 'urn:ietf:params:acme:error:rejectedIdentifier'
        else:
            # Not refused for the wildcard: the next gate (kid) answers.
            assert problem['type'] == 'urn:ietf:params:acme:error:malformed'
            assert 'kid' in problem['detail']
        service_factory.assert_not_called()


class TestShapeComesFirst:
    def test_http01_is_refused_before_any_account_check(
            self, client, service_factory, verified):
        verified({'identifiers': [{'type': 'dns', 'value': 'a.example.com'}],
                  'challenge_type': 'http-01'}, {'kid': _GHOST_KID})
        response = _post(client, {})

        assert response.status_code == 400
        problem = response.get_json()
        assert problem['type'] == 'urn:ietf:params:acme:error:malformed'
        assert 'http-01' in problem['detail']
        service_factory.assert_not_called()

    @pytest.mark.parametrize('payload', [[1, 2], 'text', 7])
    def test_a_payload_that_is_not_an_object_is_malformed(
            self, client, service_factory, verified, payload):
        verified(payload, {'kid': _GHOST_KID})
        response = _post(client, {})

        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
        service_factory.assert_not_called()

    @pytest.mark.parametrize('identifiers', ['a.example.com', {'type': 'dns'}, 5])
    def test_identifiers_that_is_not_an_array_is_malformed(
            self, client, service_factory, verified, identifiers):
        verified({'identifiers': identifiers}, {'kid': _GHOST_KID})
        response = _post(client, {})

        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
        service_factory.assert_not_called()

    def test_ip_identifier_is_unsupported_even_for_an_unknown_account(
            self, client, service_factory, verified):
        verified({'identifiers': [{'type': 'ip', 'value': '192.0.2.1'}]},
                 {'kid': _GHOST_KID})
        response = _post(client, {})

        assert response.status_code == 400
        assert (response.get_json()['type']
                == 'urn:ietf:params:acme:error:unsupportedIdentifier')
        service_factory.assert_not_called()


class TestAccountStatus:
    @pytest.mark.parametrize('status', ['deactivated', 'revoked'])
    def test_inactive_account_is_unauthorized(
            self, client, service_factory, verified, local_account, status):
        account = local_account(status)
        verified({'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                 {'kid': f'http://localhost/acme/proxy/acct/{account.account_id}'})
        response = _post(client, {})

        assert response.status_code == 401
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:unauthorized'
        service_factory.assert_not_called()

    @pytest.mark.parametrize('status', ['deactivated', 'revoked'])
    def test_real_kid_jws_of_an_inactive_account_is_refused_upstream_of_the_gate(
            self, app, client, service_factory, status):
        """End to end, verify_jws refuses the kid of an inactive account first."""
        from services.acme.jwk_thumbprint import jwk_thumbprint

        key, jwk = _rsa_key_and_jwk()
        with app.app_context():
            account = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=jwk_thumbprint(jwk),
                                  status=status)
            db.session.add(account)
            db.session.commit()
            row_id, account_id = account.id, account.account_id
            before = AcmeClientOrder.query.count()
        try:
            body = _signed_jws(
                'http://localhost/acme/proxy/new-order',
                {'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                key, kid=f'http://localhost/acme/proxy/acct/{account_id}',
                nonce=_fresh_nonce(app))
            response = _post(client, body)

            assert response.status_code == 401
            assert response.get_json()['type'] == 'urn:ietf:params:acme:error:unauthorized'
            service_factory.assert_not_called()
            with app.app_context():
                assert AcmeClientOrder.query.count() == before
        finally:
            with app.app_context():
                db.session.delete(db.session.get(AcmeAccount, row_id))
                db.session.commit()

    def test_real_kid_jws_of_a_valid_account_reaches_the_service(
            self, app, client, service_factory):
        """Control for the test above: the same JWS from a valid account passes."""
        from services.acme.jwk_thumbprint import jwk_thumbprint

        key, jwk = _rsa_key_and_jwk()
        with app.app_context():
            account = AcmeAccount(jwk=json.dumps(jwk), jwk_thumbprint=jwk_thumbprint(jwk))
            db.session.add(account)
            db.session.commit()
            row_id, account_id = account.id, account.account_id
        try:
            body = _signed_jws(
                'http://localhost/acme/proxy/new-order',
                {'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                key, kid=f'http://localhost/acme/proxy/acct/{account_id}',
                nonce=_fresh_nonce(app))
            assert _post(client, body).status_code == 201
            service_factory.assert_called_once()
        finally:
            with app.app_context():
                db.session.delete(db.session.get(AcmeAccount, row_id))
                db.session.commit()

    def test_unknown_kid_account_does_not_exist(self, client, service_factory, verified):
        verified({'identifiers': [{'type': 'dns', 'value': 'a.example.com'}]},
                 {'kid': _GHOST_KID})
        response = _post(client, {})

        assert response.status_code == 404
        assert (response.get_json()['type']
                == 'urn:ietf:params:acme:error:accountDoesNotExist')
        service_factory.assert_not_called()


class TestFinalizePayloadShape:
    @pytest.mark.parametrize('payload', [['csr'], 'csr'])
    def test_finalize_payload_that_is_not_an_object_is_malformed(
            self, client, service_factory, verified, payload):
        verified(payload)
        response = client.post('/acme/proxy/order/abc/finalize', data='{}',
                               content_type='application/jose+json')

        assert response.status_code == 400
        assert response.get_json()['type'] == 'urn:ietf:params:acme:error:malformed'
        service_factory.assert_not_called()
