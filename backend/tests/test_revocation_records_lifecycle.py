"""Revocation, deletion and hold release keep the revocation records right.

A revoked serial lives in ``revoked_serials`` from the revocation on, outlives
the certificate row, and leaves with a lifted hold. Each scenario drives the
service or the route and reads the rows back.
"""
import json
import os
import secrets
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest

from models import db, Certificate, RevokedSerial, AuditLog
from models.policy import ApprovalRequest
from utils.datetime_utils import utc_now

DELETE_VALID_MESSAGE = ('Cannot delete a valid certificate: revoke it first so the '
                        'CRL and OCSP responder reflect the change.')


def _post(client, url, payload=None):
    return client.post(url, data=json.dumps(payload or {}), content_type='application/json')


def _row(app, cert_id):
    with app.app_context():
        db.session.expire_all()
        cert = db.session.get(Certificate, cert_id)
        if cert is None:
            return None
        return {'revoked': cert.revoked, 'revoked_at': cert.revoked_at,
                'reason': cert.revoke_reason, 'invalidity_at': cert.invalidity_at,
                'serial': cert.serial_number, 'caref': cert.caref, 'valid_to': cert.valid_to}


def _records(app, serial):
    with app.app_context():
        db.session.expire_all()
        return [r.to_dict() for r in RevokedSerial.query.filter_by(serial_number=serial).all()]


def _request(app, request_type, data, certificate_id=None, status='pending'):
    with app.app_context():
        approval = ApprovalRequest(
            request_type=request_type, request_data=json.dumps(data), status=status,
            certificate_id=certificate_id, expires_at=utc_now() + timedelta(days=1))
        db.session.add(approval)
        db.session.commit()
        return approval.id


def _approval(app, approval_id):
    with app.app_context():
        db.session.expire_all()
        approval = db.session.get(ApprovalRequest, approval_id)
        if approval is None:
            return None
        votes = approval.get_approvals()
        return {'status': approval.status, 'certificate_id': approval.certificate_id,
                'comment': votes[-1]['comment'] if votes else None}


def _fail_commit_when(monkeypatch, cert_id, predicate):
    """Make ``db.session.commit`` raise while ``predicate`` holds for the
    session's copy of certificate ``cert_id`` (flushed or not)."""
    original = db.session.commit

    def commit():
        for obj in list(db.session.identity_map.values()):
            if isinstance(obj, Certificate) and obj.id == cert_id and predicate(obj):
                raise RuntimeError('simulated commit failure')
        return original()

    monkeypatch.setattr(db.session, 'commit', commit)


def _revoke_service(app, cert_id, reason='keyCompromise', **kwargs):
    from services.cert_service import CertificateService
    with app.app_context():
        CertificateService.revoke_certificate(cert_id=cert_id, reason=reason,
                                              username='admin', **kwargs)


class TestRevocationRecord:

    def test_a_revocation_writes_its_record(self, app, auth_client, create_ca, create_cert):
        ca = create_ca(cn='Record Write CA')
        cert = create_cert(cn='record-write.example.test', ca_id=ca['id'])
        r = _post(auth_client, f"/api/v2/certificates/{cert['id']}/revoke", {'reason': 'keyCompromise'})
        assert r.status_code == 200, r.data
        state = _row(app, cert['id'])
        records = _records(app, state['serial'])
        assert len(records) == 1
        record = records[0]
        assert record['caref'] == state['caref'] and record['revoke_reason'] == 'keyCompromise'
        assert record['certificate_id'] == cert['id']
        assert record['valid_to'] is not None
        assert record['valid_to'][:19] == state['valid_to'].isoformat()[:19]

    def test_hold_release_then_revocation_updates_the_single_record(
            self, app, auth_client, create_ca, create_cert):
        ca = create_ca(cn='Record Update CA')
        cert = create_cert(cn='record-update.example.test', ca_id=ca['id'])
        url = f"/api/v2/certificates/{cert['id']}"
        assert _post(auth_client, f'{url}/revoke', {'reason': 'certificateHold'}).status_code == 200
        assert _post(auth_client, f'{url}/unhold').status_code == 200
        assert _post(auth_client, f'{url}/revoke', {'reason': 'keyCompromise'}).status_code == 200
        records = _records(app, _row(app, cert['id'])['serial'])
        assert len(records) == 1 and records[0]['revoke_reason'] == 'keyCompromise'

    def test_a_record_left_by_an_earlier_revocation_is_updated_not_doubled(
            self, app, create_ca, create_cert):
        ca = create_ca(cn='Record Leftover CA')
        cert = create_cert(cn='record-leftover.example.test', ca_id=ca['id'])
        state = _row(app, cert['id'])
        with app.app_context():
            db.session.add(RevokedSerial(caref=state['caref'], serial_number=state['serial'],
                                         revoked_at=utc_now() - timedelta(days=3),
                                         revoke_reason='certificateHold',
                                         valid_to=utc_now() + timedelta(days=1)))
            db.session.commit()
        _revoke_service(app, cert['id'], reason='superseded')
        records = _records(app, state['serial'])
        assert len(records) == 1
        assert records[0]['revoke_reason'] == 'superseded' and records[0]['certificate_id'] == cert['id']

    def test_already_revoked_is_refused(self, app, auth_client, create_ca, create_cert):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Already Revoked CA')
        cert = create_cert(cn='already-revoked.example.test', ca_id=ca['id'])
        _revoke_service(app, cert['id'])
        with app.app_context(), pytest.raises(ValueError, match='Certificate already revoked'):
            CertificateService.revoke_certificate(cert_id=cert['id'])
        r = _post(auth_client, f"/api/v2/certificates/{cert['id']}/revoke", {'reason': 'superseded'})
        assert r.status_code == 400 and b'Certificate already revoked' in r.data

    def test_a_missing_certificate_is_refused(self, app):
        from services.cert_service import CertificateService
        with app.app_context(), pytest.raises(ValueError, match='Certificate not found'):
            CertificateService.revoke_certificate(cert_id=987654321)

    def test_an_invalidity_date_is_kept_unless_one_is_given(self, app, create_ca, create_cert):
        ca = create_ca(cn='Invalidity Keep CA')
        cert = create_cert(cn='invalidity-keep.example.test', ca_id=ca['id'])
        earlier = (utc_now() - timedelta(days=5)).replace(microsecond=0)
        with app.app_context():
            db.session.get(Certificate, cert['id']).invalidity_at = earlier
            db.session.commit()
        _revoke_service(app, cert['id'])
        state = _row(app, cert['id'])
        assert state['revoked'] and state['invalidity_at'] == earlier
        assert abs((state['revoked_at'] - utc_now()).total_seconds()) < 60

    def test_a_certificate_without_caref_gets_no_record(self, app, create_ca, create_cert):
        ca = create_ca(cn='Microsoft Like CA')
        cert = create_cert(cn='msca-like.example.test', ca_id=ca['id'])
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.caref = None
            row.source = 'msca'
            db.session.commit()
        _revoke_service(app, cert['id'])
        state = _row(app, cert['id'])
        assert state['revoked'] is True
        assert _records(app, state['serial']) == []

    def test_a_failed_commit_restores_the_previous_state(
            self, app, create_ca, create_cert, monkeypatch):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Revoke Commit Fails CA')
        cert = create_cert(cn='revoke-commit-fails.example.test', ca_id=ca['id'])
        earlier = (utc_now() - timedelta(days=9)).replace(microsecond=0)
        with app.app_context():
            db.session.get(Certificate, cert['id']).invalidity_at = earlier
            db.session.commit()
        before = _row(app, cert['id'])
        with app.app_context():
            _fail_commit_when(monkeypatch, cert['id'], lambda c: c.revoked is True)
            with pytest.raises(RuntimeError) as raised:
                CertificateService.revoke_certificate(
                    cert_id=cert['id'], reason='keyCompromise',
                    invalidity_at=utc_now() - timedelta(days=1))
            monkeypatch.undo()
        assert str(raised.value).startswith(
            f"Revocation failed for cert {cert['id']}: unable to persist revocation record: ")
        assert _row(app, cert['id']) == before
        assert _records(app, before['serial']) == []


class TestRevocationClosesRequests:

    def _two_requests(self, app, cert_id):
        renewal = _request(app, 'renewal', {'certificate_id': cert_id})
        revocation = _request(app, 'revocation', {'certificate_id': cert_id, 'reason': 'superseded'})
        return renewal, revocation

    def test_a_revocation_rejects_the_renewal_and_approves_the_revocation(
            self, app, create_ca, create_cert):
        ca = create_ca(cn='Close Requests CA')
        cert = create_cert(cn='close-requests.example.test', ca_id=ca['id'])
        renewal, revocation = self._two_requests(app, cert['id'])
        _revoke_service(app, cert['id'], reason='superseded')
        assert _approval(app, renewal) == {'status': 'rejected', 'certificate_id': None,
                                           'comment': 'Certificate revoked'}
        assert _approval(app, revocation) == {'status': 'approved', 'certificate_id': cert['id'],
                                              'comment': 'Revoked directly'}

    def test_a_hold_leaves_them_pending(self, app, create_ca, create_cert):
        ca = create_ca(cn='Hold Keeps Requests CA')
        cert = create_cert(cn='hold-keeps-requests.example.test', ca_id=ca['id'])
        renewal, revocation = self._two_requests(app, cert['id'])
        _revoke_service(app, cert['id'], reason='certificateHold')
        assert _approval(app, renewal)['status'] == 'pending'
        assert _approval(app, revocation)['status'] == 'pending'
        for approval_id in (renewal, revocation):
            with app.app_context():
                db.session.delete(db.session.get(ApprovalRequest, approval_id))
                db.session.commit()


class TestRevocationEvents:

    def test_the_webhook_gets_the_snapshot_and_the_audit_is_written(
            self, app, create_ca, create_cert, monkeypatch):
        emitted = []
        monkeypatch.setattr('services.webhook_service.emit_cert_revoked',
                            lambda cert, reason=None, ca_refid=None, actor=None:
                            emitted.append((cert['id'], cert['revoked'], reason, ca_refid, actor)))
        ca = create_ca(cn='Revoke Events CA')
        cert = create_cert(cn='revoke-events.example.test', ca_id=ca['id'])
        _revoke_service(app, cert['id'], reason='superseded')
        caref = _row(app, cert['id'])['caref']
        assert emitted == [(cert['id'], True, 'superseded', caref, 'admin')]
        with app.app_context():
            assert AuditLog.query.filter_by(action='cert_revoked',
                                            resource_name='revoke-events.example.test').count() == 1

    def test_a_failed_crl_is_audited_and_the_revocation_stands(
            self, app, create_ca, create_cert, monkeypatch):
        from services.crl_service import CRLService
        from models import CA
        ca = create_ca(cn='Revoke CRL Fails CA')
        cert = create_cert(cn='revoke-crl-fails.example.test', ca_id=ca['id'])
        with app.app_context():
            db.session.get(CA, ca['id']).cdp_enabled = True
            db.session.commit()

        def refuse(*_a, **_k):
            raise RuntimeError('signing key unavailable')
        monkeypatch.setattr(CRLService, 'generate_crl', staticmethod(refuse))
        _revoke_service(app, cert['id'])
        assert _row(app, cert['id'])['revoked'] is True
        with app.app_context():
            entry = AuditLog.query.filter_by(action='crl_auto_generation_failed',
                                             resource_id=str(ca['id'])).first()
            assert entry is not None and entry.success is False

    def test_the_cached_answers_of_a_responder_ca_are_dropped(
            self, app, create_ca, create_cert, monkeypatch):
        from models import SystemConfig
        from services.ocsp_service import OCSPService
        ca = create_ca(cn='Responder Revoked CA')
        responder = create_cert(cn='responder-revoked.example.test', ca_id=ca['id'])
        dropped = []
        monkeypatch.setattr(OCSPService, 'invalidate_ca_cache', staticmethod(dropped.append))
        with app.app_context():
            db.session.add(SystemConfig(key=f"ocsp_responder_cert_{ca['id']}", value=str(responder['id'])))
            db.session.commit()
        try:
            _revoke_service(app, responder['id'])
            assert dropped == [ca['id']]
        finally:
            with app.app_context():
                SystemConfig.query.filter_by(key=f"ocsp_responder_cert_{ca['id']}").delete()
                db.session.commit()


class TestUnhold:

    def _held(self, app, auth_client, create_ca, create_cert, name, **ca_settings):
        from models import CA
        ca = create_ca(cn=f'{name} CA')
        if ca_settings:
            with app.app_context():
                row = db.session.get(CA, ca['id'])
                for key, value in ca_settings.items():
                    setattr(row, key, value)
                db.session.commit()
        cert = create_cert(cn=f'{name}.example.test', ca_id=ca['id'])
        r = _post(auth_client, f"/api/v2/certificates/{cert['id']}/revoke", {'reason': 'certificateHold'})
        assert r.status_code == 200, r.data
        return cert

    def test_unhold_removes_the_record(self, app, auth_client, create_ca, create_cert):
        cert = self._held(app, auth_client, create_ca, create_cert, 'unhold-record')
        serial = _row(app, cert['id'])['serial']
        assert len(_records(app, serial)) == 1
        r = _post(auth_client, f"/api/v2/certificates/{cert['id']}/unhold")
        assert r.status_code == 200, r.data
        state = _row(app, cert['id'])
        assert state['revoked'] is False and state['reason'] is None
        assert _records(app, serial) == []

    @pytest.mark.parametrize('delta', [False, True], ids=['full-crl', 'delta-crl'])
    def test_a_failed_commit_keeps_the_hold(self, app, auth_client, create_ca, create_cert,
                                            monkeypatch, delta):
        settings = {'cdp_enabled': True, 'delta_crl_enabled': True} if delta else {}
        cert = self._held(app, auth_client, create_ca, create_cert,
                          f'unhold-fails-{int(delta)}', **settings)
        before = _row(app, cert['id'])
        with app.app_context():
            _fail_commit_when(monkeypatch, cert['id'], lambda c: c.revoked is False)
            r = _post(auth_client, f"/api/v2/certificates/{cert['id']}/unhold")
            monkeypatch.undo()
        assert r.status_code == 500 and b'Failed to remove certificate hold' in r.data
        after = _row(app, cert['id'])
        assert after['revoked'] is True and after['reason'] == 'certificateHold'
        assert after['revoked_at'] == before['revoked_at']
        assert len(_records(app, before['serial'])) == 1


class TestDeletion:

    def test_a_valid_certificate_is_refused(self, app, auth_client, create_ca, create_cert):
        ca = create_ca(cn='Delete Valid CA')
        cert = create_cert(cn='delete-valid.example.test', ca_id=ca['id'])
        r = auth_client.delete(f"/api/v2/certificates/{cert['id']}")
        assert r.status_code == 409
        assert DELETE_VALID_MESSAGE in r.get_data(as_text=True)
        assert _row(app, cert['id']) is not None

    def test_a_revoked_then_deleted_certificate_keeps_its_record(
            self, app, auth_client, create_ca, create_cert):
        ca = create_ca(cn='Delete Revoked CA')
        cert = create_cert(cn='delete-revoked.example.test', ca_id=ca['id'])
        assert _post(auth_client, f"/api/v2/certificates/{cert['id']}/revoke",
                     {'reason': 'keyCompromise'}).status_code == 200
        serial = _row(app, cert['id'])['serial']
        r = auth_client.delete(f"/api/v2/certificates/{cert['id']}")
        assert r.status_code == 204, r.data
        assert _row(app, cert['id']) is None
        records = _records(app, serial)
        assert len(records) == 1 and records[0]['certificate_id'] is None
        assert records[0]['revoke_reason'] == 'keyCompromise'

    def test_pending_requests_are_rejected_and_linked_ones_removed(
            self, app, create_ca, create_cert):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Delete Requests CA')
        cert = create_cert(cn='delete-requests.example.test', ca_id=ca['id'])
        renewal = _request(app, 'renewal', {'certificate_id': cert['id']})
        revocation = _request(app, 'revocation', {'certificate_id': cert['id']})
        linked = _request(app, 'renewal', {'certificate_id': 1}, certificate_id=cert['id'],
                          status='approved')
        _revoke_service(app, cert['id'], reason='certificateHold')
        with app.app_context():
            assert CertificateService.delete_certificate(cert['id'], username='admin') is True
        assert _approval(app, renewal) == {'status': 'rejected', 'certificate_id': None,
                                           'comment': 'Certificate deleted'}
        assert _approval(app, revocation)['status'] == 'rejected'
        assert _approval(app, revocation)['comment'] == 'Certificate deleted'
        assert _approval(app, linked) is None

    def test_a_csr_with_a_pending_signing_request_is_rejected(self, app):
        from services.cert_service import CertificateService
        with app.app_context():
            csr = Certificate(refid=str(uuid.uuid4()), descr='delete-csr.example.test',
                              csr='-----BEGIN CERTIFICATE REQUEST-----\n-----END CERTIFICATE REQUEST-----')
            db.session.add(csr)
            db.session.commit()
            csr_id = csr.id
        signing = _request(app, 'csr', {'csr_id': csr_id})
        with app.app_context():
            assert CertificateService.delete_certificate(csr_id, username='admin') is True
        assert _row(app, csr_id) is None
        assert _approval(app, signing) == {'status': 'rejected', 'certificate_id': None,
                                           'comment': 'Request deleted'}

    def test_a_failed_delete_is_rolled_back_and_audited(
            self, app, create_ca, create_cert, monkeypatch):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Delete Fails CA')
        cert = create_cert(cn='delete-fails.example.test', ca_id=ca['id'])
        _revoke_service(app, cert['id'])
        renewal = _request(app, 'renewal', {'certificate_id': cert['id']})
        serial = _row(app, cert['id'])['serial']

        def refuse(_obj):
            raise RuntimeError('delete refused')
        with app.app_context():
            monkeypatch.setattr(db.session, 'delete', refuse)
            assert CertificateService.delete_certificate(cert['id'], username='admin') is False
            monkeypatch.undo()
        assert _row(app, cert['id']) is not None
        assert _approval(app, renewal)['status'] == 'pending'
        assert _records(app, serial)[0]['certificate_id'] == cert['id']
        with app.app_context():
            entry = AuditLog.query.filter_by(
                action='cert_deleted', resource_name='delete-fails.example.test',
            ).order_by(AuditLog.id.desc()).first()
            assert entry is not None and entry.success is False

    def test_success_is_audited_after_the_commit_and_emitted_from_the_snapshot(
            self, app, create_ca, create_cert, monkeypatch):
        from services.cert_service import CertificateService
        emitted = []
        monkeypatch.setattr('services.webhook_service.emit_cert_deleted',
                            lambda cert, ca_refid=None, actor=None:
                            emitted.append((cert['id'], cert['descr'], ca_refid, actor)))
        ca = create_ca(cn='Delete Events CA')
        cert = create_cert(cn='delete-events.example.test', ca_id=ca['id'])
        _revoke_service(app, cert['id'])
        caref = _row(app, cert['id'])['caref']
        with app.app_context():
            assert CertificateService.delete_certificate(cert['id'], username='robot') is True
            entry = AuditLog.query.filter_by(
                action='cert_deleted', resource_name='delete-events.example.test',
            ).order_by(AuditLog.id.desc()).first()
        assert entry is not None and entry.success is True
        assert entry.resource_name == 'delete-events.example.test' and entry.username == 'robot'
        assert emitted == [(cert['id'], 'delete-events.example.test', caref, 'robot')]

    def test_the_responder_binding_goes_with_the_certificate(
            self, app, create_ca, create_cert, monkeypatch):
        from models import SystemConfig
        from services.cert_service import CertificateService
        from services.ocsp_service import OCSPService
        ca = create_ca(cn='Delete Responder CA')
        responder = create_cert(cn='delete-responder.example.test', ca_id=ca['id'])
        _revoke_service(app, responder['id'])
        dropped = []
        monkeypatch.setattr(OCSPService, 'invalidate_ca_cache', staticmethod(dropped.append))
        key = f"ocsp_responder_cert_{ca['id']}"
        with app.app_context():
            db.session.add(SystemConfig(key=key, value=str(responder['id'])))
            db.session.commit()
            assert CertificateService.delete_certificate(responder['id']) is True
            assert SystemConfig.query.filter_by(key=key).first() is None
        assert dropped == [ca['id']]


def _seed_references(cert_id):
    """An ACME server order, an ACME client order and a deploy binding with
    its delivery history, all on ``cert_id``; returns their ids."""
    from models import DeployTarget, DeployBinding, DeployDelivery
    from models.acme_models import AcmeAccount, AcmeOrder, AcmeClientOrder
    account = AcmeAccount(account_id=f'del-{secrets.token_hex(6)}', jwk='{}',
                          jwk_thumbprint=secrets.token_hex(16), status='valid')
    db.session.add(account)
    db.session.flush()
    order = AcmeOrder(order_id=secrets.token_urlsafe(16), account_id=account.account_id,
                      identifiers='[]', status='valid', certificate_id=cert_id)
    client_order = AcmeClientOrder(domains='["d.test"]', certificate_id=cert_id,
                                   source_certificate_id=cert_id, key_source='reuse')
    target = DeployTarget(name=f'del-target-{secrets.token_hex(4)}', host='h.test',
                          username='u', private_key='k')
    db.session.add_all([order, client_order, target])
    db.session.flush()
    binding = DeployBinding(target_id=target.id, certificate_id=cert_id, cert_path='/x.pem')
    db.session.add(binding)
    db.session.flush()
    delivery = DeployDelivery(binding_id=binding.id, binding_type='certificate',
                              event_type='initial', status='delivered')
    db.session.add(delivery)
    db.session.commit()
    return {'account': account.account_id, 'order': order.id, 'client_order': client_order.id,
            'target': target.id, 'binding': binding.id, 'delivery': delivery.id}


def _assert_references_cleared(ids):
    from models import DeployTarget, DeployBinding, DeployDelivery
    from models.acme_models import AcmeAccount, AcmeOrder, AcmeClientOrder
    db.session.expire_all()
    order = db.session.get(AcmeOrder, ids['order'])
    client_order = db.session.get(AcmeClientOrder, ids['client_order'])
    assert order.certificate_id is None
    assert client_order.certificate_id is None and client_order.source_certificate_id is None
    assert db.session.get(DeployBinding, ids['binding']) is None
    assert db.session.get(DeployDelivery, ids['delivery']) is None
    db.session.delete(order)
    db.session.delete(client_order)
    db.session.delete(db.session.get(DeployTarget, ids['target']))
    db.session.flush()
    db.session.delete(AcmeAccount.query.filter_by(account_id=ids['account']).one())
    db.session.commit()


class TestReferencesAreCleared:

    def test_acme_orders_and_deploy_bindings_on_sqlite(self, app, create_ca, create_cert):
        from services.cert_service import CertificateService
        ca = create_ca(cn='Delete References CA')
        cert = create_cert(cn='delete-references.example.test', ca_id=ca['id'])
        _revoke_service(app, cert['id'])
        with app.app_context():
            ids = _seed_references(cert['id'])
            assert CertificateService.delete_certificate(cert['id']) is True
            assert db.session.get(Certificate, cert['id']) is None
            _assert_references_cleared(ids)


_PG_URL = os.environ.get('UCM_TEST_PG_URL')


@contextmanager
def _postgres_session(app, monkeypatch):
    """``db.session`` bound to a throwaway PostgreSQL schema built from the models."""
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import scoped_session, sessionmaker
    schema = f'b4_delete_{secrets.token_hex(4)}'
    admin = create_engine(_PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    separator = '&' if '?' in _PG_URL else '?'
    engine = create_engine(f'{_PG_URL}{separator}options=-csearch_path%3D{schema}')
    try:
        db.metadata.create_all(bind=engine)
        session = scoped_session(sessionmaker(bind=engine))
        with app.app_context():
            monkeypatch.setattr(db, 'session', session)
            try:
                yield session
            finally:
                session.remove()
                monkeypatch.undo()
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()


@pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')
class TestReferencesAreClearedOnPostgres:

    def test_acme_orders_and_deploy_bindings(self, app, monkeypatch):
        from models import CA
        from services.cert_service import CertificateService
        with _postgres_session(app, monkeypatch):
            caref = str(uuid.uuid4())
            db.session.add(CA(refid=caref, descr='PG CA', crt='x'))
            db.session.flush()
            cert = Certificate(refid=str(uuid.uuid4()), descr='pg-delete.example.test', caref=caref,
                               crt='x', serial_number='4242', revoked=True,
                               revoked_at=utc_now(), revoke_reason='keyCompromise')
            db.session.add(cert)
            db.session.flush()
            db.session.add(RevokedSerial(caref=caref, serial_number='4242',
                                         revoke_reason='keyCompromise',
                                         valid_to=utc_now() + timedelta(days=30),
                                         certificate_id=cert.id))
            db.session.commit()
            cert_id = cert.id
            ids = _seed_references(cert_id)
            assert CertificateService.delete_certificate(cert_id) is True
            assert db.session.get(Certificate, cert_id) is None
            record = RevokedSerial.query.filter_by(serial_number='4242').one()
            assert record.certificate_id is None
            _assert_references_cleared(ids)
