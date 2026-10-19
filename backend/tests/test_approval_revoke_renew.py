"""A policy governs the operations it lists: issuance, renewal, revocation.

Revocations (certificate, bulk, user certificate, intermediate CA) and the
renewal scheduler are queued for approval under a policy that requires it;
the approval performs the action with the stored parameters, checked again.
ACME cannot wait and is refused. An issuance-only policy holds neither.
"""

import base64
import json
from datetime import timedelta

import pytest
from cryptography import x509

from models import CA, AuthCertificate, Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy
from utils.datetime_utils import utc_now


def _json(client, method, url, payload=None):
    return getattr(client, method)(url, data=json.dumps(payload or {}), content_type='application/json')


def _login(app, create_user, role='operator'):
    user = create_user(role=role)
    client = app.test_client()
    r = _json(client, 'post', '/api/v2/auth/login', {'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    return client, user


def _policy(app, ca_id, name, operations):
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', ca_id=ca_id, requires_approval=True,
                                min_approvers=1, is_active=True, priority=100)
        pol.set_rules({})
        pol.set_operations(operations)
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _drop_policy(app, pid):
    with app.app_context():
        for ap in ApprovalRequest.query.filter_by(policy_id=pid).all():
            db.session.delete(ap)
        pol = db.session.get(CertificatePolicy, pid)
        if pol:
            db.session.delete(pol)
        db.session.commit()


def _cert_row(app, ca_id, cn):
    from services.cert_service import CertificateService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        db.session.commit()
        return row.id


def _cert(app, cert_id):
    with app.app_context():
        db.session.expire_all()
        row = db.session.get(Certificate, cert_id)
        return None if row is None else {
            'revoked': bool(row.revoked), 'reason': row.revoke_reason,
            'invalidity_at': row.invalidity_at, 'serial': row.serial_number, 'crt': row.crt}


def _request(app, approval_id):
    with app.app_context():
        db.session.expire_all()
        return db.session.get(ApprovalRequest, approval_id)


@pytest.fixture
def scoped(app, create_ca):
    """A CA with a revocation policy that requires approval, and a cleanup."""
    made = {'policies': [], 'certs': []}

    def make(name, operations=('revocation',)):
        ca = create_ca(cn=f'{name} CA')
        pid = _policy(app, ca['id'], name, list(operations))
        made['policies'].append(pid)
        return ca, pid

    def cert(ca, cn):
        cid = _cert_row(app, ca['id'], cn)
        made['certs'].append(cid)
        return cid

    make.cert = cert
    yield make
    for pid in made['policies']:
        _drop_policy(app, pid)
    with app.app_context():
        for cid in made['certs']:
            for ap in ApprovalRequest.query.all():
                try:
                    rd = json.loads(ap.request_data or '{}')
                except ValueError:
                    rd = {}
                if str(rd.get('certificate_id')) == str(cid) or ap.certificate_id == cid:
                    db.session.delete(ap)
            row = db.session.get(Certificate, cid)
            if row:
                db.session.delete(row)
        db.session.commit()


class TestPolicyOperations:

    def test_create_with_operations_and_legacy_type(self, app, auth_client):
        names = []
        try:
            r = _json(auth_client, 'post', '/api/v2/policies',
                      {'name': 'ops-both', 'operations': ['revocation', 'renewal']})
            assert r.status_code == 200, r.get_json()
            names.append('ops-both')
            assert r.get_json()['data']['operations'] == ['renewal', 'revocation']
            r = _json(auth_client, 'post', '/api/v2/policies', {'name': 'ops-legacy', 'policy_type': 'revocation'})
            names.append('ops-legacy')
            assert r.get_json()['data']['operations'] == ['revocation']
            r = _json(auth_client, 'post', '/api/v2/policies', {'name': 'ops-default'})
            names.append('ops-default')
            assert r.get_json()['data']['operations'] == ['issuance']
            for bad in ([], ['delete'], 'revocation'):
                r = _json(auth_client, 'post', '/api/v2/policies', {'name': 'ops-bad', 'operations': bad})
                assert r.status_code == 400, bad
            with app.app_context():
                pid = CertificatePolicy.query.filter_by(name='ops-default').first().id
            r = _json(auth_client, 'put', f'/api/v2/policies/{pid}', {'operations': ['revocation']})
            assert r.get_json()['data']['operations'] == ['revocation']
        finally:
            with app.app_context():
                CertificatePolicy.query.filter(CertificatePolicy.name.in_(names)).delete(
                    synchronize_session=False)
                db.session.commit()

    def test_rows_without_operations_keep_what_they_did(self, app):
        with app.app_context():
            assert CertificatePolicy(policy_type='issuance').get_operations() == ['issuance']
            assert CertificatePolicy(policy_type=None).get_operations() == ['issuance']
            # A renewal or revocation type was never enforced: it stays inert
            assert CertificatePolicy(policy_type='revocation').get_operations() == []
            assert CertificatePolicy(policy_type='renewal').get_operations() == []


class TestRevocation:

    def test_queued_then_revoked_with_the_requested_reason(self, app, auth_client, create_user, scoped):
        ca, _pid = scoped('rv-queue')
        cid = scoped.cert(ca, 'rv-queue.example.test')
        operator, _ = _login(app, create_user)
        when = (utc_now() - timedelta(days=2)).replace(microsecond=0)
        r = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                  {'reason': 'keyCompromise', 'invalidity_date': when.isoformat()})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()['data']
        assert body['approval_required'] is True and body['request_type'] == 'revocation'
        assert not _cert(app, cid)['revoked']

        r = _json(auth_client, 'post', f"/api/v2/approvals/{body['approval_id']}/approve", {'comment': 'ok'})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data']['certificate']['revoked'] is True
        after = _cert(app, cid)
        assert after['revoked'] and after['reason'] == 'keyCompromise'
        assert after['invalidity_at'].replace(tzinfo=None) == when.replace(tzinfo=None)
        ap = _request(app, body['approval_id'])
        assert ap.status == 'approved' and ap.certificate_id == cid

    def test_rejection_revokes_nothing(self, app, auth_client, create_user, scoped):
        ca, _pid = scoped('rv-reject')
        cid = scoped.cert(ca, 'rv-reject.example.test')
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                            {'reason': 'superseded'}).get_json()['data']['approval_id']
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/reject', {'comment': 'no'})
        assert r.status_code == 200
        assert _request(app, approval_id).status == 'rejected'
        assert not _cert(app, cid)['revoked']

    def test_the_requester_cannot_approve(self, app, create_user, scoped):
        ca, _pid = scoped('rv-self')
        cid = scoped.cert(ca, 'rv-self.example.test')
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                            {'reason': 'superseded'}).get_json()['data']['approval_id']
        r = _json(operator, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
        assert r.status_code == 403
        assert not _cert(app, cid)['revoked']
        assert _request(app, approval_id).status == 'pending'

    def test_administrators_bypass(self, app, auth_client, scoped):
        ca, _pid = scoped('rv-admin')
        cid = scoped.cert(ca, 'rv-admin.example.test')
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cid}/revoke', {'reason': 'superseded'})
        assert r.status_code == 200 and not r.get_json()['data'].get('approval_required')
        assert _cert(app, cid)['revoked']

    def test_an_issuance_policy_does_not_hold_a_revocation(self, app, create_user, scoped):
        ca, _pid = scoped('rv-issuance', operations=('issuance',))
        cid = scoped.cert(ca, 'rv-issuance.example.test')
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke', {'reason': 'superseded'})
        assert r.status_code == 200 and not r.get_json()['data'].get('approval_required')
        assert _cert(app, cid)['revoked']

    def test_bulk_revocation_is_queued(self, app, create_user, scoped):
        ca, _pid = scoped('rv-bulk')
        a = scoped.cert(ca, 'rv-bulk-a.example.test')
        b = scoped.cert(ca, 'rv-bulk-b.example.test')
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', '/api/v2/certificates/bulk/revoke', {'ids': [a, b], 'reason': 'superseded'})
        assert r.status_code == 200, r.get_json()
        data = r.get_json()['data']
        assert data['success'] == []
        assert sorted(p['id'] for p in data['pending_approval']) == sorted([a, b])
        assert not _cert(app, a)['revoked'] and not _cert(app, b)['revoked']

    def test_renewed_since_the_request_is_not_revoked(self, app, auth_client, create_user, scoped):
        ca, _pid = scoped('rv-renewed')
        cid = scoped.cert(ca, 'rv-renewed.example.test')
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                            {'reason': 'keyCompromise'}).get_json()['data']['approval_id']
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cid}/renew', {})
        assert r.status_code == 200, r.get_json()
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
        assert r.status_code == 200 and r.get_json()['data']['request_closed'] is True
        assert _request(app, approval_id).status == 'rejected'
        assert not _cert(app, cid)['revoked']

    def test_on_hold_the_approval_waits(self, app, auth_client, create_user, scoped):
        ca, _pid = scoped('rv-hold')
        cid = scoped.cert(ca, 'rv-hold.example.test')
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                            {'reason': 'keyCompromise'}).get_json()['data']['approval_id']
        assert _json(auth_client, 'post', f'/api/v2/certificates/{cid}/revoke',
                     {'reason': 'certificateHold'}).status_code == 200
        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
        assert r.get_json()['data']['certificate_issued'] is False
        assert _request(app, approval_id).status == 'pending'
        assert _cert(app, cid)['reason'] == 'certificateHold'

    def test_a_direct_revocation_closes_the_request(self, app, auth_client, create_user, scoped):
        ca, _pid = scoped('rv-direct')
        cid = scoped.cert(ca, 'rv-direct.example.test')
        operator, _ = _login(app, create_user)
        approval_id = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke',
                            {'reason': 'superseded'}).get_json()['data']['approval_id']
        assert _json(auth_client, 'post', f'/api/v2/certificates/{cid}/revoke',
                     {'reason': 'superseded'}).status_code == 200
        ap = _request(app, approval_id)
        assert ap.status == 'approved' and ap.certificate_id == cid

    def test_policy_evaluation_failure_revokes_nothing(self, app, create_user, scoped, monkeypatch):
        from services.policy_service import PolicyEvaluationService
        ca, _pid = scoped('rv-boom')
        cid = scoped.cert(ca, 'rv-boom.example.test')
        operator, _ = _login(app, create_user)

        def boom(**_kw):
            raise RuntimeError('policy store unavailable')
        monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', staticmethod(boom))
        r = _json(operator, 'post', f'/api/v2/certificates/{cid}/revoke', {'reason': 'superseded'})
        assert r.status_code == 500
        assert not _cert(app, cid)['revoked']


@pytest.fixture
def mtls_ca(app, create_ca):
    from models import SystemConfig
    ca = create_ca(cn='Approval mTLS CA')
    with app.app_context():
        row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
        previous = row.value if row else None
        if not row:
            row = SystemConfig(key='mtls_trusted_ca_id')
            db.session.add(row)
        row.value = ca['refid']
        db.session.commit()
    yield ca
    with app.app_context():
        row = SystemConfig.query.filter_by(key='mtls_trusted_ca_id').first()
        if previous is None:
            if row:
                db.session.delete(row)
        else:
            row.value = previous
        db.session.commit()


def _enrol(auth_client, user_id, name):
    r = _json(auth_client, 'post', f'/api/v2/users/{user_id}/mtls/certificates', {'mode': 'generate', 'name': name})
    assert r.status_code in (200, 201), r.data
    data = r.get_json()
    return data.get('data', data)


class TestUserCertificates:

    def test_revocation_is_queued_then_disables_the_enrolment(self, app, auth_client, create_user, mtls_ca):
        pid = _policy(app, mtls_ca['id'], 'rv-user', ['revocation'])
        try:
            _owner_client, owner = _login(app, create_user)
            operator, _ = _login(app, create_user)
            enrolment = _enrol(auth_client, owner['id'], 'approval user cert')
            r = _json(operator, 'post', f"/api/v2/user-certificates/{enrolment['id']}/revoke",
                      {'reason': 'affiliationChanged'})
            assert r.status_code == 200, r.get_json()
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                auth_cert = db.session.get(AuthCertificate, enrolment['id'])
                cert_id = auth_cert.certificate_id if hasattr(auth_cert, 'certificate_id') else None
                assert auth_cert.enabled
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                db.session.expire_all()
                assert not db.session.get(AuthCertificate, enrolment['id']).enabled
                ap = db.session.get(ApprovalRequest, approval_id)
                row = db.session.get(Certificate, ap.certificate_id)
                assert row.revoked and row.revoke_reason == 'affiliationChanged'
                assert cert_id in (None, row.id)
        finally:
            _drop_policy(app, pid)

    def test_removing_someone_else_enrolment_waits_for_the_revocation(self, app, auth_client, create_user, mtls_ca):
        pid = _policy(app, mtls_ca['id'], 'rv-remove', ['revocation'])
        try:
            owner_client, owner = _login(app, create_user)
            operator, _ = _login(app, create_user)
            theirs = _enrol(auth_client, owner['id'], 'approval removal other')
            r = operator.delete(f"/api/v2/user-certificates/{theirs['id']}")
            assert r.status_code == 409, r.get_json()
            with app.app_context():
                assert db.session.get(AuthCertificate, theirs['id']) is not None
            # Removing one's own enrolment is never held
            r = owner_client.delete(f"/api/v2/mtls/certificates/{theirs['id']}")
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                assert db.session.get(AuthCertificate, theirs['id']) is None
        finally:
            _drop_policy(app, pid)


class TestCaRevocation:

    def _intermediate(self, auth_client, root, cn):
        r = _json(auth_client, 'post', '/api/v2/cas', {
            'type': 'intermediate', 'parentCAId': root['id'], 'commonName': cn,
            'organization': 'Test Org', 'country': 'US', 'state': 'CA', 'locality': 'Test City',
            'keyType': 'RSA', 'keySize': 2048, 'validityYears': 5, 'hashAlgorithm': 'sha256'})
        assert r.status_code in (200, 201), r.data
        return r.get_json()['data']

    def test_queued_under_the_parent_then_revoked(self, app, auth_client, create_user, create_ca):
        root = create_ca(cn='rv-ca root')
        sub = self._intermediate(auth_client, root, 'rv-ca sub')
        pid = _policy(app, root['id'], 'rv-ca', ['revocation'])
        try:
            operator, _ = _login(app, create_user)
            r = _json(operator, 'post', f"/api/v2/cas/{sub['id']}/revoke", {'reason': 'cACompromise'})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert body['approval_required'] and body['request_type'] == 'ca_revocation'
            with app.app_context():
                assert not db.session.get(CA, sub['id']).revoked
            # A root cannot be revoked: refused at once, never queued
            r = _json(operator, 'post', f"/api/v2/cas/{root['id']}/revoke", {'reason': 'cACompromise'})
            assert r.status_code == 400
            r = _json(auth_client, 'post', f"/api/v2/approvals/{body['approval_id']}/approve", {})
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                db.session.expire_all()
                ca = db.session.get(CA, sub['id'])
                assert ca.revoked and ca.revoke_reason == 'cACompromise'
                assert db.session.get(ApprovalRequest, body['approval_id']).status == 'approved'
        finally:
            _drop_policy(app, pid)


class TestAcme:

    def test_a_held_revocation_is_refused(self, app, client, scoped):
        from tests.test_acme_security_paths import _build_jws, _int_to_b64, _nonce, _post_jws
        from utils.key_codec import load_pem_bytes
        from cryptography.hazmat.primitives import serialization
        ca, _pid = scoped('rv-acme')
        cid = scoped.cert(ca, 'rv-acme.example.test')
        with app.app_context():
            row = db.session.get(Certificate, cid)
            key = serialization.load_pem_private_key(load_pem_bytes(row.prv, context='test'), None)
            der = x509.load_pem_x509_certificate(base64.b64decode(row.crt)).public_bytes(
                serialization.Encoding.DER)
        pub = key.public_key().public_numbers()
        jwk = {'kty': 'RSA', 'n': _int_to_b64(pub.n), 'e': _int_to_b64(pub.e)}
        path = '/acme/revoke-cert'
        jws = _build_jws(f'http://localhost{path}',
                         {'certificate': base64.urlsafe_b64encode(der).rstrip(b'=').decode(), 'reason': 1},
                         key, jwk=jwk, nonce=_nonce(client))
        r = _post_jws(client, path, jws)
        assert r.status_code == 403, r.data
        problem = r.get_json()
        assert problem['type'] == 'urn:ietf:params:acme:error:unauthorized'
        assert 'approval' in problem['detail']
        assert not _cert(app, cid)['revoked']


class TestRenewal:

    def _run_scheduler(self, app, cert_id, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        with app.app_context():
            config = AutoRenewalService.get_renewal_config()
            previous = dict(config)
            AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                                   'renewal_sources': ['manual']})
            try:
                cert = db.session.get(Certificate, cert_id)
                monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal',
                                    staticmethod(lambda: [cert]))
                return AutoRenewalService.run_auto_renewal()
            finally:
                AutoRenewalService.set_renewal_config(previous)

    @staticmethod
    def _public_key(app, cert_id):
        with app.app_context():
            db.session.expire_all()
            crt = db.session.get(Certificate, cert_id).crt
            return x509.load_pem_x509_certificate(base64.b64decode(crt)).public_key().public_numbers()

    def test_the_scheduler_queues_then_the_approval_renews(self, app, auth_client, scoped, monkeypatch):
        ca, pid = scoped('rn-sched', operations=('renewal',))
        cid = scoped.cert(ca, 'rn-sched.example.test')
        before = _cert(app, cid)
        key_before = self._public_key(app, cid)
        stats = self._run_scheduler(app, cid, monkeypatch)
        assert stats['renewed'] == 0 and stats['queued'] == 1, stats
        assert _cert(app, cid)['serial'] == before['serial']
        with app.app_context():
            pending = [a for a in ApprovalRequest.query.filter_by(policy_id=pid, status='pending')]
            assert len(pending) == 1 and pending[0].requester_id is None
            assert pending[0].to_dict()['requester_username'] == 'auto-renewal'
            approval_id = pending[0].id
        # Queued once: the next run leaves it to the decision
        stats = self._run_scheduler(app, cid, monkeypatch)
        assert stats['renewed'] == 0, stats
        with app.app_context():
            assert ApprovalRequest.query.filter_by(policy_id=pid, status='pending').count() == 1

        r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {})
        assert r.status_code == 200 and r.get_json()['data']['certificate_issued'], r.get_json()
        assert _cert(app, cid)['serial'] != before['serial']
        # Performed as the scheduler would have: the held key re-signed
        assert self._public_key(app, cid) == key_before

    def test_the_scheduler_never_overrides_a_renewal_policy(self, app, scoped, monkeypatch):
        ca, pid = scoped('rn-late', operations=('renewal',))
        cid = scoped.cert(ca, 'rn-late.example.test')
        before = _cert(app, cid)['serial']
        self._run_scheduler(app, cid, monkeypatch)
        with app.app_context():
            ap = ApprovalRequest.query.filter_by(policy_id=pid, status='pending').one()
            # The decision would come after the certificate expires
            ap.expires_at = db.session.get(Certificate, cid).valid_to + timedelta(days=1)
            db.session.commit()
        stats = self._run_scheduler(app, cid, monkeypatch)
        assert stats['renewed'] == 0, stats
        assert _cert(app, cid)['serial'] == before

    def test_an_issuance_policy_does_not_hold_the_scheduler(self, app, scoped, monkeypatch):
        ca, _pid = scoped('rn-issuance', operations=('issuance',))
        cid = scoped.cert(ca, 'rn-issuance.example.test')
        stats = self._run_scheduler(app, cid, monkeypatch)
        assert stats['renewed'] == 1 and stats['queued'] == 0, stats

    def test_a_renewal_policy_holds_an_operator_but_not_issuance(self, app, create_user, scoped):
        ca, _pid = scoped('rn-operator', operations=('renewal',))
        cid = scoped.cert(ca, 'rn-operator.example.test')
        operator, _ = _login(app, create_user)
        r = _json(operator, 'post', f'/api/v2/certificates/{cid}/renew', {})
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        r = _json(operator, 'post', '/api/v2/certificates', {
            'cn': 'rn-operator-new.example.test', 'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code in (200, 201), r.get_json()
        # Only this policy is asserted: another file may leave a global one
        assert r.get_json()['data'].get('policy_name') != f"rn-operator-{ca['id']}"
        with app.app_context():
            new_id = r.get_json()['data'].get('id')
            row = db.session.get(Certificate, new_id) if new_id else None
            if row:
                db.session.delete(row)
                db.session.commit()


class TestBackup:

    def test_a_request_the_scheduler_queued_is_restored(self, app):
        """It names no requester; a restore must not refuse it for that."""
        from datetime import datetime
        from services.backup.export_generic import IdentityIndex, export_section
        from services.backup.restore import RestorePlan, single_transaction
        from services.backup_service import BackupService
        created = datetime(2026, 10, 1, 9, 0, 0, 424242)
        marker = 'scheduler-restore.example.test'
        with app.app_context():
            db.session.add(ApprovalRequest(
                request_type='renewal', requester_id=None, status='pending', created_at=created,
                request_data=json.dumps({'cn': marker, 'trigger': 'auto', 'requested_by': 'auto-renewal'})))
            db.session.commit()
            mine = lambda row: marker in (row.get('request_data') or '')  # noqa: E731
            payload = {'approval_requests': json.loads(json.dumps(
                [row for row in export_section('approval_requests', IdentityIndex()) if mine(row)]))}
            assert len(payload['approval_requests']) == 1
            ApprovalRequest.query.filter(ApprovalRequest.request_data.like(f'%{marker}%')).delete(
                synchronize_session=False)
            db.session.commit()
            try:
                plan = RestorePlan.build(payload)
                with single_transaction():
                    BackupService()._restore_approval_requests(payload, {}, plan)
                restored = ApprovalRequest.query.filter(
                    ApprovalRequest.request_data.like(f'%{marker}%')).all()
                assert len(restored) == 1 and restored[0].requester_id is None
            finally:
                ApprovalRequest.query.filter(ApprovalRequest.request_data.like(f'%{marker}%')).delete(
                    synchronize_session=False)
                db.session.commit()
