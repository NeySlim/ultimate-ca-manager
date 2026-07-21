"""ACME proxy upstream certificate revocation (RFC 8555 §7.6)."""
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

from models import AcmeClientAccount, Certificate, db
from models.acme_models import AcmeClientOrder


def _certificate():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'proxy-revoke.example')])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(0xCAFE1234)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=90))
        .sign(key, hashes.SHA256())
    )
    return cert


def _b64url(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode()


@pytest.fixture
def proxy_revocation_rows(app):
    cert_obj = _certificate()
    pem = cert_obj.public_bytes(serialization.Encoding.PEM)
    with app.app_context():
        account = AcmeClientAccount(
            directory_url=f'https://revoke-{uuid4().hex}.example/directory',
            label='Proxy revoke test',
            email='proxy-revoke@example.com',
            account_url='https://revoke.example/acct/1',
            proxy_enabled=True,
        )
        cert = Certificate(
            refid=str(uuid4()),
            descr='proxy-revoke.example',
            crt=base64.b64encode(pem).decode(),
            subject='CN=proxy-revoke.example',
            subject_cn='proxy-revoke.example',
            issuer='CN=External CA',
            serial_number=format(cert_obj.serial_number, 'x'),
            valid_from=datetime.utcnow() - timedelta(days=1),
            valid_to=datetime.utcnow() + timedelta(days=90),
            key_algo='RSA 2048',
            source='acme_client',
            imported_from='acme_client',
        )
        db.session.add_all([account, cert])
        db.session.flush()
        order = AcmeClientOrder(
            domains='["proxy-revoke.example"]',
            challenge_type='dns-01',
            environment='custom',
            status='valid',
            is_proxy_order=True,
            certificate_id=cert.id,
            account_id='internal-acme-account',
            acme_client_account_id=account.id,
        )
        db.session.add(order)
        db.session.commit()
        result = {
            'account_id': account.id,
            'certificate_id': cert.id,
            'order_id': order.id,
            'certificate_der': cert_obj.public_bytes(serialization.Encoding.DER),
        }

    yield result

    with app.app_context():
        db.session.query(AcmeClientOrder).filter_by(id=result['order_id']).delete()
        db.session.query(Certificate).filter_by(id=result['certificate_id']).delete()
        db.session.query(AcmeClientAccount).filter_by(id=result['account_id']).delete()
        db.session.commit()


def test_proxy_new_order_forwards_replaces_when_present(client, monkeypatch):
    from api.acme import acme_proxy_api

    cert_id = f'{_b64url(b"aki")}.{_b64url(b"serial")}'
    payload = {
        'identifiers': [{'type': 'dns', 'value': 'proxy-revoke.example'}],
        'replaces': cert_id,
    }
    service = MagicMock()
    service.new_order.return_value = ({'status': 'pending'}, 'order-id')
    monkeypatch.setattr(
        acme_proxy_api,
        'verify_proxy_jws',
        lambda: (True, payload, None, None),
    )
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    monkeypatch.setattr(
        acme_proxy_api,
        '_kid_account_thumbprint',
        lambda protected: None,
    )

    response = client.post(
        '/acme/proxy/new-order',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json',
    )

    assert response.status_code == 201
    assert service.new_order.call_args.kwargs['replaces'] == cert_id


def test_proxy_revoke_relays_upstream_status_and_revokes_local(
    app, client, proxy_revocation_rows, monkeypatch,
):
    from api.acme import acme_proxy_api

    payload = {
        'certificate': _b64url(proxy_revocation_rows['certificate_der']),
        'reason': 4,
    }
    service = MagicMock()
    service.account.id = proxy_revocation_rows['account_id']
    service.revoke_certificate.return_value.status_code = 200
    local_revoke = MagicMock()

    monkeypatch.setattr(
        acme_proxy_api,
        'verify_proxy_jws',
        lambda: (True, payload, None, None),
    )
    monkeypatch.setattr(
        acme_proxy_api,
        '_request_protected_header',
        lambda: {'kid': 'https://ucm.example/acme/proxy/acct/internal-acme-account'},
    )
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    monkeypatch.setattr(
        'services.cert_service.CertificateService.revoke_certificate',
        local_revoke,
    )

    response = client.post(
        '/acme/proxy/revoke-cert',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json',
    )

    assert response.status_code == 200
    service.revoke_certificate.assert_called_once()
    forwarded_cert, forwarded_reason = service.revoke_certificate.call_args.args
    assert forwarded_cert.public_bytes(serialization.Encoding.DER) == proxy_revocation_rows['certificate_der']
    assert forwarded_reason == 4
    local_revoke.assert_called_once_with(
        cert_id=proxy_revocation_rows['certificate_id'],
        reason='superseded',
        username='acme_proxy',
    )


def test_proxy_revoke_rejects_invalid_reason(app, client, proxy_revocation_rows, monkeypatch):
    from api.acme import acme_proxy_api

    payload = {
        'certificate': _b64url(proxy_revocation_rows['certificate_der']),
        'reason': 7,
    }
    monkeypatch.setattr(
        acme_proxy_api,
        'verify_proxy_jws',
        lambda: (True, payload, None, None),
    )

    response = client.post(
        '/acme/proxy/revoke-cert',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json',
    )

    assert response.status_code == 400
    assert response.get_json()['type'].endswith(':malformed')


def test_proxy_revoke_relays_upstream_failure_status(
    app, client, proxy_revocation_rows, monkeypatch,
):
    from api.acme import acme_proxy_api

    payload = {
        'certificate': _b64url(proxy_revocation_rows['certificate_der']),
        'reason': 1,
    }
    service = MagicMock()
    service.account.id = proxy_revocation_rows['account_id']
    service.revoke_certificate.return_value.status_code = 403

    monkeypatch.setattr(
        acme_proxy_api,
        'verify_proxy_jws',
        lambda: (True, payload, None, None),
    )
    monkeypatch.setattr(
        acme_proxy_api,
        '_request_protected_header',
        lambda: {'kid': 'https://ucm.example/acme/proxy/acct/internal-acme-account'},
    )
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)

    response = client.post(
        '/acme/proxy/revoke-cert',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json',
    )

    assert response.status_code == 403
    assert response.get_json()['detail'] == 'Upstream certificate revocation failed'
