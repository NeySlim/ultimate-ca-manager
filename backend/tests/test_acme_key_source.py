"""Tests for ACME key source (CSR / reuse) — issue #161."""
import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from cryptography.x509.oid import NameOID

from tests.conftest import get_json, assert_success, assert_error

CONTENT_JSON = 'application/json'


def post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type=CONTENT_JSON)


def _make_csr(domains, key=None):
    key = key or rsa.generate_private_key(65537, 2048, default_backend())
    primary = domains[0]
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, primary)])
    san = x509.SubjectAlternativeName([x509.DNSName(d) for d in domains])
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(subject)
        .add_extension(san, critical=False)
        .sign(key, hashes.SHA256(), default_backend())
    )
    pem = csr.public_bytes(serialization.Encoding.PEM).decode()
    return pem, key


class TestAcmeCsrUtils:
    def test_csr_domains_must_match_order(self):
        from utils.acme_csr import load_pem_csr, csr_domains_match_order

        pem, _ = _make_csr(['example.com', 'www.example.com'])
        csr = load_pem_csr(pem)
        ok, _ = csr_domains_match_order(csr, ['example.com', 'www.example.com'])
        assert ok
        ok2, msg = csr_domains_match_order(csr, ['example.com'])
        assert not ok2
        assert 'match' in msg.lower()


class TestAcmeClientKeySourceApi:
    def test_request_rejects_csr_without_pem(self, auth_client):
        r = post_json(auth_client, '/api/v2/acme/client/request', {
            'domains': ['example.com'],
            'email': 'admin@example.com',
            'challenge_type': 'http-01',
            'environment': 'staging',
            'key_source': 'csr',
        })
        assert r.status_code == 400
        body = get_json(r)
        assert 'csr' in body.get('message', '').lower()

    def test_request_rejects_mismatched_csr_domains(self, auth_client):
        pem, _ = _make_csr(['other.com'])
        r = post_json(auth_client, '/api/v2/acme/client/request', {
            'domains': ['example.com'],
            'email': 'admin@example.com',
            'challenge_type': 'http-01',
            'environment': 'staging',
            'key_source': 'csr',
            'csr_pem': pem,
        })
        assert r.status_code == 400

    def test_finalize_order_csr_path(self, app):
        from models.acme_models import AcmeClientOrder
        from services.acme.acme_client_service import AcmeClientService

        pem, _ = _make_csr(['finalize-test.example.com'])
        order = AcmeClientOrder(
            domains=json.dumps(['finalize-test.example.com']),
            challenge_type='dns-01',
            environment='staging',
            status='ready',
            order_url='https://acme.example/order/1',
            finalize_url='https://acme.example/order/1/finalize',
            key_source='csr',
            csr_pem=pem,
        )

        captured = {}

        class FakeResp:
            status_code = 200

            def json(self):
                return {'status': 'processing', 'certificate': 'https://acme.example/cert/1'}

        class FakeCertResp:
            status_code = 200
            text = (
                '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n'
            )

        with app.app_context():
            svc = AcmeClientService.__new__(AcmeClientService)
            svc.check_order_status = lambda o: ('ready', {})
            svc._post = lambda url, payload: (
                captured.update({'csr': payload.get('csr')}) or FakeResp()
                if 'finalize' in url
                else FakeCertResp()
            )
            svc._import_certificate = lambda **kw: 42

            ok, msg, cert_id = AcmeClientService.finalize_order(svc, order)
            assert ok, msg
            assert cert_id == 42
            assert captured.get('csr')


class TestAcmeClientFinalizeReuse:
    def test_reuse_without_prior_cert_generates_key(self, app):
        from models.acme_models import AcmeClientOrder
        from services.acme.acme_client_service import AcmeClientService

        order = AcmeClientOrder(
            domains=json.dumps(['reuse.example.com']),
            challenge_type='dns-01',
            environment='staging',
            status='ready',
            order_url='https://acme.example/order/2',
            finalize_url='https://acme.example/order/2/finalize',
            key_source='reuse',
            key_type='RSA-2048',
        )

        imported = {}

        class FakeResp:
            status_code = 200

            def json(self):
                return {'status': 'processing', 'certificate': 'https://acme.example/cert/2'}

        class FakeCertResp:
            status_code = 200
            text = '-----BEGIN CERTIFICATE-----\nMIIB\n-----END CERTIFICATE-----\n'

        with app.app_context():
            svc = AcmeClientService.__new__(AcmeClientService)
            svc.check_order_status = lambda o: ('ready', {})
            svc._post = lambda url, payload: FakeResp() if 'finalize' in url else FakeCertResp()
            svc._import_certificate = lambda **kw: imported.update({'has_key': kw.get('key_pem') is not None}) or 99

            ok, _, _ = AcmeClientService.finalize_order(svc, order)
            assert ok
            assert imported['has_key'] is True
