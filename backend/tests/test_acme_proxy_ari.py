"""ACME proxy ARI (RFC 9773) — directory advertisement + renewal-info route.

Regression coverage for:
  * get_directory() advertises renewalInfo when upstream does
  * get_directory() omits renewalInfo when upstream does not
  * GET /acme/proxy/renewal-info/<certID> serves a local suggestedWindow
  * GET /acme/proxy/<slug>/renewal-info/<certID> works for slug-scoped CAs
  * Malformed / unknown certID → problem+json error
"""
import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone
from tests.seeded_rows import delete_client_accounts

import pytest

from models import db, AcmeClientAccount, Certificate
from services.acme.acme_proxy_service import AcmeProxyService
from tests.acme_proxy_upstream_stub import stub_acme_proxy_upstream


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


@pytest.fixture
def proxy_account(app):
    with app.app_context():
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()
        acct = AcmeClientAccount(
            directory_url='https://acme-ari-stub.example/directory',
            label='ARI test',
            email='ari@example.com',
            proxy_enabled=True,
            proxy_slug='ari-test',
        )
        db.session.add(acct)
        db.session.commit()
        yield acct
        delete_client_accounts(AcmeClientAccount.query)
        db.session.commit()


def _make_proxy(monkeypatch, fake_directory, account_id=None):
    stub_acme_proxy_upstream(monkeypatch, fake_directory=fake_directory)
    base = 'https://ucm.example/acme/proxy'
    if account_id is not None:
        return AcmeProxyService(base_url=base, account_id=account_id)
    return AcmeProxyService(base_url=base)


class TestDirectoryRenewalInfo:
    def test_advertises_renewal_info_when_upstream_has_it(self, proxy_account, monkeypatch):
        # Actalis-style directory with renewalInfo
        d = {
            'newNonce': 'https://acme-ari-stub.example/acme/newnonce',
            'newAccount': 'https://acme-ari-stub.example/acme/newaccount',
            'newOrder': 'https://acme-ari-stub.example/acme/neworders',
            'revokeCert': 'https://acme-ari-stub.example/acme/revokecert',
            'keyChange': 'https://acme-ari-stub.example/acme/key-change',
            'renewalInfo': 'https://acme-ari-stub.example/acme/renewal-info',
            'meta': {'externalAccountRequired': True, 'name': 'acme-server'},
        }
        svc = _make_proxy(monkeypatch, d, account_id=proxy_account.id)
        out = svc.get_directory()
        assert 'renewalInfo' in out
        # RFC 9773 §3/§4.1: directory publishes the BASE URL; clients append
        # "/<certID>". No literal placeholder in the value.
        assert out['renewalInfo'] == 'https://ucm.example/acme/proxy/renewal-info'

    def test_omits_renewal_info_when_upstream_lacks_it(self, proxy_account, monkeypatch):
        # Let's Encrypt-style directory without top-level renewalInfo
        d = {
            'newNonce': 'https://acme-ari-stub.example/new-nonce',
            'newAccount': 'https://acme-ari-stub.example/new-account',
            'newOrder': 'https://acme-ari-stub.example/new-order',
            'revokeCert': 'https://acme-ari-stub.example/revoke-cert',
            'keyChange': 'https://acme-ari-stub.example/key-change',
            'meta': {},
        }
        svc = _make_proxy(monkeypatch, d, account_id=proxy_account.id)
        out = svc.get_directory()
        assert 'renewalInfo' not in out


def _real_pem(aki_hex: str, serial_int: int) -> bytes:
    """A certificate carrying this AKI and serial, as the upstream CA would issue it."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ari-test')])
    aki = x509.AuthorityKeyIdentifier(bytes.fromhex(aki_hex.replace(':', '')), None, None)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(serial_int)
            .not_valid_before(datetime.now(timezone.utc) - timedelta(days=10))
            .not_valid_after(datetime.now(timezone.utc) + timedelta(days=80))
            .add_extension(aki, critical=False)
            .sign(key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


def _import_cert_for_ari(app, aki_hex: str, serial_int: int, real=False):
    """Insert a minimal Certificate row with aki + serial matching a certID."""
    with app.app_context():
        from uuid import uuid4
        cert = Certificate(
            refid=str(uuid4()),
            descr='ARI proxy test',
            crt=base64.b64encode(_real_pem(aki_hex, serial_int) if real else b'FAKEPEM').decode(),
            subject='CN=ari-test',
            subject_cn='ari-test',
            issuer='CN=ari-test-ca',
            serial_number=str(serial_int),
            valid_from=datetime.now(timezone.utc) - timedelta(days=10),
            valid_to=datetime.now(timezone.utc) + timedelta(days=80),
            key_algo='RSA 2048',
            aki=aki_hex,
            imported_from='acme_client',
            source='acme_client',
        )
        db.session.add(cert)
        db.session.commit()
        return cert.id


class TestRenewalInfoRoute:
    def _certid(self, aki_hex: str, serial_int: int) -> str:
        aki_bytes = bytes.fromhex(aki_hex.replace(':', ''))
        serial_bytes = serial_int.to_bytes((serial_int.bit_length() + 7) // 8, 'big')
        return f"{_b64url(aki_bytes)}.{_b64url(serial_bytes)}"

    def test_default_route_serves_window(self, app, client, proxy_account, monkeypatch):
        aki_hex = 'A8:4A:94:24:3A:1E:82:11'
        serial_int = 0x1234567890ABCDEF
        _import_cert_for_ari(app, aki_hex, serial_int)
        certid = self._certid(aki_hex, serial_int)

        # No directory fetch needed for the route — but stub anyway for safety.
        stub_acme_proxy_upstream(monkeypatch)

        r = client.get(f'/acme/proxy/renewal-info/{certid}')
        assert r.status_code == 200, r.get_data(as_text=True)
        body = r.get_json()
        assert 'suggestedWindow' in body
        assert 'start' in body['suggestedWindow']
        assert 'end' in body['suggestedWindow']
        assert r.headers.get('Retry-After')
        assert 'public' in r.headers.get('Cache-Control', '')

    def test_slug_route_serves_window(self, app, client, proxy_account, monkeypatch):
        aki_hex = 'B1:C2:D3:E4'
        serial_int = 0x42
        _import_cert_for_ari(app, aki_hex, serial_int)
        certid = self._certid(aki_hex, serial_int)

        stub_acme_proxy_upstream(monkeypatch)

        r = client.get(f'/acme/proxy/ari-test/renewal-info/{certid}')
        assert r.status_code == 200, r.get_data(as_text=True)
        assert 'suggestedWindow' in r.get_json()

    def test_malformed_certid_returns_400(self, app, client, monkeypatch):
        stub_acme_proxy_upstream(monkeypatch)
        r = client.get('/acme/proxy/renewal-info/not-a-valid-certid')
        assert r.status_code == 400
        assert r.headers['Content-Type'] == 'application/problem+json'

    def test_unknown_certid_returns_404(self, app, client, monkeypatch):
        stub_acme_proxy_upstream(monkeypatch)
        # Valid shape, no matching cert in DB
        certid = self._certid('AA:BB:CC:DD', 999999)
        r = client.get(f'/acme/proxy/renewal-info/{certid}')
        assert r.status_code == 404


class TestImportPopulatesAki:
    def test_import_certificate_sets_aki_and_ski(self, app):
        """Proxy-issued certs must have aki populated so ARI lookups match."""
        from services.cert_service import CertificateService
        # Self-signed cert with AKI==SKI (generated via cryptography)
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048, backend=default_backend())
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'ari-import-test')])
        builder = (x509.CertificateBuilder()
                   .subject_name(subject)
                   .issuer_name(issuer)
                   .public_key(key.public_key())
                   .serial_number(0x1234)
                   .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
                   .not_valid_after(datetime.now(timezone.utc) + timedelta(days=30)))
        cert_obj = builder.add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False
        ).add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(key.public_key()), critical=False
        ).sign(key, hashes.SHA256(), default_backend())
        pem = cert_obj.public_bytes(serialization.Encoding.PEM).decode()

        with app.app_context():
            imported = CertificateService.import_certificate(
                descr='ari-aki-test', cert_pem=pem, source='acme_client', username='test'
            )
            assert imported.aki is not None and ':' in imported.aki
            assert imported.ski is not None and ':' in imported.ski
            # Cleanup
            db.session.delete(imported)
            db.session.commit()


UPSTREAM_DIR = 'https://acme-ari-stub.example/directory'
UPSTREAM_ARI = 'https://acme-ari-stub.example/acme/renewal-info'
UPSTREAM_WINDOW = {'start': '2026-11-05T00:00:00Z', 'end': '2026-11-06T00:00:00Z'}


class _Answer:
    def __init__(self, payload, status_code=200, headers=None):
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeUpstream:
    """Upstream CA over unauthenticated GET: its directory, and its renewalInfo when it has one."""

    def __init__(self, announces=True, answer=None):
        self.announces = announces
        self.answer = answer or _Answer({'suggestedWindow': UPSTREAM_WINDOW,
                                         'explanationURL': 'https://ca.example/incident'},
                                        headers={'Retry-After': '1800'})
        self.ari_calls = []

    def __call__(self, url, *_a, **kwargs):
        if url == UPSTREAM_DIR:
            directory = {'newNonce': 'https://acme-ari-stub.example/nonce', 'meta': {}}
            if self.announces:
                directory['renewalInfo'] = UPSTREAM_ARI
            return _Answer(directory)
        if url.startswith(UPSTREAM_ARI + '/'):
            assert 'Authorization' not in (kwargs.get('headers') or {})
            self.ari_calls.append(url[len(UPSTREAM_ARI) + 1:])
            if isinstance(self.answer, Exception):
                raise self.answer
            return self.answer
        raise AssertionError(f'unexpected upstream GET {url}')


def _served_locally(resp):
    """The local window of a certificate valid for 80 more days starts weeks from now."""
    start = resp.get_json()['suggestedWindow']['start']
    start = datetime.fromisoformat(start.replace('Z', '+00:00'))
    return resp.status_code == 200 and start > datetime.now(timezone.utc) + timedelta(days=7)


class TestUpstreamRenewalInfoRelay:
    """RFC 9773: a certificate issued through the proxy gets the window of the CA that
    issued it, relayed with its Retry-After; the local window when the CA has none."""

    AKI = 'C0:FF:EE:01:02:03'
    SERIAL = 0x8A11E0  # high bit set: its DER value bytes carry a leading zero

    def _certid(self):
        aki = bytes.fromhex(self.AKI.replace(':', ''))
        serial = b'\x00' + self.SERIAL.to_bytes(3, 'big')
        return f"{_b64url(aki)}.{_b64url(serial)}"

    @pytest.fixture
    def issued(self, app, proxy_account):
        from models import AcmeClientOrder
        cert_id = _import_cert_for_ari(app, self.AKI, self.SERIAL, real=True)
        with app.app_context():
            order = AcmeClientOrder(domains=json.dumps(['ari.example']), environment='staging',
                                    challenge_type='dns-01', status='valid', is_proxy_order=True,
                                    certificate_id=cert_id,
                                    acme_client_account_id=proxy_account.id)
            db.session.add(order)
            db.session.commit()
            order_id = order.id
        yield cert_id
        with app.app_context():
            AcmeClientOrder.query.filter_by(id=order_id).delete()
            Certificate.query.filter_by(id=cert_id).delete()
            db.session.commit()

    @staticmethod
    def _upstream(monkeypatch, **kwargs):
        upstream = _FakeUpstream(**kwargs)
        monkeypatch.setattr('utils.ssrf_protection.safe_request_get', upstream)
        return upstream

    def test_upstream_window_is_relayed_with_its_retry_after(self, client, issued, monkeypatch):
        upstream = self._upstream(monkeypatch)
        r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        assert r.status_code == 200, r.get_data(as_text=True)
        assert r.get_json() == {'suggestedWindow': UPSTREAM_WINDOW,
                                'explanationURL': 'https://ca.example/incident'}
        assert 1790 <= int(r.headers['Retry-After']) <= 1800
        assert upstream.ari_calls == [self._certid()]

    def test_relayed_window_is_cached_until_retry_after(self, client, issued, monkeypatch):
        upstream = self._upstream(monkeypatch)
        for _ in range(3):
            assert client.get(f'/acme/proxy/renewal-info/{self._certid()}').status_code == 200
        assert len(upstream.ari_calls) == 1

    def test_local_window_when_upstream_announces_none(self, client, issued, monkeypatch):
        upstream = self._upstream(monkeypatch, announces=False)
        r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        assert _served_locally(r)
        assert r.headers['Retry-After'] == str(6 * 3600)
        assert upstream.ari_calls == []

    @pytest.mark.parametrize('answer', [
        _Answer({'suggestedWindow': UPSTREAM_WINDOW}, status_code=503),
        _Answer({'suggestedWindow': {'start': UPSTREAM_WINDOW['end'],
                                     'end': UPSTREAM_WINDOW['start']}}),
        _Answer(['not', 'an', 'object']),
        ConnectionError('unreachable'),
    ], ids=['5xx', 'inverted-window', 'not-an-object', 'unreachable'])
    def test_local_window_when_upstream_gives_no_usable_answer(self, client, issued, monkeypatch,
                                                               answer):
        upstream = self._upstream(monkeypatch, answer=answer)
        r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        assert _served_locally(r)
        assert upstream.ari_calls == [self._certid()]

    def test_certificate_not_issued_through_the_proxy_is_not_relayed(self, app, client,
                                                                     proxy_account, monkeypatch):
        upstream = self._upstream(monkeypatch)
        cert_id = _import_cert_for_ari(app, self.AKI, self.SERIAL, real=True)
        try:
            r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        finally:
            with app.app_context():
                Certificate.query.filter_by(id=cert_id).delete()
                db.session.commit()
        assert _served_locally(r)
        assert upstream.ari_calls == []

    def test_http_date_retry_after(self, client, issued, monkeypatch):
        from email.utils import format_datetime
        when = datetime.now(timezone.utc) + timedelta(hours=2)
        self._upstream(monkeypatch, answer=_Answer(
            {'suggestedWindow': UPSTREAM_WINDOW},
            headers={'Retry-After': format_datetime(when, usegmt=True)}))
        r = client.get(f'/acme/proxy/renewal-info/{self._certid()}')
        assert r.get_json() == {'suggestedWindow': UPSTREAM_WINDOW}
        assert 7100 <= int(r.headers['Retry-After']) <= 7200

    def test_certificate_revoked_here_gets_the_local_window(self, app, client, issued,
                                                           monkeypatch):
        upstream = self._upstream(monkeypatch)
        with app.app_context():
            db.session.get(Certificate, issued).revoked = True
            db.session.commit()
        r = client.get(f'/acme/proxy/renewal-info/{self._certid()}')
        start = datetime.fromisoformat(r.get_json()['suggestedWindow']['start'].replace('Z', ''))
        assert start < datetime.now(timezone.utc).replace(tzinfo=None)
        assert upstream.ari_calls == []

    def test_upstream_is_asked_with_the_certid_of_the_stored_certificate(self, client, issued,
                                                                        monkeypatch):
        """A client that drops the serial's leading zero still names the certificate."""
        upstream = self._upstream(monkeypatch)
        aki = bytes.fromhex(self.AKI.replace(':', ''))
        loose = f"{_b64url(aki)}.{_b64url(self.SERIAL.to_bytes(3, 'big'))}"
        r = client.get(f'/acme/proxy/renewal-info/{loose}')
        assert r.get_json()['suggestedWindow'] == UPSTREAM_WINDOW
        assert upstream.ari_calls == [self._certid()]

    def test_failed_upstream_is_asked_again_only_after_a_minute(self, client, issued,
                                                                monkeypatch):
        import services.acme.acme_proxy_service as proxy_mod
        upstream = self._upstream(monkeypatch, answer=ConnectionError('unreachable'))
        clock = [1000.0]
        monkeypatch.setattr(proxy_mod.time, 'monotonic', lambda: clock[0])
        for _ in range(3):
            assert _served_locally(client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}'))
        assert len(upstream.ari_calls) == 1
        clock[0] += 61
        assert _served_locally(client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}'))
        assert len(upstream.ari_calls) == 2

    @pytest.fixture
    def stored_twice(self, app, issued):
        """A second download stored the certificate again and the order now names that row."""
        from models import AcmeClientOrder
        second = _import_cert_for_ari(app, self.AKI, self.SERIAL, real=True)
        with app.app_context():
            order = AcmeClientOrder.query.filter_by(certificate_id=issued).one()
            order.certificate_id = second
            db.session.commit()
        yield issued, second
        with app.app_context():
            AcmeClientOrder.query.filter_by(certificate_id=second).update(
                {AcmeClientOrder.certificate_id: issued}, synchronize_session=False)
            Certificate.query.filter_by(id=second).delete()
            db.session.commit()

    def test_order_naming_a_later_row_is_still_relayed(self, client, stored_twice, monkeypatch):
        upstream = self._upstream(monkeypatch)
        r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        assert r.get_json()['suggestedWindow'] == UPSTREAM_WINDOW
        assert upstream.ari_calls == [self._certid()]

    @pytest.mark.parametrize('revoked_row', [0, 1])
    def test_revocation_on_any_row_gets_the_local_window(self, app, client, stored_twice,
                                                         monkeypatch, revoked_row):
        upstream = self._upstream(monkeypatch)
        with app.app_context():
            db.session.get(Certificate, stored_twice[revoked_row]).revoked = True
            db.session.commit()
        r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
        start = datetime.fromisoformat(r.get_json()['suggestedWindow']['start'].replace('Z', ''))
        assert start < datetime.now(timezone.utc).replace(tzinfo=None)
        assert upstream.ari_calls == []

    def test_oversized_retry_after_falls_back_to_the_default_and_is_cached(self, client, issued,
                                                                          monkeypatch):
        upstream = self._upstream(monkeypatch, answer=_Answer(
            {'suggestedWindow': UPSTREAM_WINDOW}, headers={'Retry-After': '9' * 30}))
        for _ in range(2):
            r = client.get(f'/acme/proxy/ari-test/renewal-info/{self._certid()}')
            assert r.get_json() == {'suggestedWindow': UPSTREAM_WINDOW}
        assert 6 * 3600 - 10 <= int(r.headers['Retry-After']) <= 6 * 3600
        assert len(upstream.ari_calls) == 1

    @pytest.mark.parametrize('retry_after, still_cached, asked_again', [
        ('1800', 1790, 1801),  # the upstream Retry-After, within the bounds
        ('10', 30, 61),        # raised to one minute
        ('7200', 3590, 3601),  # cut to one hour
    ])
    def test_cache_follows_retry_after_within_bounds(self, client, issued, monkeypatch,
                                                     retry_after, still_cached, asked_again):
        import services.acme.acme_proxy_service as proxy_mod
        upstream = self._upstream(monkeypatch, answer=_Answer(
            {'suggestedWindow': UPSTREAM_WINDOW}, headers={'Retry-After': retry_after}))
        clock = [1000.0]
        monkeypatch.setattr(proxy_mod.time, 'monotonic', lambda: clock[0])
        url = f'/acme/proxy/ari-test/renewal-info/{self._certid()}'
        assert client.get(url).status_code == 200
        clock[0] = 1000.0 + still_cached
        assert client.get(url).status_code == 200
        assert len(upstream.ari_calls) == 1
        clock[0] = 1000.0 + asked_again
        assert client.get(url).status_code == 200
        assert len(upstream.ari_calls) == 2
