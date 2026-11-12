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
from tests.seeded_rows import ensure_acme_account
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
        ensure_acme_account('internal-acme-account')
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
    # new-order requires a kid-signed JWS from an active account.
    monkeypatch.setattr(
        acme_proxy_api,
        '_request_protected_header',
        lambda: {'kid': 'http://localhost/acme/proxy/acct/replaces-acct'},
    )
    active_account = MagicMock()
    active_account.status = 'valid'
    monkeypatch.setattr(acme_proxy_api.AcmeService, 'get_account_by_kid',
                        lambda *_args: active_account)

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
    # RFC 8555 §7.6: 200 without a body, so no HTML media type
    assert response.data == b'' and response.headers['Content-Length'] == '0'
    assert 'Content-Type' not in response.headers
    assert response.headers['Link'] == '<http://localhost/acme/proxy/directory>;rel="index"'
    service.revoke_certificate.assert_called_once()
    forwarded_cert, forwarded_reason = service.revoke_certificate.call_args.args
    assert forwarded_cert.public_bytes(serialization.Encoding.DER) == proxy_revocation_rows['certificate_der']
    assert forwarded_reason == 4
    local_revoke.assert_called_once_with(
        cert_id=proxy_revocation_rows['certificate_id'],
        reason='superseded',
        username='acme_proxy',
        revoke_related=False,
    )


@pytest.mark.parametrize('held_as, code, local', [
    ('certificateHold', 1, 'keyCompromise'),
    ('certificateHold', 6, None),
    ('superseded', 1, None),
])
def test_proxy_revoke_makes_a_local_hold_final_only(
    app, client, proxy_revocation_rows, monkeypatch, held_as, code, local,
):
    from api.acme import acme_proxy_api

    with app.app_context():
        row = db.session.get(Certificate, proxy_revocation_rows['certificate_id'])
        row.revoked, row.revoke_reason, row.revoked_at = True, held_as, datetime.utcnow()
        db.session.commit()
    payload = {'certificate': _b64url(proxy_revocation_rows['certificate_der']), 'reason': code}
    service = MagicMock()
    service.account.id = proxy_revocation_rows['account_id']
    service.revoke_certificate.return_value.status_code = 200
    local_revoke = MagicMock()
    monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws', lambda: (True, payload, None, None))
    monkeypatch.setattr(
        acme_proxy_api, '_request_protected_header',
        lambda: {'kid': 'https://ucm.example/acme/proxy/acct/internal-acme-account'})
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    monkeypatch.setattr('services.cert_service.CertificateService.revoke_certificate', local_revoke)

    response = client.post(
        '/acme/proxy/revoke-cert',
        data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
        content_type='application/jose+json')

    assert response.status_code == 200
    if local:
        local_revoke.assert_called_once_with(
            cert_id=proxy_revocation_rows['certificate_id'], reason=local, username='acme_proxy',
            revoke_related=False)
    else:
        local_revoke.assert_not_called()


@pytest.mark.parametrize('reason', [7, 8, 11, '1'])
def test_proxy_revoke_rejects_invalid_reason(app, client, proxy_revocation_rows, monkeypatch, reason):
    from api.acme import acme_proxy_api

    payload = {
        'certificate': _b64url(proxy_revocation_rows['certificate_der']),
        'reason': reason,
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

    # RFC 8555 §7.6: an unsupported reason is badRevocationReason, not malformed
    assert response.status_code == 400
    assert response.get_json()['type'].endswith(':badRevocationReason')


def test_the_client_never_sends_remove_from_crl():
    from services.acme.acme_client_service import AcmeClientService
    with pytest.raises(ValueError):
        AcmeClientService.validate_revocation_reason(8)


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
    problem = response.get_json()
    assert problem['type'] == 'urn:ietf:params:acme:error:serverInternal'
    assert 'HTTP 403' in problem['detail']


def test_proxy_revoke_leaves_the_related_member_alone(
    app, client, proxy_revocation_rows, monkeypatch,
):
    """RFC 8555 §7.6: the key holder revokes the certificate presented, not its pair partner."""
    from api.acme import acme_proxy_api
    from services.acme import upstream_revocation

    with app.app_context():
        a = db.session.get(Certificate, proxy_revocation_rows['certificate_id'])
        b = Certificate(
            refid=str(uuid4()), descr='proxy-partner.example', crt=a.crt,
            subject='CN=proxy-partner.example', issuer='CN=External CA',
            serial_number=format(uuid4().int >> 64, 'x'), source='acme_client',
            valid_from=datetime.utcnow() - timedelta(days=1),
            valid_to=datetime.utcnow() + timedelta(days=90),
            related_certificate_id=a.id)
        db.session.add(b)
        db.session.flush()
        a.related_certificate_id = b.id
        db.session.commit()
        partner_id = b.id
    sent = []
    monkeypatch.setattr(upstream_revocation, 'propagate_acme_revocation',
                        lambda cert, reason: sent.append(cert.id) or ('revoked', None))
    payload = {'certificate': _b64url(proxy_revocation_rows['certificate_der']), 'reason': 1}
    service = MagicMock()
    service.account.id = proxy_revocation_rows['account_id']
    service.revoke_certificate.return_value.status_code = 200
    monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws', lambda: (True, payload, None, None))
    monkeypatch.setattr(
        acme_proxy_api, '_request_protected_header',
        lambda: {'kid': 'https://ucm.example/acme/proxy/acct/internal-acme-account'})
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    try:
        response = client.post(
            '/acme/proxy/revoke-cert',
            data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
            content_type='application/jose+json')

        assert response.status_code == 200
        with app.app_context():
            db.session.expire_all()
            assert db.session.get(Certificate, proxy_revocation_rows['certificate_id']).revoked
            assert db.session.get(Certificate, partner_id).revoked is not True
        assert partner_id not in sent
        service.revoke_certificate.assert_called_once()
    finally:
        with app.app_context():
            from models import RevokedSerial
            for cid in (proxy_revocation_rows['certificate_id'], partner_id):
                row = db.session.get(Certificate, cid)
                if row is not None:
                    row.related_certificate_id = None
            RevokedSerial.query.filter(
                RevokedSerial.certificate_id.in_(
                    [proxy_revocation_rows['certificate_id'], partner_id])).delete(
                synchronize_session=False)
            db.session.query(Certificate).filter_by(id=partner_id).delete()
            db.session.commit()


def test_proxy_revoke_leaves_a_certificate_its_ca_recorded_as_revoked(
    app, client, create_ca, proxy_revocation_rows, monkeypatch,
):
    """Revoked for good by its CA's record: already revoked, no local revocation is tried."""
    from api.acme import acme_proxy_api
    from models import CA, RevokedSerial

    ca = create_ca(cn=f'Proxy record CA {uuid4().hex[:6]}')
    with app.app_context():
        refid = db.session.get(CA, ca['id']).refid
        row = db.session.get(Certificate, proxy_revocation_rows['certificate_id'])
        row.caref = refid
        db.session.add(RevokedSerial(caref=refid, serial_number=str(0xCAFE1234), revoke_reason='keyCompromise',
                                     revoked_at=datetime(2026, 1, 2), valid_to=datetime(2099, 1, 1)))
        db.session.commit()
    payload = {'certificate': _b64url(proxy_revocation_rows['certificate_der']), 'reason': 4}
    service = MagicMock()
    service.account.id = proxy_revocation_rows['account_id']
    service.revoke_certificate.return_value.status_code = 200
    local_revoke = MagicMock()
    monkeypatch.setattr(acme_proxy_api, 'verify_proxy_jws', lambda: (True, payload, None, None))
    monkeypatch.setattr(
        acme_proxy_api, '_request_protected_header',
        lambda: {'kid': 'https://ucm.example/acme/proxy/acct/internal-acme-account'})
    monkeypatch.setattr(acme_proxy_api, 'get_proxy_service', lambda slug=None: service)
    monkeypatch.setattr('services.cert_service.CertificateService.revoke_certificate', local_revoke)
    try:
        response = client.post(
            '/acme/proxy/revoke-cert',
            data=json.dumps({'protected': 'stub', 'payload': 'stub', 'signature': 'stub'}),
            content_type='application/jose+json')
        assert response.status_code == 200
        local_revoke.assert_not_called()
    finally:
        with app.app_context():
            RevokedSerial.query.filter_by(caref=refid).delete()
            row = db.session.get(Certificate, proxy_revocation_rows['certificate_id'])
            row.caref = None
            db.session.commit()
            from services.ca_service import CAService
            CAService.delete_ca(ca['id'])
