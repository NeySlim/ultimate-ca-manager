"""External ACME client revocation and ARI renewal behavior."""
import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import AcmeClientAccount, Certificate, SystemConfig, db
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


def _certificate(common_name='client-ari.example', serial=0x123456, aki=b'\x01\x02\x03\x04'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(serial)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=90))
        .add_extension(
            x509.AuthorityKeyIdentifier(aki, None, None),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


class _Response:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class TestAcmeClientRevocation:
    def test_posts_der_and_reason_with_account_jws(self):
        cert, _ = _certificate()
        captured = {}
        service = AcmeClientService.__new__(AcmeClientService)
        service._fetch_directory = lambda: {
            'revokeCert': 'https://ca.example/acme/revoke-cert',
        }

        def fake_post(url, payload, use_jwk=False):
            captured.update(url=url, payload=payload, use_jwk=use_jwk)
            return _Response(200)

        service._post = fake_post
        response = service.revoke_certificate(
            cert.public_bytes(serialization.Encoding.PEM),
            reason=4,
        )

        assert response.status_code == 200
        assert captured['url'] == 'https://ca.example/acme/revoke-cert'
        assert captured['use_jwk'] is False
        assert captured['payload'] == {
            'certificate': _b64url(cert.public_bytes(serialization.Encoding.DER)),
            'reason': 4,
        }

    @pytest.mark.parametrize('reason', [-1, 7, 11, True, '4'])
    def test_rejects_invalid_rfc5280_reason(self, reason):
        cert, _ = _certificate()
        service = AcmeClientService.__new__(AcmeClientService)
        service._fetch_directory = lambda: pytest.fail('directory must not be fetched')

        with pytest.raises(ValueError, match='reason'):
            service.revoke_certificate(cert, reason=reason)


class TestAcmeClientAri:
    def test_fetches_and_parses_renewal_info(self, monkeypatch):
        aki = b'\x10\x20\x30\x40'
        serial = 0xA1B2C3
        cert, _ = _certificate(serial=serial, aki=aki)
        captured = {}
        service = AcmeClientService.__new__(AcmeClientService)
        service.directory_url = 'https://ca.example/directory'
        service.directory = {
            'renewalInfo': 'https://ca.example/acme/renewal-info',
        }
        service.account = None
        service.verify_ssl = True
        service.session = MagicMock()
        service.session.headers = {'User-Agent': 'test'}
        service._fetch_directory = lambda: service.directory
        service._http_timeout = lambda: 15
        service._validate_outbound_acme_url = lambda url: captured.update(url=url)

        response = _Response(
            200,
            {
                'suggestedWindow': {
                    'start': '2026-08-01T00:00:00Z',
                    'end': '2026-08-02T00:00:00Z',
                },
            },
            {'Retry-After': '3600'},
        )
        monkeypatch.setattr(
            'utils.ssrf_protection.safe_request_get',
            lambda *args, **kwargs: response,
        )

        info = service.get_renewal_info(cert)
        cert_id = f'{_b64url(aki)}.{_b64url(serial.to_bytes(3, "big"))}'

        assert captured['url'] == f'https://ca.example/acme/renewal-info/{cert_id}'
        assert info['cert_id'] == cert_id
        assert info['suggested_window']['start'] == datetime(2026, 8, 1)
        assert info['suggested_window']['end'] == datetime(2026, 8, 2)
        assert info['retry_after'] > datetime.utcnow()

    def test_returns_none_when_directory_has_no_ari(self):
        cert, _ = _certificate()
        service = AcmeClientService.__new__(AcmeClientService)
        service._fetch_directory = lambda: {'newOrder': 'https://ca.example/order'}

        assert service.get_renewal_info(cert) is None


@pytest.fixture
def renewal_ari_rows(app):
    cert_obj, _ = _certificate(common_name='scheduled-ari.example', serial=0xABCDEF)
    pem = cert_obj.public_bytes(serialization.Encoding.PEM)
    with app.app_context():
        account = AcmeClientAccount(
            directory_url=f'https://ca-{uuid4().hex}.example/directory',
            label='ARI scheduler test',
            email='ari-scheduler@example.com',
            account_url='https://ca.example/acct/1',
        )
        cert = Certificate(
            refid=str(uuid4()),
            descr='scheduled-ari.example',
            crt=base64.b64encode(pem).decode(),
            subject='CN=scheduled-ari.example',
            subject_cn='scheduled-ari.example',
            issuer='CN=External CA',
            serial_number=format(cert_obj.serial_number, 'x'),
            valid_from=datetime.utcnow() - timedelta(days=10),
            valid_to=datetime.utcnow() + timedelta(days=80),
            key_algo='RSA 2048',
            aki='AB:CD:EF',
            source='acme_client',
            imported_from='acme_client',
        )
        db.session.add_all([account, cert])
        db.session.flush()
        order = AcmeClientOrder(
            domains='["scheduled-ari.example"]',
            challenge_type='dns-01',
            environment='custom',
            status='issued',
            renewal_enabled=True,
            renewal_failures=0,
            expires_at=datetime.utcnow() + timedelta(days=80),
            certificate_id=cert.id,
            acme_client_account_id=account.id,
        )
        db.session.add(order)
        db.session.commit()
        ids = order.id, cert.id, account.id

    yield ids

    with app.app_context():
        order_id, cert_id, account_id = ids
        db.session.query(AcmeClientOrder).filter_by(id=order_id).delete()
        db.session.query(Certificate).filter_by(id=cert_id).delete()
        db.session.query(AcmeClientAccount).filter_by(id=account_id).delete()
        db.session.commit()


def test_scheduler_uses_ari_window_and_retry_after(app, renewal_ari_rows, monkeypatch):
    from services import acme_renewal_service as renewal_service

    renewal_service._ARI_CACHE.clear()
    fetches = []
    renewed = []
    now = datetime.utcnow()
    info = {
        'cert_id': 'q83v.q83v',
        'suggested_window': {
            'start': now - timedelta(minutes=1),
            'end': now + timedelta(hours=1),
        },
        'retry_after': now + timedelta(hours=6),
    }
    client = MagicMock()
    client.get_renewal_info.side_effect = lambda cert: fetches.append(cert.id) or info
    monkeypatch.setattr(
        renewal_service.AcmeClientService,
        'for_order',
        staticmethod(lambda order: client),
    )
    monkeypatch.setattr(
        renewal_service,
        'renew_certificate',
        lambda order: renewed.append(order.id) or (True, 'ok'),
    )

    with app.app_context():
        renewal_service.scheduled_acme_renewal()
        renewal_service.scheduled_acme_renewal()

    assert len(fetches) == 1
    assert renewed == [renewal_ari_rows[0], renewal_ari_rows[0]]


def test_upstream_revoke_failure_does_not_undo_local_revoke(
    app, renewal_ari_rows, monkeypatch,
):
    from services import acme_renewal_service as renewal_service

    with app.app_context():
        setting = SystemConfig.query.filter_by(key='acme.revoke_on_renewal').first()
        previous = setting.value if setting else None
        if setting:
            setting.value = 'true'
        else:
            setting = SystemConfig(
                key='acme.revoke_on_renewal',
                value='true',
                description='test',
            )
            db.session.add(setting)
        db.session.commit()

        local_revoke = MagicMock()
        monkeypatch.setattr(
            renewal_service.CertificateService,
            'revoke_certificate',
            local_revoke,
        )
        client = MagicMock()
        client.revoke_certificate.side_effect = RuntimeError('upstream unavailable')
        certificate = db.session.get(Certificate, renewal_ari_rows[1])

        renewal_service._revoke_replaced_certificate(client, certificate)

        local_revoke.assert_called_once_with(
            cert_id=certificate.id,
            reason='superseded',
            username='system',
        )
        client.revoke_certificate.assert_called_once_with(certificate, reason=4)

        if previous is None:
            db.session.delete(setting)
        else:
            setting.value = previous
        db.session.commit()


def test_renewal_order_sends_replaces_when_ari_is_advertised(app, monkeypatch):
    cert, _ = _certificate(serial=0x10203, aki=b'\x0a\x0b\x0c')
    with app.app_context():
        account = AcmeClientAccount(
            directory_url=f'https://replace-{uuid4().hex}.example/directory',
            label='Replaces test',
            email='replace@example.com',
            account_url='https://replace.example/acct/1',
        )
        db.session.add(account)
        db.session.commit()
        service = AcmeClientService(account=account)
        directory = {
            'newOrder': 'https://replace.example/new-order',
            'renewalInfo': 'https://replace.example/renewal-info',
        }
        service._fetch_directory = lambda: directory
        service.ensure_account = lambda email: (True, 'ok')
        captured = {}

        class OrderResponse(_Response):
            def __init__(self, status_code, payload):
                super().__init__(status_code, payload, {'Location': 'https://replace.example/order/1'})

        def fake_post(url, payload, use_jwk=False):
            captured.setdefault(url, []).append(payload)
            if url == directory['newOrder']:
                return OrderResponse(201, {
                    'expires': '2026-12-01T00:00:00Z',
                    'finalize': 'https://replace.example/order/1/finalize',
                    'authorizations': [],
                })
            raise AssertionError(url)

        service._post = fake_post
        cert_id = service.certificate_identifier(cert)
        ok, message, order = service.create_order(
            ['replace.example'],
            'replace@example.com',
            replaces=cert_id,
        )

        assert ok, message
        assert captured[directory['newOrder']][0]['replaces'] == cert_id
        db.session.delete(order)
        db.session.delete(account)
        db.session.commit()
