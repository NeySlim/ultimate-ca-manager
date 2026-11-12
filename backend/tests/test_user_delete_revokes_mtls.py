"""Deleting a user withdraws the certificates they enrolled for mTLS.

The user routes dropped the enrolment rows with a bare query delete, so the
certificate stayed "good" on the CRL and at the responder for every other
service trusting the same authority. Each enrolment now goes through the same
withdrawal as removing it (revoked as cessationOfOperation, then deleted); a
certificate that cannot be revoked never blocks the deletion and is named.
"""
import base64
import json

import pytest
from cryptography import x509

from models import db, User, Certificate, CA, AuditLog
from models.auth_certificate import AuthCertificate
from models.revoked_serial import RevokedSerial
from tests.test_user_certificate_key_export_guard import _enrolment_for

# The CAs and certificates made here (the default test CA included) go with the module.
pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def _enrolled_user(app, create_user, create_cert, username):
    create_user(username=username, role='viewer')
    enrolment_id, user_id = _enrolment_for(app, create_cert, username, username.replace('_', '-'))
    with app.app_context():
        from services.mtls_enrollment import certificate_row_for
        certificate = certificate_row_for(db.session.get(AuthCertificate, enrolment_id))
        ca = CA.query.filter_by(refid=certificate.caref).first()
        issued = x509.load_pem_x509_certificate(base64.b64decode(certificate.crt))
        return {'user_id': user_id, 'enrolment_id': enrolment_id,
                'serial': issued.serial_number, 'serial_text': certificate.serial_number,
                'certificate_id': certificate.id, 'ca_id': ca.id}


def _cleanup(app, probe):
    with app.app_context():
        row = db.session.get(AuthCertificate, probe['enrolment_id'])
        if row is not None:
            db.session.delete(row)
        user = db.session.get(User, probe['user_id'])
        if user is not None:
            db.session.delete(user)
        certificate = db.session.get(Certificate, probe['certificate_id'])
        if certificate is not None:
            db.session.delete(certificate)
        db.session.commit()


def _assert_published_as_revoked(app, probe):
    from services.crl_service import CRLService
    from services.ocsp_service import OCSPService
    with app.app_context():
        record = RevokedSerial.query.filter_by(
            caref=db.session.get(CA, probe['ca_id']).refid,
            serial_number=probe['serial_text']).first()
        assert record is not None, 'the CRL has nothing to publish'
        assert record.revoke_reason == 'cessationOfOperation'
        ca = db.session.get(CA, probe['ca_id'])
        crl = x509.load_pem_x509_crl(CRLService.generate_crl(ca.id).crl_pem.encode())
        assert crl.get_revoked_certificate_by_serial_number(probe['serial']) is not None
        _, status, _, _ = OCSPService._status_for_serial(ca, probe['serial'])
        assert status == 'revoked'


def _refuse_revocation(monkeypatch):
    from services.cert_service import CertificateService

    def _offline(**_kwargs):
        raise ValueError('CA is offline and cannot sign')
    monkeypatch.setattr(CertificateService, 'revoke_certificate', _offline)


def _last_audit(app, action):
    with app.app_context():
        row = AuditLog.query.filter_by(action=action).order_by(AuditLog.id.desc()).first()
        return row.details if row else ''


@pytest.fixture
def probe(app, create_user, create_cert, request):
    data = _enrolled_user(app, create_user, create_cert, f'mtls_del_{request.node.name[-20:]}')
    yield data
    _cleanup(app, data)


class TestDeletingAUserRevokesTheirMtlsCertificate:
    def test_unit_delete(self, app, auth_client, probe):
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
            assert db.session.get(Certificate, probe['certificate_id']) is None
        _assert_published_as_revoked(app, probe)

    def test_bulk_delete(self, app, auth_client, probe):
        answer = auth_client.post('/api/v2/users/bulk/delete',
                                  data=json.dumps({'ids': [probe['user_id']]}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        assert json.loads(answer.data)['data']['success'] == [probe['user_id']]
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
        _assert_published_as_revoked(app, probe)

    def test_a_certificate_enrolled_twice_is_revoked_once(self, app, auth_client, probe):
        with app.app_context():
            first = db.session.get(AuthCertificate, probe['enrolment_id'])
            # The same certificate under its hexadecimal serial, as /enroll stores it
            twin = AuthCertificate(user_id=first.user_id, cert_serial=hex(probe['serial']),
                                   cert_subject=first.cert_subject, cert_issuer=first.cert_issuer,
                                   cert_fingerprint='', name='twin', enabled=True)
            db.session.add(twin)
            db.session.commit()
            twin_id = twin.id
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        assert 'could not be revoked' not in json.loads(answer.data)['message']
        with app.app_context():
            assert db.session.get(AuthCertificate, twin_id) is None
        _assert_published_as_revoked(app, probe)


class TestACertificateThatCannotBeRevokedNeverBlocksTheDeletion:
    def test_unit_delete_names_it(self, app, auth_client, probe, monkeypatch):
        _refuse_revocation(monkeypatch)
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        body = json.loads(answer.data)
        assert 'could not be revoked' in body['message']
        assert f"#{probe['certificate_id']}" in body['message']
        assert [c['id'] for c in body['data']['unrevoked_certificates']] == [probe['certificate_id']]
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
            kept = db.session.get(Certificate, probe['certificate_id'])
            assert kept is not None and not kept.revoked
        assert f"#{probe['certificate_id']}" in _last_audit(app, 'user_delete')

    def test_bulk_names_it_and_deletes_everyone(
            self, app, auth_client, create_user, probe, monkeypatch):
        plain = create_user(username='mtls_del_bulk_plain', role='viewer')
        _refuse_revocation(monkeypatch)
        answer = auth_client.post(
            '/api/v2/users/bulk/delete',
            data=json.dumps({'ids': [probe['user_id'], plain['id']]}),
            content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        data = json.loads(answer.data)['data']
        assert sorted(data['success']) == sorted([probe['user_id'], plain['id']])
        assert data['failed'] == []
        assert [(w['user_id'], [c['id'] for c in w['certificates']]) for w in data['unrevoked']] == [
            (probe['user_id'], [probe['certificate_id']])]
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
            assert db.session.get(User, plain['id']) is None
        assert f"#{probe['certificate_id']}" in _last_audit(app, 'users_bulk_deleted')

    def test_a_ca_without_its_key(self, app, auth_client, create_user, create_ca, create_cert):
        ca = create_ca(cn='Keyless mTLS delete CA')
        create_user(username='mtls_del_keyless', role='viewer')
        enrolment_id, user_id = _enrolment_for(
            app, lambda cn: create_cert(cn=cn, ca_id=ca['id']), 'mtls_del_keyless', 'keyless')
        with app.app_context():
            from services.mtls_enrollment import certificate_row_for
            certificate = certificate_row_for(db.session.get(AuthCertificate, enrolment_id))
            certificate_id, serial = certificate.id, certificate.serial_number
            keyless = db.session.get(CA, ca['id'])
            caref = keyless.refid
            keyless.prv = None
            db.session.commit()
        answer = auth_client.delete(f'/api/v2/users/{user_id}')
        assert answer.status_code == 200, answer.data[:300]
        with app.app_context():
            assert db.session.get(User, user_id) is None
            assert db.session.get(AuthCertificate, enrolment_id) is None
            # The revocation record needs no signature: the CRL publishes it once the key is back
            assert db.session.get(Certificate, certificate_id) is None
            record = RevokedSerial.query.filter_by(caref=caref, serial_number=serial).first()
            assert record is not None and record.revoke_reason == 'cessationOfOperation'


class TestAFailureLeavesAConsistentState:
    def test_the_user_stays_when_its_own_deletion_fails(self, app, auth_client, probe, monkeypatch):
        from api.v2.users import crud

        def _broken(_user_id):
            raise RuntimeError('database went away')
        monkeypatch.setattr(crud, '_purge_user_dependencies', _broken)
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 500, answer.data[:300]
        with app.app_context():
            # Access withdrawn and published; the account is still there to delete again
            assert db.session.get(User, probe['user_id']) is not None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
        _assert_published_as_revoked(app, probe)


    def test_bulk_does_not_name_a_user_it_failed_to_delete(
            self, app, auth_client, create_user, probe, monkeypatch):
        from api.v2.users import crud
        plain = create_user(username='mtls_del_bulk_survivor', role='viewer')
        real_purge = crud._purge_user_dependencies

        def _broken_for_probe(user_id):
            if user_id == probe['user_id']:
                raise RuntimeError('database went away')
            return real_purge(user_id)
        monkeypatch.setattr(crud, '_purge_user_dependencies', _broken_for_probe)
        _refuse_revocation(monkeypatch)
        answer = auth_client.post(
            '/api/v2/users/bulk/delete',
            data=json.dumps({'ids': [probe['user_id'], plain['id']]}),
            content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        body = json.loads(answer.data)
        assert body['data']['success'] == [plain['id']]
        assert [f['id'] for f in body['data']['failed']] == [probe['user_id']]
        assert body['data']['unrevoked'] == []
        assert f"#{probe['certificate_id']}" not in body['message']
        assert f"#{probe['certificate_id']}" not in _last_audit(app, 'users_bulk_deleted')
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is not None


class TestNothingToRevoke:
    def test_a_user_without_enrolment(self, app, auth_client, create_user, monkeypatch):
        from services.cert_service import CertificateService
        calls = []
        monkeypatch.setattr(CertificateService, 'revoke_certificate',
                            lambda **kw: calls.append(kw))
        user = create_user(username='mtls_del_no_enrolment', role='viewer')
        answer = auth_client.delete(f"/api/v2/users/{user['id']}")
        assert answer.status_code == 200, answer.data[:300]
        assert calls == []
        with app.app_context():
            assert db.session.get(User, user['id']) is None

    def test_a_presented_enrolment_without_certificate_row(
            self, app, auth_client, create_user, monkeypatch):
        from services.cert_service import CertificateService
        calls = []
        monkeypatch.setattr(CertificateService, 'revoke_certificate',
                            lambda **kw: calls.append(kw))
        user = create_user(username='mtls_del_presented', role='viewer')
        with app.app_context():
            row = AuthCertificate(user_id=user['id'], cert_serial='123456789987654321',
                                  cert_subject='CN=presented.example', cert_issuer='CN=Elsewhere',
                                  cert_fingerprint='', name='presented', enabled=True)
            db.session.add(row)
            db.session.commit()
            enrolment_id = row.id
        answer = auth_client.delete(f"/api/v2/users/{user['id']}")
        assert answer.status_code == 200, answer.data[:300]
        assert 'could not be revoked' not in json.loads(answer.data)['message']
        assert calls == []
        with app.app_context():
            assert db.session.get(User, user['id']) is None
            assert db.session.get(AuthCertificate, enrolment_id) is None


class TestACertificateItsCaRecordedAsRevoked:
    """Revoked for good by its CA's record, the row unmarked: already revoked, so the
    withdrawal goes on and never names it as left valid."""

    @staticmethod
    def _recorded(app, probe):
        from datetime import datetime
        with app.app_context():
            refid = db.session.get(CA, probe['ca_id']).refid
            db.session.add(RevokedSerial(caref=refid, serial_number=str(probe['serial']),
                                         revoked_at=datetime(2026, 1, 2), revoke_reason='keyCompromise',
                                         valid_to=datetime(2099, 1, 1)))
            db.session.commit()
            return refid

    @staticmethod
    def _drop_record(app, refid, probe):
        with app.app_context():
            RevokedSerial.query.filter_by(caref=refid, serial_number=str(probe['serial'])).delete()
            db.session.commit()

    def test_removing_the_enrolment(self, app, auth_client, probe):
        refid = self._recorded(app, probe)
        try:
            answer = auth_client.delete(
                f"/api/v2/users/{probe['user_id']}/mtls/certificates/{probe['enrolment_id']}")
            assert answer.status_code in (200, 204), answer.data[:300]
            with app.app_context():
                assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
                record = RevokedSerial.query.filter_by(caref=refid, serial_number=str(probe['serial'])).one()
                assert record.revoke_reason == 'keyCompromise'
        finally:
            self._drop_record(app, refid, probe)

    def test_deleting_the_user(self, app, auth_client, probe):
        refid = self._recorded(app, probe)
        try:
            answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
            assert answer.status_code == 200, answer.data[:300]
            body = json.loads(answer.data)
            assert 'could not be revoked' not in (body.get('message') or '')
            assert not (body.get('data') or {}).get('unrevoked_certificates')
            with app.app_context():
                assert db.session.get(User, probe['user_id']) is None
                assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
                assert db.session.get(Certificate, probe['certificate_id']) is None
        finally:
            self._drop_record(app, refid, probe)
