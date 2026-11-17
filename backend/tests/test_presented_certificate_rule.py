"""Follow-up to the protocol renewal rule: the same rule authenticates EST
/simpleenroll and /serverkeygen over mTLS, the mTLS login refuses a revoked
certificate, and approving a queued SCEP request issues its certificate."""

import base64
import json

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SCEPRequest, db
from services.cert.issued_lookup import NOT_YET_VALID, REVOKED, issued_certificate_status
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


def _revoke(app, ca_id, leaf):
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row, _ = issued_certificate_status(ca, leaf)
        row.revoked = True
        db.session.commit()


class TestEstEnrolmentOverMtls:

    def test_revoked_certificate_cannot_enrol_another(self, client, app, est_config):
        leaf, key = _enrol(client, 'mtls-enrol.example.test')
        _revoke(app, est_config['id'], leaf)
        csr, _ = _csr('anything-else.example.test')
        r = _post_csr(client, 'simpleenroll', csr,
                      client_cert_pem=leaf.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 403, r.data

    def test_revoked_certificate_cannot_use_serverkeygen(self, client, app, est_config):
        leaf, key = _enrol(client, 'mtls-keygen.example.test')
        _revoke(app, est_config['id'], leaf)
        csr, _ = _csr('keygen.example.test')
        r = _post_csr(client, 'serverkeygen', csr,
                      client_cert_pem=leaf.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 403, r.data

    def test_valid_certificate_still_enrols(self, client, app, est_config):
        leaf, key = _enrol(client, 'mtls-ok.example.test')
        csr, _ = _csr('second.example.test')
        r = _post_csr(client, 'simpleenroll', csr,
                      client_cert_pem=leaf.public_bytes(serialization.Encoding.PEM).decode())
        assert r.status_code == 200, r.data


class TestMtlsLoginRevocation:

    def test_revoked_enrolled_certificate_opens_no_session(self, app, auth_client, create_ca):
        from services.mtls_auth_service import MTLSAuthService
        ca = create_ca(cn='mTLS login revocation CA')
        r = auth_client.post('/api/v2/mtls/certificates', data=json.dumps(
            {'ca_id': ca['id'], 'name': 'revocable'}), content_type='application/json')
        assert r.status_code == 201, r.get_json()
        data = r.get_json()['data']
        cert = x509.load_pem_x509_certificate(data['certificate'].encode(), default_backend())
        info = {'serial': format(cert.serial_number, 'X'),
                'fingerprint': cert.fingerprint(hashes.SHA256()).hex().upper()}
        with app.app_context():
            user, _, err = MTLSAuthService.authenticate_certificate(info)
            assert user is not None, err
            row = db.session.get(Certificate, data['certificate_id'])
            row.revoked = True
            db.session.commit()
            user, _, err = MTLSAuthService.authenticate_certificate(info)
            assert user is None
            assert 'revoked' in err.lower()
            from models.auth_certificate import AuthCertificate
            AuthCertificate.query.filter_by(id=data['id']).delete()
            db.session.delete(db.session.get(Certificate, data['certificate_id']))
            db.session.commit()


class TestScepRestApproval:

    def test_approving_a_queued_request_issues_its_certificate(self, app, auth_client, create_ca):
        ca = create_ca(cn='SCEP REST approval CA')
        csr, _ = _csr('queued.example.test')
        with app.app_context():
            ca_row = db.session.get(CA, ca['id'])
            req = SCEPRequest(transaction_id='rest-approve-1', ca_refid=ca_row.refid,
                              csr=base64.b64encode(csr.public_bytes(serialization.Encoding.DER)).decode(),
                              status='pending', subject='CN=queued.example.test')
            db.session.add(req)
            db.session.commit()
            req_id = req.id
        r = auth_client.post(f'/api/v2/scep/{req_id}/approve', data='{}', content_type='application/json')
        assert r.status_code == 200, r.get_json()
        with app.app_context():
            req = db.session.get(SCEPRequest, req_id)
            assert req.status == 'approved' and req.cert_refid
            row = Certificate.query.filter_by(refid=req.cert_refid).first()
            assert row is not None and row.crt
            db.session.delete(row)
            db.session.delete(req)
            db.session.commit()


def test_not_yet_valid_is_its_own_state(app, create_ca):
    from datetime import datetime, timedelta, timezone
    from utils.key_codec import load_pem_bytes
    ca = create_ca(cn='Issued status future CA')
    with app.app_context():
        ca_row = db.session.get(CA, ca['id'])
        ca_cert = x509.load_pem_x509_certificate(base64.b64decode(ca_row.crt), default_backend())
        ca_key = serialization.load_pem_private_key(load_pem_bytes(ca_row.prv, context='t'), password=None)
        key = rsa.generate_private_key(65537, 2048)
        now = datetime.now(timezone.utc)
        leaf = (x509.CertificateBuilder().subject_name(
            x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'future.example.test')]))
            .issuer_name(ca_cert.subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now + timedelta(days=2)).not_valid_after(now + timedelta(days=30))
            .sign(ca_key, hashes.SHA256()))
        row = Certificate(refid='future-leaf', descr='future', caref=ca_row.refid,
                          crt=base64.b64encode(leaf.public_bytes(serialization.Encoding.PEM)).decode(),
                          cert_type='server_cert', subject=leaf.subject.rfc4514_string(),
                          issuer=leaf.issuer.rfc4514_string(), serial_number=str(leaf.serial_number),
                          valid_from=(now + timedelta(days=2)).replace(tzinfo=None),
                          valid_to=(now + timedelta(days=30)).replace(tzinfo=None), source='manual')
        db.session.add(row)
        db.session.commit()
        try:
            assert issued_certificate_status(ca_row, leaf)[1] == NOT_YET_VALID
        finally:
            db.session.delete(row)
            db.session.commit()
