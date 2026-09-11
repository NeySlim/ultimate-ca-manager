"""Follow-up to the mTLS PKCS#12 binding: every route that joins an mTLS
enrolment to a private key uses the same identity rule, and enrolment
itself cannot be used to squat another certificate's serial number.
"""

import base64
import importlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from models import CA, Certificate, SystemConfig, db
from models.auth_certificate import AuthCertificate
from services.mtls_enrollment import certificate_row_for, parse_validity_days
from tests.test_mtls_p12_identity import (  # noqa: F401  (fixture + helpers)
    _forged_cert_with_serial, _post, _serial_int, victim,
)


def _login(app, username, password):
    client = app.test_client()
    r = _post(client, '/api/v2/auth/login', {'username': username, 'password': password})
    assert r.status_code == 200, r.data
    return client


class TestUserCertificateRoutesShareTheRule:

    @pytest.mark.parametrize('fmt', ['pem', 'pkcs12', 'jks'])
    def test_forged_serial_exports_no_key(self, app, viewer_client, victim, fmt):
        forged = _forged_cert_with_serial(_serial_int(victim['serial']))
        r = _post(viewer_client, '/api/v2/mtls/enroll-import', {'pem': forged, 'name': 'forged'})
        # A forged self-signed certificate is no longer enrollable at all
        assert r.status_code == 400, (r.status_code, r.get_json())

    def test_legacy_enrolment_by_serial_exports_only_its_own_row(self, app, auth_client, victim):
        """An enrolment stored before fingerprints and PEMs were kept still
        resolves, but only to the row whose certificate carries that serial
        number under that issuer."""
        with app.app_context():
            row = db.session.get(Certificate, victim['id'])
            legacy = AuthCertificate(
                user_id=1, cert_serial=row.serial_number, cert_subject=row.subject,
                cert_issuer=row.issuer, cert_fingerprint='', name='legacy', enabled=True,
            )
            db.session.add(legacy)
            db.session.commit()
            legacy_id = legacy.id
        try:
            r = auth_client.get(f'/api/v2/user-certificates/{legacy_id}/export?format=pem')
            assert r.status_code == 200, r.data[:200]
            assert b'PRIVATE KEY' in r.data
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(id=legacy_id).delete()
                db.session.commit()


class TestSerialInterpretation:

    def test_decimal_and_hexadecimal_readings_never_cross(self, app):
        """Rows with serials 10 and 16 (0x10) under one issuer: a legacy
        enrolment of serial '10' must resolve to the certificate whose
        serial IS 10, never to 16 because '10' also reads as hexadecimal."""
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Serial reading CA')])
        now = datetime.now(timezone.utc)
        rows = {}
        with app.app_context():
            for serial in (16, 10):
                key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                cert = (
                    x509.CertificateBuilder()
                    .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f'leaf-{serial}')]))
                    .issuer_name(ca_name).public_key(key.public_key()).serial_number(serial)
                    .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=30))
                    .sign(ca_key, hashes.SHA256())
                )
                row = Certificate(
                    refid=f'serial-reading-{serial}', descr=f'leaf-{serial}',
                    crt=base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode(),
                    cert_type='usr_cert', subject=cert.subject.rfc4514_string(),
                    issuer=ca_name.rfc4514_string(), serial_number=str(serial),
                    valid_from=now.replace(tzinfo=None), valid_to=(now + timedelta(days=30)).replace(tzinfo=None),
                )
                db.session.add(row)
                db.session.flush()
                rows[serial] = row.id
            legacy = AuthCertificate(
                user_id=1, cert_serial='10', cert_subject='CN=leaf-10',
                cert_issuer=ca_name.rfc4514_string(), cert_fingerprint='', name='legacy-10', enabled=True,
            )
            db.session.add(legacy)
            db.session.commit()
            try:
                resolved = certificate_row_for(legacy)
                assert resolved is not None and resolved.id == rows[10]
            finally:
                db.session.delete(legacy)
                for rid in rows.values():
                    db.session.delete(db.session.get(Certificate, rid))
                db.session.commit()


class TestEnrolmentCannotSquatASerial:

    def test_self_signed_certificate_is_refused(self, auth_client):
        forged = _forged_cert_with_serial(12345)
        r = _post(auth_client, '/api/v2/mtls/enroll-import', {'pem': forged, 'name': 'x'})
        assert r.status_code == 400
        assert b'not issued by a CA of this server' in r.data

    def test_login_refuses_a_certificate_that_is_not_the_enrolled_one(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='mTLS login identity CA')
        r = _post(auth_client, '/api/v2/mtls/certificates', {'ca_id': ca_data['id'], 'name': 'login'})
        assert r.status_code == 201, r.get_json()
        data = r.get_json()['data']
        module = importlib.import_module('services.mtls_auth_service')
        service = next(getattr(module, n) for n in dir(module) if n.lower().endswith('authservice'))
        try:
            with app.app_context():
                enrolled = x509.load_pem_x509_certificate(data['certificate'].encode(), default_backend())
                good = {
                    'serial': format(enrolled.serial_number, 'X'),
                    'fingerprint': enrolled.fingerprint(hashes.SHA256()).hex().upper(),
                }
                user, auth_cert, err = service.authenticate_certificate(good)
                assert user is not None, err
                bad = dict(good, fingerprint='00' * 32)
                user, auth_cert, err = service.authenticate_certificate(bad)
                assert user is None
                assert err == 'Certificate not enrolled'
        finally:
            with app.app_context():
                AuthCertificate.query.filter_by(id=data['id']).delete()
                row = db.session.get(Certificate, data['certificate_id'])
                if row:
                    db.session.delete(row)
                db.session.commit()


class TestListingsAndInputs:

    def test_operator_only_sees_own_available_certificates(self, app, auth_client, create_ca, create_user):
        ca_data = create_ca(cn='mTLS available CA')
        from services.cert_service import CertificateService
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = CertificateService.create_certificate(
                descr='admin-owned', caref=ca.refid, dn={'CN': 'admin-owned@mtls'},
                cert_type='usr_cert', key_type='2048', validity_days=30, username='admin',
            )
            db.session.commit()
            row_id = row.id
        user = create_user(role='operator')
        operator = _login(app, user['username'], 'TestPass123!')
        try:
            r = operator.get('/api/v2/mtls/available-certificates')
            assert r.status_code == 200
            assert row_id not in [c['id'] for c in r.get_json()['data']]
            r = auth_client.get('/api/v2/mtls/available-certificates')
            assert row_id in [c['id'] for c in r.get_json()['data']]
        finally:
            with app.app_context():
                db.session.delete(db.session.get(Certificate, row_id))
                db.session.commit()

    def test_admin_generation_falls_back_to_the_configured_mtls_ca(self, app, auth_client, create_ca):
        ca_data = create_ca(cn='mTLS configured CA')
        with app.app_context():
            ca = db.session.get(CA, ca_data['id'])
            row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
            previous = row.value if row else None
            if row is None:
                db.session.add(SystemConfig(key='mtls_trusted_ca_id', value=ca.refid))
            else:
                row.value = ca.refid
            db.session.commit()
        try:
            r = _post(auth_client, '/api/v2/users/1/mtls/certificates', {'mode': 'generate'})
            assert r.status_code == 201, r.get_json()
            data = r.get_json()['data']
        finally:
            with app.app_context():
                row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
                if previous is None:
                    db.session.delete(row)
                else:
                    row.value = previous
                db.session.commit()
        with app.app_context():
            AuthCertificate.query.filter_by(id=data['id']).delete()
            cert = db.session.get(Certificate, data['cert_id'])
            if cert:
                db.session.delete(cert)
            db.session.commit()

    @pytest.mark.parametrize('value', [True, 1.9, '7.5', 'abc', 0, 3651, [30]])
    def test_validity_parser_rejects_non_integers(self, value):
        assert parse_validity_days(value) is None

    @pytest.mark.parametrize('value,expected', [(None, 365), (30, 30), ('30', 30), (30.0, 30), (3650, 3650)])
    def test_validity_parser_accepts_integers(self, value, expected):
        assert parse_validity_days(value) == expected
