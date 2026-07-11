"""Security regressions for ACME proxy (EAB gate, order/cert binding)."""
import base64
import json

import pytest

from models import db, SystemConfig, AcmeClientAccount, AcmeClientOrder
from services.acme.acme_proxy_account import PROXY_ACCOUNT_ID_KEY


_STUB_DIRECTORY_URL = 'https://acme-stub.example/directory'


def _set_eab_required(app, enabled):
    with app.app_context():
        row = SystemConfig.query.filter_by(key='acme_eab_required').first()
        if not row:
            row = SystemConfig(key='acme_eab_required', description='test')
            db.session.add(row)
        row.value = 'true' if enabled else 'false'
        db.session.commit()


def _get_nonce(client):
    r = client.get('/acme/proxy/new-nonce')
    return r.headers.get('Replay-Nonce', 'fallback-nonce')


def _generate_rsa_key_and_jwk():
    from cryptography.hazmat.primitives.asymmetric import rsa

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private_key.public_key().public_numbers()

    def int_to_b64(n):
        b = n.to_bytes((n.bit_length() + 7) // 8, 'big')
        return base64.urlsafe_b64encode(b).rstrip(b'=').decode()

    jwk = {'kty': 'RSA', 'n': int_to_b64(pub.n), 'e': int_to_b64(pub.e)}
    return private_key, jwk


def _build_jws(url, payload, jwk, private_key, nonce='test-nonce', use_kid=None):
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives import hashes

    protected = {'alg': 'RS256', 'nonce': nonce, 'url': url}
    if use_kid:
        protected['kid'] = use_kid
    else:
        protected['jwk'] = jwk

    protected_b64 = base64.urlsafe_b64encode(
        json.dumps(protected).encode()
    ).rstrip(b'=').decode()

    if payload is not None:
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
    else:
        payload_b64 = ''

    signing_input = f'{protected_b64}.{payload_b64}'.encode()
    signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
    sig_b64 = base64.urlsafe_b64encode(signature).rstrip(b'=').decode()

    return {'protected': protected_b64, 'payload': payload_b64, 'signature': sig_b64}


@pytest.fixture(autouse=True)
def _reset_eab_required_after_test(app):
    yield
    _set_eab_required(app, False)


@pytest.fixture
def proxy_protocol_upstream_stub(app, monkeypatch):
    """Stub upstream directory fetch for proxy protocol security tests."""
    fake_directory = {
        'newNonce': 'https://acme-stub.example/acme/new-nonce',
        'newAccount': 'https://acme-stub.example/acme/new-account',
        'newOrder': 'https://acme-stub.example/acme/new-order',
        'meta': {},
    }

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return fake_directory

    monkeypatch.setattr(
        'services.acme.acme_proxy_service.requests.get',
        lambda *args, **kwargs: _FakeResp(),
    )

    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url=_STUB_DIRECTORY_URL,
            label='Proxy Security Stub',
            email='proxy-security@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        db.session.add(SystemConfig(
            key=PROXY_ACCOUNT_ID_KEY,
            value=str(acct.id),
            description='test proxy security',
        ))
        db.session.commit()
    yield
    with app.app_context():
        SystemConfig.query.filter_by(key=PROXY_ACCOUNT_ID_KEY).delete()
        AcmeClientAccount.query.filter_by(
            directory_url=_STUB_DIRECTORY_URL
        ).delete()
        db.session.commit()


class TestAcmeProxyEabNewOrder:
    def test_new_order_requires_kid_when_eab_enabled(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, True)
        private_key, jwk = _generate_rsa_key_and_jwk()
        nonce = _get_nonce(client)
        url = 'http://localhost/acme/proxy/new-order'
        payload = {'identifiers': [{'type': 'dns', 'value': 'test.example.com'}]}
        jws = _build_jws(url, payload, jwk, private_key, nonce=nonce)

        r = client.post(
            '/acme/proxy/new-order',
            data=json.dumps(jws),
            content_type='application/jose+json',
        )
        assert r.status_code == 400
        assert 'kid' in r.get_json().get('detail', '').lower()

    def test_new_order_allows_kid_when_eab_enabled(
        self, app, client, proxy_protocol_upstream_stub,
    ):
        _set_eab_required(app, False)
        private_key, jwk = _generate_rsa_key_and_jwk()

        nonce1 = _get_nonce(client)
        url_acct = 'http://localhost/acme/proxy/new-account'
        jws_acct = _build_jws(
            url_acct, {'termsOfServiceAgreed': True}, jwk, private_key, nonce=nonce1,
        )
        r_acct = client.post(
            '/acme/proxy/new-account',
            data=json.dumps(jws_acct),
            content_type='application/jose+json',
        )
        assert r_acct.status_code == 201
        kid = r_acct.headers['Location']

        _set_eab_required(app, True)

        nonce2 = _get_nonce(client)
        url_order = 'http://localhost/acme/proxy/new-order'
        payload_order = {'identifiers': [{'type': 'dns', 'value': 'test.example.com'}]}
        jws_order = _build_jws(
            url_order, payload_order, jwk, private_key, nonce=nonce2, use_kid=kid,
        )
        r_order = client.post(
            '/acme/proxy/new-order',
            data=json.dumps(jws_order),
            content_type='application/jose+json',
        )

        detail = (r_order.get_json() or {}).get('detail', '')
        assert 'Missing JWK' not in detail
        assert 'kid required' not in detail.lower()
        assert 'Account not found' not in detail


class TestAcmeProxyCertOrderBinding:
    def test_find_order_for_certificate_matches_upstream_cert_url(self, app, monkeypatch):
        from services.acme.acme_proxy_service import AcmeProxyService

        cert_url = 'https://ca.example/acme/cert/1'
        order_a_url = 'https://ca.example/acme/order/a'
        order_b_url = 'https://ca.example/acme/order/b'

        with app.app_context():
            order_a = AcmeClientOrder(
                domains='["a.example.com"]',
                environment='staging',
                challenge_type='dns-01',
                status='pending',
                order_url=order_a_url,
                upstream_order_url=order_a_url,
                is_proxy_order=True,
            )
            order_b = AcmeClientOrder(
                domains='["b.example.com"]',
                environment='staging',
                challenge_type='dns-01',
                status='pending',
                order_url=order_b_url,
                upstream_order_url=order_b_url,
                is_proxy_order=True,
            )
            db.session.add_all([order_a, order_b])
            db.session.commit()

            svc = AcmeProxyService('https://ucm.example/acme/proxy')

            def fake_post(url, payload):
                class Resp:
                    status_code = 200

                    def json(self_inner):
                        if url == order_b_url:
                            return {'certificate': cert_url}
                        return {}

                return Resp()

            monkeypatch.setattr(svc, '_post_with_account', fake_post)
            matched = svc._find_order_for_certificate(cert_url)
            assert matched is not None
            assert matched.id == order_b.id
