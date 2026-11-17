"""Final review follow-ups: a revoked-then-deleted certificate opens no mTLS
session, a certificate from another trusted authority may still enrol over
EST, a superseded certificate does not enrol again, the REST SCEP approval
emits the issuance webhook, and assigning a revoked certificate is refused."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SCEPRequest, db
from models.auth_certificate import AuthCertificate
from tests.test_est_rfc7030 import (  # noqa: F401
    EST_BASE, _basic_auth, _post_csr, est_config,
)


def _csr(cn, key=None):
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return x509.CertificateSigningRequestBuilder().subject_name(
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])).sign(key, hashes.SHA256()), key


def _enrol(client, cn):
    csr, key = _csr(cn)
    r = _post_csr(client, 'simpleenroll', csr, headers=_basic_auth())
    assert r.status_code == 200, r.data
    certs = pkcs7.load_der_pkcs7_certificates(base64.b64decode(r.data))
    return [c for c in certs if not c.extensions.get_extension_for_oid(
        x509.ExtensionOID.BASIC_CONSTRAINTS).value.ca][0], key


def _pem(cert):
    return cert.public_bytes(serialization.Encoding.PEM).decode()


def test_revoked_then_deleted_certificate_opens_no_session(app, auth_client, create_ca):
    from services.mtls_auth_service import MTLSAuthService
    ca = create_ca(cn='mTLS deleted revoked CA')
    r = auth_client.post('/api/v2/mtls/certificates', data=json.dumps(
        {'ca_id': ca['id'], 'name': 'to-delete'}), content_type='application/json')
    assert r.status_code == 201, r.get_json()
    data = r.get_json()['data']
    cert = x509.load_pem_x509_certificate(data['certificate'].encode(), default_backend())
    info = {'serial': format(cert.serial_number, 'X'),
            'fingerprint': cert.fingerprint(hashes.SHA256()).hex().upper(), 'cert_pem': _pem(cert)}
    r = auth_client.post(f"/api/v2/certificates/{data['certificate_id']}/revoke",
                         data=json.dumps({'reason': 'keyCompromise'}), content_type='application/json')
    assert r.status_code in (200, 201), r.get_json()
    r = auth_client.delete(f"/api/v2/certificates/{data['certificate_id']}")
    assert r.status_code in (200, 204), r.data
    with app.app_context():
        try:
            user, _, err = MTLSAuthService.authenticate_certificate(info)
            assert user is None and 'revoked' in err.lower()
        finally:
            AuthCertificate.query.filter_by(id=data['id']).delete()
            db.session.commit()


def test_certificate_of_another_trusted_authority_may_still_enrol(client, est_config):
    """RFC 7030 §3.3.2: the TLS layer's trust decision stands for a
    certificate this CA did not sign."""
    key = rsa.generate_private_key(65537, 2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'manufacturer-device')])
    now = datetime.now(timezone.utc)
    foreign = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
               .public_key(key.public_key()).serial_number(x509.random_serial_number())
               .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
               .sign(key, hashes.SHA256()))
    csr, _ = _csr('bootstrap.example.test')
    r = _post_csr(client, 'simpleenroll', csr, client_cert_pem=_pem(foreign))
    assert r.status_code == 200, r.data


def test_superseded_certificate_does_not_enrol_again(client, app, est_config):
    leaf, key = _enrol(client, 'superseded.example.test')
    csr, _ = _csr('superseded.example.test', key=key)
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 200, r.data
    r = _post_csr(client, 'simplereenroll', csr, client_cert_pem=_pem(leaf))
    assert r.status_code == 403 and b'superseded' in r.data, r.data
    csr2, _ = _csr('another.example.test')
    r = _post_csr(client, 'simpleenroll', csr2, client_cert_pem=_pem(leaf))
    assert r.status_code == 403 and b'superseded' in r.data, r.data


def test_rest_approval_emits_the_issuance_webhook(app, auth_client, create_ca, monkeypatch):
    import services.webhook_service as webhook_service
    seen = []
    monkeypatch.setattr(webhook_service, 'emit_cert_issued', lambda payload, ca_refid=None: seen.append(payload))
    ca = create_ca(cn='SCEP REST webhook CA')
    csr, _ = _csr('webhook.example.test')
    with app.app_context():
        ca_row = db.session.get(CA, ca['id'])
        req = SCEPRequest(transaction_id='rest-webhook-1', ca_refid=ca_row.refid,
                          csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                          status='pending', subject='CN=webhook.example.test')
        db.session.add(req)
        db.session.commit()
        req_id = req.id
    r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
    assert r.status_code == 200, r.get_json()
    assert len(seen) == 1
    with app.app_context():
        req = db.session.get(SCEPRequest, req_id)
        row = Certificate.query.filter_by(refid=req.cert_refid).first()
        db.session.delete(row)
        db.session.delete(req)
        db.session.commit()


def test_assigning_a_revoked_certificate_is_refused(app, auth_client, create_ca):
    from services.cert_service import CertificateService
    ca = create_ca(cn='mTLS assign revoked CA')
    with app.app_context():
        ca_row = db.session.get(CA, ca['id'])
        row = CertificateService.create_certificate(
            descr='assign-revoked', caref=ca_row.refid, dn={'CN': 'assign@mtls'},
            cert_type='usr_cert', key_type='2048', validity_days=30, username='admin')
        row.revoked = True
        db.session.commit()
        row_id = row.id
    try:
        r = auth_client.post('/api/v2/mtls/assign', data=json.dumps({'cert_id': row_id}),
                             content_type='application/json')
        assert r.status_code == 400, (r.status_code, r.get_json())
    finally:
        with app.app_context():
            db.session.delete(db.session.get(Certificate, row_id))
            db.session.commit()
