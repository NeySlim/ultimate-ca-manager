"""Regression tests for the ACME proxy bug batch (#217, #218, #219, #220).

#217 — Link: rel="up" header must not double the /acme/proxy prefix.
#218 — DNS-01 cleanup must not run on the request thread in get_certificate().
#219 — certificate download must resolve its order via the persisted
       certificate_url (indexed) instead of live upstream scans.
#220 — the upstream Link header (rel="alternate" → real CA URLs) must never be
       forwarded to the downstream client.
"""
import base64
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from models import db
from models.acme_models import AcmeClientOrder

UPSTREAM = 'https://acme-stub.example'


def _b64(url: str) -> str:
    return base64.urlsafe_b64encode(url.encode()).rstrip(b'=').decode()


def _self_signed_pem() -> str:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'proxy-fix.test')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name).public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now).not_valid_after(now + timedelta(days=1))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def _make_service(app):
    from services.acme.acme_proxy_service import AcmeProxyService
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    svc.upstream_directory_url = f'{UPSTREAM}/directory'
    svc.account = SimpleNamespace(preferred_chain='')
    return svc


def _seed_proxy_order(**kwargs):
    order = AcmeClientOrder(
        domains=json.dumps(['proxy-fix.test']),
        status=kwargs.pop('status', 'pending'),
        is_proxy_order=True,
        **kwargs,
    )
    db.session.add(order)
    db.session.commit()
    return order


@pytest.fixture(autouse=True)
def _clean_orders(app):
    with app.app_context():
        yield
        AcmeClientOrder.query.filter_by(domains=json.dumps(['proxy-fix.test'])).delete()
        db.session.commit()


class TestAuthzLinkNotDoubled:
    """#217 — base_url already ends in /acme/proxy; the rel="up" link must not
    prepend the segment a second time."""

    def test_rel_up_link_single_prefix(self, app):
        with app.app_context():
            svc = _make_service(app)
            upstream = f'<{UPSTREAM}/authz/xyz>;rel="up"'
            link = svc._get_authz_link(upstream)
        expected_id = _b64(f'{UPSTREAM}/authz/xyz')
        assert link == f'<https://ucm.example/acme/proxy/authz/{expected_id}>;rel="up"'
        assert link.count('/acme/proxy/') == 1


class TestCertificateUrlPersistence:
    """#219 — persisted certificate_url enables an indexed order lookup."""

    def test_persist_certificate_url(self, app):
        with app.app_context():
            svc = _make_service(app)
            order = _seed_proxy_order(upstream_order_url=f'{UPSTREAM}/order/1')
            svc._persist_certificate_url(f'{UPSTREAM}/order/1', f'{UPSTREAM}/cert/abc')
            assert db.session.get(AcmeClientOrder, order.id).certificate_url == f'{UPSTREAM}/cert/abc'

    def test_find_order_fast_path_no_upstream_calls(self, app, monkeypatch):
        with app.app_context():
            svc = _make_service(app)
            order = _seed_proxy_order(
                upstream_order_url=f'{UPSTREAM}/order/2',
                certificate_url=f'{UPSTREAM}/cert/fast',
            )

            def _no_upstream(*_a, **_k):
                raise AssertionError('fast path must not call upstream')

            monkeypatch.setattr(svc, '_post_with_account', _no_upstream)
            found = svc._find_order_for_certificate(f'{UPSTREAM}/cert/fast')
            assert found.id == order.id

    def test_fallback_scan_skips_rows_with_url(self, app, monkeypatch):
        with app.app_context():
            # Isolate from proxy orders leaked by other test modules — the
            # fallback scan queries every pending proxy order without a URL.
            AcmeClientOrder.query.filter_by(is_proxy_order=True).delete()
            db.session.commit()
            svc = _make_service(app)
            _seed_proxy_order(
                upstream_order_url=f'{UPSTREAM}/order/3',
                certificate_url=f'{UPSTREAM}/cert/other',
            )
            calls = []

            def _count_upstream(*_a, **_k):
                calls.append(1)
                return SimpleNamespace(status_code=404)

            monkeypatch.setattr(svc, '_post_with_account', _count_upstream)
            assert svc._find_order_for_certificate(f'{UPSTREAM}/cert/missing') is None
            # The row already carrying a certificate_url must not be re-polled.
            assert calls == []


class TestGetCertificateResponsePath:
    """#218 + #220 — success path: background DNS cleanup, no Link forwarded."""

    def _run_get_certificate(self, app, monkeypatch, order):
        from services.acme.acme_proxy_service import AcmeProxyService
        from services.cert_service import CertificateService

        pem = _self_signed_pem()
        cert_url = f'{UPSTREAM}/cert/dl-1'

        upstream_resp = SimpleNamespace(
            status_code=200,
            content=pem.encode(),
            headers={
                'Link': f'<{UPSTREAM}/cert/dl-1/1>;rel="alternate"',
                'Content-Type': 'application/pem-certificate-chain',
            },
        )
        svc = _make_service(app)
        monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: upstream_resp)
        monkeypatch.setattr(
            CertificateService, 'import_certificate',
            staticmethod(lambda **_kw: SimpleNamespace(id=4242)),
        )

        spawned = []

        class _FakeThread:
            def __init__(self, target=None, args=(), **_kw):
                spawned.append((target, args))
                self.name = ''
                self.daemon = False

            def start(self):
                pass

        monkeypatch.setattr(threading, 'Thread', _FakeThread)
        body, content_type, link_header = svc.get_certificate(_b64(cert_url))
        return body, content_type, link_header, spawned, pem

    def test_dns_cleanup_dispatched_to_background(self, app, monkeypatch):
        with app.app_context():
            records = [{'provider_id': 1, 'domain': 'proxy-fix.test', 'record_name': '_acme-challenge'}]
            order = _seed_proxy_order(
                upstream_order_url=f'{UPSTREAM}/order/4',
                certificate_url=f'{UPSTREAM}/cert/dl-1',
                dns_records_created=json.dumps(records),
            )
            body, _ct, _link, spawned, _pem = self._run_get_certificate(app, monkeypatch, order)

            assert len(spawned) == 1
            target, args = spawned[0]
            assert target.__name__ == '_bg_cleanup_dns_records'
            assert args[1] == records

            refreshed = db.session.get(AcmeClientOrder, order.id)
            assert refreshed.status == 'valid'
            assert refreshed.dns_records_created is None
            assert refreshed.certificate_id == 4242

    def test_upstream_link_header_not_forwarded(self, app, monkeypatch):
        with app.app_context():
            order = _seed_proxy_order(
                upstream_order_url=f'{UPSTREAM}/order/5',
                certificate_url=f'{UPSTREAM}/cert/dl-1',
            )
            body, content_type, link_header, _sp, pem = self._run_get_certificate(app, monkeypatch, order)
            assert link_header is None
            assert content_type == 'application/pem-certificate-chain'
            assert pem.strip() in (body if isinstance(body, str) else body.decode())

    def test_link_not_forwarded_on_upstream_error(self, app, monkeypatch):
        with app.app_context():
            svc = _make_service(app)
            err_resp = SimpleNamespace(
                status_code=404,
                content=b'not found',
                headers={'Link': f'<{UPSTREAM}/x>;rel="alternate"', 'Content-Type': 'application/problem+json'},
            )
            monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: err_resp)
            _body, _ct, link_header = svc.get_certificate(_b64(f'{UPSTREAM}/cert/err'))
            assert link_header is None


class TestBgCleanupDnsRecords:
    """#218 — the background task is fault-tolerant per record."""

    def test_missing_provider_is_skipped(self, app):
        with app.app_context():
            svc = _make_service(app)
        # Unknown provider id and malformed record must not raise.
        svc._bg_cleanup_dns_records(app, [
            {'provider_id': 999999, 'domain': 'proxy-fix.test', 'record_name': '_acme-challenge'},
            {'domain': 'proxy-fix.test'},
        ])
