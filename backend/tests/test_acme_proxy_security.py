"""Security regressions for ACME proxy (EAB gate, order/cert binding)."""
import base64
import hashlib
import json

import pytest

from models import db, SystemConfig, AcmeClientOrder


def _jwk_thumbprint(jwk):
    canonical = json.dumps(jwk, separators=(',', ':'), sort_keys=True)
    return base64.urlsafe_b64encode(
        hashlib.sha256(canonical.encode()).digest()
    ).rstrip(b'=').decode()


class TestAcmeProxyEabNewOrder:
    def test_new_order_requires_kid_when_eab_enabled(self, app, client, monkeypatch):
        from api.acme import acme_api

        with app.app_context():
            db.session.add(SystemConfig(
                key='acme_eab_required',
                value='true',
                description='test',
            ))
            db.session.commit()

        jwk = {'kty': 'RSA', 'n': 'abc', 'e': 'AQAB'}
        payload = {'identifiers': [{'type': 'dns', 'value': 'test.example.com'}]}
        protected = {'alg': 'RS256', 'nonce': 'n', 'url': 'http://localhost/acme/proxy/new-order'}
        protected_b64 = base64.urlsafe_b64encode(
            json.dumps(protected).encode()
        ).rstrip(b'=').decode()
        payload_b64 = base64.urlsafe_b64encode(
            json.dumps(payload).encode()
        ).rstrip(b'=').decode()
        monkeypatch.setattr(
            acme_api,
            'verify_jws',
            lambda _jws, _url: (True, payload, jwk, None),
        )

        r = client.post(
            '/acme/proxy/new-order',
            json={'protected': protected_b64, 'payload': payload_b64, 'signature': 'sig'},
            content_type='application/jose+json',
        )
        assert r.status_code == 400
        assert 'kid' in r.get_json().get('detail', '').lower()


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
