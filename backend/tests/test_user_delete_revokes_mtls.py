"""Deleting a user withdraws the certificates they enrolled for mTLS.

The user routes dropped the enrolment rows with a bare query delete, so the
X.509 certificate stayed "good" on the CRL and at the responder for every
other service trusting the same authority. They now go through the same
withdrawal as removing one enrolment: revoked (cessationOfOperation), then
deleted; a certificate that cannot be revoked never blocks the deletion and is named.
"""
import base64
import json

import pytest
from cryptography import x509

from models import db, User, Certificate, CA, AuditLog
from models.auth_certificate import AuthCertificate
from models.revoked_serial import RevokedSerial
from tests.conftest import cert_factory
from tests.test_user_certificate_key_export_guard import _enrolment_for


@pytest.fixture(scope='module')
def create_cert(app, auth_client, create_ca):
    """Certificates under a CA of this module, deleted with it at the end:
    the session's default CA is shared with other files and never removed."""
    from services.ca_service import CAService
    from services.cert_service import CertificateService
    ca = create_ca(cn='mTLS user-delete CA')
    made = []
    issue = cert_factory(auth_client, create_ca)

    def _create(cn=None, **kwargs):
        cert = issue(cn=cn, ca_id=ca['id'], **kwargs)
        made.append(cert['id'])
        return cert
    yield _create
    with app.app_context():
        # Certificates first: on PostgreSQL their foreign key holds the CA
        for cid in made:
            if db.session.get(Certificate, cid) is not None:
                assert CertificateService.delete_certificate(cid, username='admin')
        assert CAService.delete_ca(ca['id'], username='admin')


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
        assert crl.get_revoked_certificate_by_serial_number(probe['serial']) is not None, (
            'the regenerated CRL does not list the serial')
        _, status, _, _ = OCSPService._status_for_serial(ca, probe['serial'])
        assert status == 'revoked'


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


def _refuse_revocation(monkeypatch):
    from services.cert_service import CertificateService

    def _offline(**_kwargs):
        raise ValueError('CA is offline and cannot sign')
    monkeypatch.setattr(CertificateService, 'revoke_certificate', _offline)


def _last_audit(app, action):
    with app.app_context():
        row = AuditLog.query.filter_by(action=action).order_by(AuditLog.id.desc()).first()
        return row.details if row else ''


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
        body = json.loads(answer.data)
        data = body['data']
        assert sorted(data['success']) == sorted([probe['user_id'], plain['id']])
        assert data['failed'] == []
        assert [(w['user_id'], [c['id'] for c in w['certificates']]) for w in data['unrevoked']] == [
            (probe['user_id'], [probe['certificate_id']])]
        assert f"#{probe['certificate_id']}" in body['message']
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
            assert db.session.get(User, plain['id']) is None
            assert not db.session.get(Certificate, probe['certificate_id']).revoked
        assert f"#{probe['certificate_id']}" in _last_audit(app, 'users_bulk_deleted')


class TestARevocationFailingAfterItsCommitIsStillARevocation:
    @staticmethod
    def _fail_after_the_commit(monkeypatch):
        from services.ocsp_service import OCSPService

        real = OCSPService.responder_cas_for_certificate
        calls = []

        def _broken_once(cert_id):
            # The revocation's own lookup; the deletion that follows reads it normally
            if not calls:
                calls.append(cert_id)
                raise RuntimeError('responder lookup failed')
            return real(cert_id)
        monkeypatch.setattr(OCSPService, 'responder_cas_for_certificate', staticmethod(_broken_once))

    @staticmethod
    def _spy_on_the_acme_propagation(monkeypatch):
        from services.acme import upstream_revocation
        told = []
        real = upstream_revocation.propagate_acme_revocation

        def spy(certificate, reason):
            told.append(certificate.id)
            return real(certificate, reason)
        monkeypatch.setattr(upstream_revocation, 'propagate_acme_revocation', spy)
        return told

    def test_unit_delete_does_not_call_it_valid(self, app, auth_client, probe, monkeypatch):
        self._fail_after_the_commit(monkeypatch)
        told = self._spy_on_the_acme_propagation(monkeypatch)
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        body = json.loads(answer.data)
        assert not (body.get('data') or {}).get('unrevoked_certificates')
        assert 'could not be revoked' not in body['message']
        assert told == [probe['certificate_id']]
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is None
            assert db.session.get(Certificate, probe['certificate_id']) is None
        assert 'could not be revoked' not in _last_audit(app, 'user_delete')

    def test_bulk_delete_does_not_call_it_valid(self, app, auth_client, probe, monkeypatch):
        self._fail_after_the_commit(monkeypatch)
        told = self._spy_on_the_acme_propagation(monkeypatch)
        answer = auth_client.post('/api/v2/users/bulk/delete',
                                  data=json.dumps({'ids': [probe['user_id']]}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        data = json.loads(answer.data)['data']
        assert data['success'] == [probe['user_id']] and not data.get('unrevoked')
        assert told == [probe['certificate_id']]
        with app.app_context():
            assert db.session.get(Certificate, probe['certificate_id']) is None


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
            # Its enrolment stays with it: the certificate it names is still valid
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is not None


class TestAUserWithoutEnrolment:
    def test_is_deleted_as_before_without_revoking_anything(
            self, app, auth_client, create_user, monkeypatch):
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


class TestAllOrNothingAcrossEnrolments:
    """Every enrolment is checked before any is revoked: a refusal on the
    second must not leave the first revoked under a user that stays."""

    @pytest.fixture
    def two(self, app, create_user, create_cert):
        first = _enrolled_user(app, create_user, create_cert, 'mtls_del_two')
        enrolment_id, _ = _enrolment_for(app, create_cert, 'mtls_del_two', 'mtls-del-two-b')
        with app.app_context():
            from services.mtls_enrollment import certificate_row_for
            second_id = certificate_row_for(db.session.get(AuthCertificate, enrolment_id)).id
        second = dict(first, enrolment_id=enrolment_id, certificate_id=second_id)
        yield first, second
        with app.app_context():
            row = db.session.get(AuthCertificate, second['enrolment_id'])
            if row is not None:
                db.session.delete(row)
                db.session.commit()
        _cleanup(app, first)
        _cleanup(app, second)

    @staticmethod
    def _revoked(app, probe):
        with app.app_context():
            return bool(db.session.get(Certificate, probe['certificate_id']).revoked)

    def test_a_policy_on_the_second_revokes_nothing(self, app, auth_client, two, monkeypatch):
        from types import SimpleNamespace
        import services.approval_gate as gate
        import services.mtls_enrollment as enrollment
        first, second = two
        monkeypatch.setattr(enrollment, '_revocation_held', lambda actor: True)
        monkeypatch.setattr(gate, 'revocation_policy_for', lambda cert: (
            SimpleNamespace(name='dual control') if cert.id == second['certificate_id'] else None))
        answer = auth_client.delete(f"/api/v2/users/{first['user_id']}")
        assert answer.status_code == 409, answer.data[:300]
        assert b'dual control' in answer.data
        assert not self._revoked(app, first), 'the first certificate was revoked anyway'
        assert not self._revoked(app, second)
        with app.app_context():
            assert db.session.get(User, first['user_id']) is not None

    def test_a_revocation_failing_after_another_names_only_the_unrevoked_one(
            self, app, auth_client, two, monkeypatch):
        from services.cert_service import CertificateService
        first, second = two
        original = CertificateService.revoke_certificate

        def _second_fails(**kwargs):
            if kwargs['cert_id'] == second['certificate_id']:
                raise RuntimeError('unable to persist revocation record')
            return original(**kwargs)
        monkeypatch.setattr(CertificateService, 'revoke_certificate', _second_fails)
        answer = auth_client.delete(f"/api/v2/users/{first['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        body = json.loads(answer.data)
        assert [c['id'] for c in body['data']['unrevoked_certificates']] == [second['certificate_id']]
        assert f"#{second['certificate_id']}" in body['message']
        assert not self._revoked(app, second)
        with app.app_context():
            assert db.session.get(User, first['user_id']) is None
            # The revoked one is withdrawn as usual, the other stays listed
            assert db.session.get(Certificate, first['certificate_id']) is None
        _assert_published_as_revoked(app, first)


class TestAFailureAfterTheRevocations:
    """Revoked certificates stay revoked when the deletion fails: the answer names them."""

    @staticmethod
    def _purge_fails(monkeypatch):
        import api.v2.users.crud as crud

        def _broken(_user_id):
            raise RuntimeError('database is locked')
        monkeypatch.setattr(crud, '_purge_user_dependencies', _broken)

    def test_unit_delete_names_the_revoked_certificate(self, app, auth_client, probe, monkeypatch):
        self._purge_fails(monkeypatch)
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 500, answer.data[:300]
        message = json.loads(answer.data)['message']
        assert f"#{probe['certificate_id']}" in message, message
        with app.app_context():
            assert db.session.get(User, probe['user_id']) is not None
            assert db.session.get(AuthCertificate, probe['enrolment_id']) is None
        _assert_published_as_revoked(app, probe)

    def test_bulk_names_the_revoked_certificate(self, app, auth_client, probe, monkeypatch):
        self._purge_fails(monkeypatch)
        answer = auth_client.post('/api/v2/users/bulk/delete',
                                  data=json.dumps({'ids': [probe['user_id']]}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        failed = json.loads(answer.data)['data']['failed']
        assert [f['id'] for f in failed] == [probe['user_id']]
        assert f"#{probe['certificate_id']}" in failed[0]['error'], failed

    def test_bulk_commit_failure_names_the_revoked_certificate(
            self, app, auth_client, probe, monkeypatch):
        import api.v2.users.crud as crud

        def _refused(_logger, _context):
            db.session.rollback()
            return False, None
        monkeypatch.setattr(crud, 'safe_commit', _refused)
        answer = auth_client.post('/api/v2/users/bulk/delete',
                                  data=json.dumps({'ids': [probe['user_id']]}),
                                  content_type='application/json')
        failed = json.loads(answer.data)['data']['failed']
        assert f"#{probe['certificate_id']}" in failed[0]['error'], failed


class TestTwoEnrolmentsOfOneCertificate:
    def test_revoke_it_once(self, app, auth_client, probe, monkeypatch):
        from services.cert_service import CertificateService
        with app.app_context():
            first = db.session.get(AuthCertificate, probe['enrolment_id'])
            certificate = db.session.get(Certificate, probe['certificate_id'])
            # Another spelling of the issuer: the unique index lets it in, the PEM binds it
            twin = AuthCertificate(user_id=probe['user_id'], cert_serial=first.cert_serial,
                                   cert_subject=first.cert_subject, cert_issuer='CN=twin spelling',
                                   cert_pem=base64.b64decode(certificate.crt), cert_fingerprint='',
                                   name='twin', enabled=True)
            db.session.add(twin)
            db.session.commit()
            twin_id = twin.id
        calls = []
        original = CertificateService.revoke_certificate

        def _counted(**kwargs):
            calls.append(kwargs['cert_id'])
            return original(**kwargs)
        monkeypatch.setattr(CertificateService, 'revoke_certificate', _counted)
        try:
            answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
            assert answer.status_code == 200, answer.data[:300]
            assert calls == [probe['certificate_id']]
            assert b'could not be deleted' not in answer.data
        finally:
            with app.app_context():
                row = db.session.get(AuthCertificate, twin_id)
                if row is not None:
                    db.session.delete(row)
                    db.session.commit()


class TestACertificateLeftBehind:
    def test_is_named_by_number(self, app, auth_client, probe, monkeypatch):
        from services.cert_service import CertificateService
        monkeypatch.setattr(CertificateService, 'delete_certificate', lambda *_a, **_k: False)
        answer = auth_client.delete(f"/api/v2/users/{probe['user_id']}")
        assert answer.status_code == 200, answer.data[:300]
        message = json.loads(answer.data)['message']
        assert f"certificate(s) #{probe['certificate_id']} could not" in message, message
        assert '[' not in message

    def test_is_named_by_number_in_the_bulk_log(self, app, auth_client, probe, monkeypatch, caplog):
        from services.cert_service import CertificateService
        monkeypatch.setattr(CertificateService, 'delete_certificate', lambda *_a, **_k: False)
        answer = auth_client.post('/api/v2/users/bulk/delete',
                                  data=json.dumps({'ids': [probe['user_id']]}),
                                  content_type='application/json')
        assert answer.status_code == 200, answer.data[:300]
        logged = [r.getMessage() for r in caplog.records if 'not deleted' in r.getMessage()]
        assert logged and f"#{probe['certificate_id']}" in logged[0], logged
        assert '[' not in logged[0]
