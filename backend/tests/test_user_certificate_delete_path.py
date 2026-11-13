"""Deleting a user certificate deletes what the certificate owns.

The route removed the `Certificate` row with a bare `session.delete`: the
files stayed on disk, the approval requests, deploy bindings and ACME orders
kept pointing at a row that was gone, and the revocation records kept a
dangling foreign key that PostgreSQL refuses outright.

Removing the enrolment withdraws access to UCM and nothing more: the
certificate stayed valid for every other service trusting the same authority.
It is revoked on the way out, so the withdrawal reaches the CRL and the
responder, and the operator still has a single gesture.
"""
import json

import pytest

from models import db
from tests.test_user_certificate_key_export_guard import _enrolment_for

pytestmark = pytest.mark.usefixtures('drop_new_users')


@pytest.fixture
def an_operator(app, create_user):
    create_user(username='op_delete_probe', role='operator')
    client = app.test_client()
    answer = client.post(
        '/api/v2/auth/login',
        data=json.dumps({'username': 'op_delete_probe',
                         'password': 'TestPass123!'}),
        content_type='application/json')
    assert answer.status_code == 200, answer.data
    return client


@pytest.fixture
def an_enrolment(app, create_user, create_cert):
    create_user(username='owner_delete_probe', role='viewer')
    enrolment_id, _owner = _enrolment_for(
        app, create_cert, 'owner_delete_probe', 'delete-path-probe')
    yield enrolment_id
    with app.app_context():
        from models.auth_certificate import AuthCertificate
        row = db.session.get(AuthCertificate, enrolment_id)
        if row:
            db.session.delete(row)
            db.session.commit()


def _certificate_id_of(app, enrolment_id):
    with app.app_context():
        from models.auth_certificate import AuthCertificate
        from services.mtls_enrollment import certificate_row_for
        row = db.session.get(AuthCertificate, enrolment_id)
        certificate = certificate_row_for(row)
        return certificate.id if certificate else None


class TestTheEnrolmentIsRemovedEitherWay:
    def test_a_valid_certificate_can_still_be_removed(
            self, app, an_operator, an_enrolment):
        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code in (200, 204), answer.data[:300]
        with app.app_context():
            from models.auth_certificate import AuthCertificate
            assert db.session.get(AuthCertificate, an_enrolment) is None


class TestTheCertificateGoesWithIt:
    def test_both_rows_are_deleted(self, app, an_operator, an_enrolment):
        certificate_id = _certificate_id_of(app, an_enrolment)
        assert certificate_id is not None

        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code in (200, 204), answer.data[:300]

        with app.app_context():
            from models import Certificate
            from models.auth_certificate import AuthCertificate
            assert db.session.get(AuthCertificate, an_enrolment) is None
            # The bare session.delete removed this row too; what it did not
            # do is everything CertificateService does around it.
            assert db.session.get(Certificate, certificate_id) is None

    def test_the_files_on_disk_go_with_it(self, app, an_operator, an_enrolment):
        certificate_id = _certificate_id_of(app, an_enrolment)

        with app.app_context():
            from models import Certificate
            from utils.file_naming import cert_cert_path, cert_key_path
            certificate = db.session.get(Certificate, certificate_id)
            paths = [cert_cert_path(certificate), cert_key_path(certificate)]
            written = [path for path in paths if path.exists()]

        an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert written, 'the fixture wrote no file, nothing to prove'
        assert [path for path in written if path.exists()] == []


class TestTheCertificateIsRevokedOnTheWayOut:
    def test_the_serial_reaches_the_revocation_records(self, app, an_operator,
                                                       an_enrolment):
        """Deleting used to leave it valid for anything else trusting the CA."""
        from models import Certificate, db
        from models.revoked_serial import RevokedSerial

        certificate_id = _certificate_id_of(app, an_enrolment)
        with app.app_context():
            certificate = db.session.get(Certificate, certificate_id)
            serial = certificate.serial_number
            assert certificate.revoked is not True

        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code in (200, 204), answer.data[:300]

        with app.app_context():
            record = RevokedSerial.query.filter_by(serial_number=serial).first()
            assert record is not None, 'the CRL has nothing to publish'
            assert record.revoke_reason == 'cessationOfOperation'

    def test_an_already_revoked_certificate_is_not_revoked_twice(
            self, app, an_operator, an_enrolment):
        from models import Certificate, db
        from services.cert_service import CertificateService

        certificate_id = _certificate_id_of(app, an_enrolment)
        with app.app_context():
            CertificateService.revoke_certificate(
                cert_id=certificate_id, reason='keyCompromise', username='probe')
            db.session.commit()

        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code in (200, 204), answer.data[:300]

        with app.app_context():
            from models.revoked_serial import RevokedSerial
            # The first reason is the true one and must not be overwritten.
            reasons = [r.revoke_reason for r in RevokedSerial.query.all()]
            assert 'keyCompromise' in reasons

    def test_a_certificate_that_cannot_be_revoked_is_not_deleted(
            self, app, an_operator, an_enrolment, monkeypatch):
        """An authority that cannot sign must not make it vanish in silence."""
        from models.auth_certificate import AuthCertificate
        from services.cert_service import CertificateService

        def _refuse(**_kwargs):
            raise ValueError('CA is offline and cannot sign')

        monkeypatch.setattr(CertificateService, 'revoke_certificate', _refuse)

        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code == 409, answer.data[:300]
        assert b'not deleted' in answer.data
        with app.app_context():
            assert db.session.get(AuthCertificate, an_enrolment) is not None


class TestARevocationFailingAfterItsCommitOnASingleRemoval:
    def test_the_enrolment_is_removed_and_the_ca_told(
            self, app, an_operator, an_enrolment, monkeypatch):
        from models.auth_certificate import AuthCertificate
        from services.acme import upstream_revocation
        from services.ocsp_service import OCSPService

        certificate_id = _certificate_id_of(app, an_enrolment)
        real = OCSPService.responder_cas_for_certificate
        calls = []

        def _broken_once(cert_id):
            if not calls:
                calls.append(cert_id)
                raise RuntimeError('responder lookup failed')
            return real(cert_id)
        monkeypatch.setattr(OCSPService, 'responder_cas_for_certificate',
                            staticmethod(_broken_once))
        told = []
        real_told = upstream_revocation.propagate_acme_revocation

        def spy(certificate, reason):
            told.append(certificate.id)
            return real_told(certificate, reason)
        monkeypatch.setattr(upstream_revocation, 'propagate_acme_revocation', spy)

        answer = an_operator.delete(f'/api/v2/user-certificates/{an_enrolment}')
        assert answer.status_code in (200, 204), answer.data[:300]
        assert b'not deleted' not in answer.data
        assert told == [certificate_id]
        with app.app_context():
            assert db.session.get(AuthCertificate, an_enrolment) is None
