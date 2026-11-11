"""An account recreated under a deleted user's name does not inherit its certificates.

The self-service mTLS routes took `Certificate.created_by == username` as proof
of ownership, so whoever got the name of a deleted account next could list,
enrol and then download the key of a certificate its holder never revoked.
A certificate made before the current account existed is not its own.
"""
import base64
import json

import pytest

from models import db, User, Certificate
from models.auth_certificate import AuthCertificate
from tests.test_user_certificate_key_export_guard import _enrolment_for

NAME = 'mtls_namesake_probe'


def _login(app, username):
    client = app.test_client()
    answer = client.post('/api/v2/auth/login',
                         data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                         content_type='application/json')
    assert answer.status_code == 200, answer.data[:300]
    return client


def _own(app, certificate_id, username):
    with app.app_context():
        certificate = db.session.get(Certificate, certificate_id)
        certificate.created_by, certificate.cert_type = username, 'usr_cert'
        db.session.commit()


def _certificate_of(app, enrolment_id):
    with app.app_context():
        from services.mtls_enrollment import certificate_row_for
        return certificate_row_for(db.session.get(AuthCertificate, enrolment_id)).id


@pytest.fixture
def left_behind(app, auth_client, create_user, create_cert, monkeypatch):
    """The certificate of a deleted user, still valid, and a namesake logged in."""
    create_user(username=NAME, role='operator')
    enrolment_id, old_user_id = _enrolment_for(app, create_cert, NAME, 'namesake-probe')
    certificate_id = _certificate_of(app, enrolment_id)
    _own(app, certificate_id, NAME)

    from services.cert_service import CertificateService

    def _offline(**_kwargs):
        raise ValueError('CA is offline and cannot sign')
    with monkeypatch.context() as patched:
        patched.setattr(CertificateService, 'revoke_certificate', _offline)
        answer = auth_client.delete(f'/api/v2/users/{old_user_id}')
    assert answer.status_code == 200, answer.data[:300]
    with app.app_context():
        kept = db.session.get(Certificate, certificate_id)
        assert kept is not None and not kept.revoked

    create_user(username=NAME, role='operator')
    with app.app_context():
        assert User.query.filter_by(username=NAME).count() == 1
    yield {'certificate_id': certificate_id, 'enrolment_id': enrolment_id,
           'client': _login(app, NAME)}
    with app.app_context():
        for row in AuthCertificate.query.join(User, AuthCertificate.user_id == User.id).filter(
                User.username == NAME).all():
            db.session.delete(row)
        user = User.query.filter_by(username=NAME).first()
        if user is not None:
            db.session.delete(user)
        certificate = db.session.get(Certificate, certificate_id)
        if certificate is not None:
            db.session.delete(certificate)
        db.session.commit()


class TestANamesakeGetsNothing:
    def test_it_is_not_offered(self, left_behind):
        answer = left_behind['client'].get('/api/v2/mtls/available-certificates')
        assert answer.status_code == 200, answer.data[:300]
        offered = [c['id'] for c in json.loads(answer.data)['data']]
        assert left_behind['certificate_id'] not in offered

    def test_it_cannot_be_assigned(self, app, left_behind):
        answer = left_behind['client'].post(
            '/api/v2/mtls/assign', data=json.dumps({'cert_id': left_behind['certificate_id']}),
            content_type='application/json')
        assert answer.status_code == 403, answer.data[:300]
        with app.app_context():
            namesake = User.query.filter_by(username=NAME).first()
            assert AuthCertificate.query.filter_by(user_id=namesake.id).count() == 0

    def test_it_cannot_be_enrolled_from_its_pem(self, app, left_behind):
        from cryptography import x509
        with app.app_context():
            row = db.session.get(Certificate, left_behind['certificate_id'])
            pem = base64.b64decode(row.crt)
            # This route looks the record up by the decimal serial it reads from the PEM
            row.serial_number = str(x509.load_pem_x509_certificate(pem).serial_number)
            db.session.commit()
        answer = left_behind['client'].post(
            '/api/v2/mtls/enroll-import', data=json.dumps({'pem': pem.decode()}),
            content_type='application/json')
        assert answer.status_code == 403, answer.data[:300]
        assert b"another record" in answer.data, answer.data[:300]

    def test_its_key_cannot_be_downloaded(self, app, left_behind):
        # Whatever the assignment answered, the key never leaves through the namesake
        left_behind['client'].post(
            '/api/v2/mtls/assign', data=json.dumps({'cert_id': left_behind['certificate_id']}),
            content_type='application/json')
        with app.app_context():
            owner_id = User.query.filter_by(username=NAME).first().id
            ids = [r.id for r in AuthCertificate.query.filter_by(user_id=owner_id)]
        for enrolment_id in ids + [left_behind['enrolment_id']]:
            answer = left_behind['client'].post(
                f'/api/v2/mtls/certificates/{enrolment_id}/download',
                data=json.dumps({'format': 'pkcs12', 'password': 'Passw0rd!2026x'}),
                content_type='application/json')
            assert answer.status_code == 404, answer.data[:300]


class TestTheAccountsOwnCertificatesStillWork:
    def test_one_made_after_the_account_is_offered_and_assignable(
            self, app, left_behind, create_cert):
        mine = create_cert(cn='namesake-own.example')
        _own(app, mine['id'], NAME)
        client = left_behind['client']
        offered = [c['id'] for c in json.loads(
            client.get('/api/v2/mtls/available-certificates').data)['data']]
        assert mine['id'] in offered
        answer = client.post('/api/v2/mtls/assign', data=json.dumps({'cert_id': mine['id']}),
                             content_type='application/json')
        assert answer.status_code in (200, 201), answer.data[:300]
        with app.app_context():
            for enrolment in AuthCertificate.query.join(User, AuthCertificate.user_id == User.id).filter(
                    User.username == NAME).all():
                db.session.delete(enrolment)
            db.session.delete(db.session.get(Certificate, mine['id']))
            db.session.commit()
