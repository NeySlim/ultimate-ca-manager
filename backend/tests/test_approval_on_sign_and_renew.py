"""An issuance policy that requires approval binds every operator path that
issues a certificate: signing a stored request (alone or in bulk) and
renewing a certificate are queued for approval like the issue form, and the
approval issues them.
"""

import json

import pytest

from models import CA, Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy


def _json(client, method, url, payload=None):
    return getattr(client, method)(url, data=json.dumps(payload or {}), content_type='application/json')


def _operator(app, create_user):
    user = create_user(role='operator')
    client = app.test_client()
    r = _json(client, 'post', '/api/v2/auth/login', {'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    return client


def _policy(app, ca_id, name):
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', policy_type='issuance', ca_id=ca_id,
                                requires_approval=True, min_approvers=1, is_active=True, priority=100)
        pol.set_rules({})
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


def _csr_row(app, cn):
    from services.cert_service import CertificateService
    with app.app_context():
        row = CertificateService.generate_csr(descr=cn, dn={'CN': cn}, key_type='2048')
        db.session.commit()
        return row.id


def _cert_row(app, ca_id, cn):
    from services.cert_service import CertificateService
    with app.app_context():
        ca = db.session.get(CA, ca_id)
        row = CertificateService.create_certificate(
            descr=cn, caref=ca.refid, dn={'CN': cn}, cert_type='server_cert',
            key_type='2048', validity_days=30, username='admin')
        db.session.commit()
        return row.id


def _drop_rows(app, *ids):
    """Delete the rows and every approval request about them. A request
    may have been attributed to a policy left behind by another test file
    (the gate picks the highest-priority match), and SQLite reuses the id
    of a deleted row: a request left pending would name the next row."""
    with app.app_context():
        wanted = {str(rid) for rid in ids}
        for ap in ApprovalRequest.query.all():
            try:
                rd = json.loads(ap.request_data or '{}')
            except Exception:
                rd = {}
            names = {str(rd.get('csr_id')), str(rd.get('certificate_id')), str(ap.certificate_id)} if isinstance(rd, dict) else {str(ap.certificate_id)}
            if names & wanted:
                db.session.delete(ap)
        for rid in ids:
            row = db.session.get(Certificate, rid)
            if row:
                db.session.delete(row)
        db.session.commit()


class TestSignCsr:

    def test_queued_then_issued_on_approval(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='Approval sign CSR CA')
        pid = _policy(app, ca['id'], 'approval-sign')
        csr_id = _csr_row(app, 'approval-sign.example.test')
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert body.get('approval_required') is True
            approval_id = body['approval_id']
            with app.app_context():
                assert not db.session.get(Certificate, csr_id).crt
                assert db.session.get(ApprovalRequest, approval_id).request_type == 'csr'

            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            with app.app_context():
                row = db.session.get(Certificate, csr_id)
                assert row.crt and row.caref
                assert db.session.get(ApprovalRequest, approval_id).certificate_id == csr_id
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_admin_signs_directly(self, app, auth_client, create_ca):
        ca = create_ca(cn='Approval sign admin CA')
        pid = _policy(app, ca['id'], 'approval-sign-admin')
        csr_id = _csr_row(app, 'approval-sign-admin.example.test')
        try:
            r = _json(auth_client, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            assert not r.get_json()['data'].get('approval_required')
            with app.app_context():
                assert db.session.get(Certificate, csr_id).crt
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_evaluation_error_fails_closed(self, app, create_ca, create_user, monkeypatch):
        from services.policy_service import PolicyEvaluationService
        ca = create_ca(cn='Approval sign fail-closed CA')
        pid = _policy(app, ca['id'], 'approval-sign-closed')
        csr_id = _csr_row(app, 'approval-sign-closed.example.test')
        operator = _operator(app, create_user)

        def boom(*args, **kwargs):
            raise RuntimeError('evaluation exploded')
        monkeypatch.setattr(PolicyEvaluationService, 'check_approval_required', staticmethod(boom))
        try:
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 500, (r.status_code, r.get_json())
            with app.app_context():
                assert not db.session.get(Certificate, csr_id).crt
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_bulk_sign_reports_pending_approval(self, app, create_ca, create_user):
        ca = create_ca(cn='Approval bulk sign CA')
        pid = _policy(app, ca['id'], 'approval-bulk-sign')
        csr_id = _csr_row(app, 'approval-bulk-sign.example.test')
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', '/api/v2/csrs/bulk/sign', {'ids': [csr_id], 'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert [p['id'] for p in body.get('pending_approval', [])] == [csr_id]
            assert body['success'] == [] and body['failed'] == []
            with app.app_context():
                assert not db.session.get(Certificate, csr_id).crt
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)


class TestRenew:

    def test_queued_then_renewed_on_approval(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='Approval renew CA')
        pid = _policy(app, ca['id'], 'approval-renew')
        cert_id = _cert_row(app, ca['id'], 'approval-renew.example.test')
        operator = _operator(app, create_user)
        try:
            with app.app_context():
                before = db.session.get(Certificate, cert_id).serial_number
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert body.get('approval_required') is True
            approval_id = body['approval_id']
            with app.app_context():
                row = db.session.get(Certificate, cert_id)
                assert row.serial_number == before and (row.renewed_times or 0) == 0
                assert db.session.get(ApprovalRequest, approval_id).request_type == 'renewal'

            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            with app.app_context():
                row = db.session.get(Certificate, cert_id)
                assert row.serial_number != before and row.renewed_times == 1
                assert db.session.get(ApprovalRequest, approval_id).certificate_id == cert_id
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_bulk_renew_reports_pending_approval(self, app, create_ca, create_user):
        ca = create_ca(cn='Approval bulk renew CA')
        pid = _policy(app, ca['id'], 'approval-bulk-renew')
        cert_id = _cert_row(app, ca['id'], 'approval-bulk-renew.example.test')
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', '/api/v2/certificates/bulk/renew', {'ids': [cert_id]})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert [p['id'] for p in body.get('pending_approval', [])] == [cert_id]
            with app.app_context():
                assert (db.session.get(Certificate, cert_id).renewed_times or 0) == 0
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)


class TestRenewStateBeforeGate:

    def test_revoked_certificate_is_refused_not_queued(self, app, create_ca, create_user):
        ca = create_ca(cn='Approval renew revoked CA')
        pid = _policy(app, ca['id'], 'approval-renew-revoked')
        cert_id = _cert_row(app, ca['id'], 'approval-renew-revoked.example.test')
        operator = _operator(app, create_user)
        try:
            with app.app_context():
                db.session.get(Certificate, cert_id).revoked = True
                db.session.commit()
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 409, (r.status_code, r.get_json())
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_bulk_renew_of_a_request_row_fails_per_item(self, app, create_ca, create_user):
        ca = create_ca(cn='Approval bulk renew CSR CA')
        pid = _policy(app, ca['id'], 'approval-bulk-renew-csr')
        csr_id = _csr_row(app, 'approval-bulk-renew-csr.example.test')
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', '/api/v2/certificates/bulk/renew', {'ids': [csr_id]})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert body.get('pending_approval', []) == []
            assert body['failed'] and 'not available' in body['failed'][0]['error'].lower()
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)


class TestMootRequestsAreResolved:
    """A request queued for approval whose target was signed, renewed,
    deleted or revoked meanwhile is closed instead of waiting for expiry."""

    def _queue_sign(self, app, auth_client, create_ca, create_user, name):
        ca = create_ca(cn=f'{name} CA')
        pid = _policy(app, ca['id'], name)
        csr_id = _csr_row(app, f'{name}.example.test')
        operator = _operator(app, create_user)
        r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        return ca, pid, csr_id, r.get_json()['data']['approval_id']

    def test_direct_signing_closes_the_request_as_approved(self, app, auth_client, create_ca, create_user):
        ca, pid, csr_id, approval_id = self._queue_sign(app, auth_client, create_ca, create_user, 'moot-sign')
        try:
            r = _json(auth_client, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'approved' and ap.certificate_id == csr_id
                assert ap.get_approvals()[-1]['username'] == 'admin'
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'late'})
            assert r.status_code == 400
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_deleting_the_request_closes_it_as_rejected(self, app, auth_client, create_ca, create_user):
        ca, pid, csr_id, approval_id = self._queue_sign(app, auth_client, create_ca, create_user, 'moot-delete')
        try:
            r = auth_client.delete(f'/api/v2/csrs/{csr_id}')
            assert r.status_code in (200, 204), r.data
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'rejected' and 'deleted' in (ap.get_approvals()[-1]['comment'] or '').lower()
                assert ap.get_approvals()[-1]['username'] == 'admin'  # the admin who deleted it
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_approving_an_already_signed_request_closes_on_the_certificate(self, app, auth_client, create_ca, create_user):
        ca, pid, csr_id, approval_id = self._queue_sign(app, auth_client, create_ca, create_user, 'moot-stale')
        try:
            # signed by a path that did not resolve the request (older code, restore)
            from services.cert_service import CertificateService
            with app.app_context():
                ca_row = db.session.get(CA, ca['id'])
                CertificateService.sign_csr(cert_id=csr_id, caref=ca_row.refid, validity_days=30)
                db.session.commit()
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.status = 'pending'  # undo the automatic resolution to simulate a stale request
                ap.certificate_id = None
                ap.approvals = '[]'
                db.session.commit()
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            body = r.get_json()['data']
            assert body['certificate_issued'] is True and body.get('already_issued') is True
            with app.app_context():
                assert db.session.get(ApprovalRequest, approval_id).certificate_id == csr_id
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def _queue_renew(self, app, create_ca, create_user, name):
        ca = create_ca(cn=f'{name} CA')
        pid = _policy(app, ca['id'], name)
        cert_id = _cert_row(app, ca['id'], f'{name}.example.test')
        operator = _operator(app, create_user)
        r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        return ca, pid, cert_id, r.get_json()['data']['approval_id']

    def test_direct_renewal_closes_the_request_as_approved(self, app, auth_client, create_ca, create_user):
        ca, pid, cert_id, approval_id = self._queue_renew(app, create_ca, create_user, 'moot-renew')
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew')
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'approved' and ap.certificate_id == cert_id
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_revocation_closes_the_renewal_request_as_rejected(self, app, auth_client, create_ca, create_user):
        ca, pid, cert_id, approval_id = self._queue_renew(app, create_ca, create_user, 'moot-revoke')
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/revoke', {'reason': 'keyCompromise'})
            assert r.status_code in (200, 201), r.get_json()
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'rejected' and 'revoked' in (ap.get_approvals()[-1]['comment'] or '').lower()
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)


class TestDuplicateRequestsFollowTheApprover:
    """Two operators may queue the same target. Approving one request closes
    the other as approved by that same approver, not by the requester of the
    first, and links it to the certificate."""

    def test_duplicate_sign_requests_are_approved_by_the_approver(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='dup-sign CA')
        pid = _policy(app, ca['id'], 'dup-sign')
        csr_id = _csr_row(app, 'dup-sign.example.test')
        try:
            ids = []
            for _ in range(2):
                operator = _operator(app, create_user)
                r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
                assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
                ids.append(r.get_json()['data']['approval_id'])
            first, second = ids
            r = _json(auth_client, 'post', f'/api/v2/approvals/{first}/approve', {'comment': 'ok'})
            assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is True, r.get_json()
            with app.app_context():
                dup = db.session.get(ApprovalRequest, second)
                assert dup.status == 'approved' and dup.certificate_id == csr_id
                vote = dup.get_approvals()[-1]
                assert vote['username'] == 'admin' and vote['user_id'] is not None
                assert vote['comment'] == f'Approved with request #{first}'
                assert db.session.get(ApprovalRequest, first).certificate_id == csr_id
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_duplicate_renewal_requests_are_approved_by_the_approver(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='dup-renew CA')
        pid = _policy(app, ca['id'], 'dup-renew')
        cert_id = _cert_row(app, ca['id'], 'dup-renew.example.test')
        try:
            ids = []
            for _ in range(2):
                operator = _operator(app, create_user)
                r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
                assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
                ids.append(r.get_json()['data']['approval_id'])
            first, second = ids
            r = _json(auth_client, 'post', f'/api/v2/approvals/{first}/approve', {'comment': 'ok'})
            assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is True, r.get_json()
            with app.app_context():
                dup = db.session.get(ApprovalRequest, second)
                assert dup.status == 'approved' and dup.certificate_id == cert_id
                vote = dup.get_approvals()[-1]
                assert vote['username'] == 'admin' and vote['user_id'] is not None
                assert vote['comment'] == f'Approved with request #{first}'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_failed_issuance_leaves_the_duplicate_pending(self, app, auth_client, create_ca, create_user, monkeypatch):
        ca = create_ca(cn='dup-fail CA')
        pid = _policy(app, ca['id'], 'dup-fail')
        csr_id = _csr_row(app, 'dup-fail.example.test')
        try:
            ids = []
            for _ in range(2):
                operator = _operator(app, create_user)
                r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
                ids.append(r.get_json()['data']['approval_id'])
            first, second = ids
            from services.cert_service import CertificateService

            def boom(*_a, **_k):
                raise ValueError('CA is offline')
            monkeypatch.setattr(CertificateService, 'sign_csr', staticmethod(boom))
            r = _json(auth_client, 'post', f'/api/v2/approvals/{first}/approve', {'comment': 'ok'})
            assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is False, r.get_json()
            with app.app_context():
                assert db.session.get(ApprovalRequest, first).status == 'pending'
                assert db.session.get(ApprovalRequest, second).status == 'pending'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)


class TestMootScanIsRobust:

    def test_non_object_request_data_is_skipped(self, app, create_ca, create_user):
        from services.approval_gate import pending_requests_naming, resolve_moot_requests
        ca = create_ca(cn='moot-robust CA')
        pid = _policy(app, ca['id'], 'moot-robust')
        with app.app_context():
            from models.policy import CertificatePolicy
            operator = create_user(role='operator')
            rows = []
            for payload in ('[1, 2]', '"oops"', 'not json', '{"csr_id": 4242}'):
                ap = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='csr',
                                     request_data=payload, status='pending', required_approvals=1)
                db.session.add(ap)
                rows.append(ap)
            db.session.commit()
            try:
                assert pending_requests_naming('csr', 'csr_id', None) == []
                found = pending_requests_naming('csr', 'csr_id', 4242)
                assert [a.id for a in found] == [rows[-1].id]
                assert len(resolve_moot_requests('csr', 'csr_id', 4242, outcome='rejected',
                                                 username='admin', reason='gone')) == 1
            finally:
                _drop_policy(app, pid)

    def test_external_completion_closes_the_request(self, app, auth_client, create_ca, create_user):
        """A pending CSR completed with a certificate issued elsewhere (#341)
        is closed as approved, like a direct signing."""
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
        import base64
        import datetime
        ca = create_ca(cn='moot-ext CA')
        pid = _policy(app, ca['id'], 'moot-ext')
        csr_id = _csr_row(app, 'moot-ext.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                from services.cert_service import CertificateService
                row = db.session.get(Certificate, csr_id)
                csr = x509.load_pem_x509_csr(base64.b64decode(row.csr))
                issuer_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
                now = datetime.datetime.now(datetime.timezone.utc)
                cert = (x509.CertificateBuilder()
                        .subject_name(csr.subject)
                        .issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'External CA')]))
                        .public_key(csr.public_key()).serial_number(x509.random_serial_number())
                        .not_valid_before(now).not_valid_after(now + datetime.timedelta(days=30))
                        .sign(issuer_key, hashes.SHA256()))
                CertificateService.complete_external_csr(
                    row, cert, cert.public_bytes(serialization.Encoding.PEM), username='admin')
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'approved' and ap.certificate_id == csr_id
                assert ap.get_approvals()[-1]['comment'] == 'Certificate imported'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)


class TestRemainingEdges:
    """A hold is temporary: the renewal request waits for the unhold. An
    expired request is closed as expired, never as approved, by a direct
    action. The scheduler leaves a certificate whose renewal awaits a human
    decision alone. Stale pending requests are expired by a task."""

    def _queue_renew(self, app, create_ca, create_user, name):
        ca = create_ca(cn=f'{name} CA')
        pid = _policy(app, ca['id'], name)
        cert_id = _cert_row(app, ca['id'], f'{name}.example.test')
        operator = _operator(app, create_user)
        r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        return ca, pid, cert_id, r.get_json()['data']['approval_id']

    def test_hold_keeps_the_renewal_request_pending_until_unhold(self, app, auth_client, create_ca, create_user):
        ca, pid, cert_id, approval_id = self._queue_renew(app, create_ca, create_user, 'edge-hold')
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/revoke', {'reason': 'certificateHold'})
            assert r.status_code in (200, 201), r.get_json()
            with app.app_context():
                assert db.session.get(ApprovalRequest, approval_id).status == 'pending'
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'held'})
            assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is False, r.get_json()
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/unhold')
            assert r.status_code == 200, r.get_json()
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200 and r.get_json()['data']['certificate_issued'] is True, r.get_json()
            with app.app_context():
                assert db.session.get(Certificate, cert_id).renewed_times == 1
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_expired_request_is_closed_as_expired_by_a_direct_action(self, app, auth_client, create_ca, create_user):
        from datetime import timedelta
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='edge-expired CA')
        pid = _policy(app, ca['id'], 'edge-expired')
        csr_id = _csr_row(app, 'edge-expired.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.expires_at = utc_now() - timedelta(hours=1)
                db.session.commit()
            r = _json(auth_client, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'expired' and ap.resolved_at is not None
                assert ap.get_approvals() == [] and ap.certificate_id is None
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_scheduler_skips_a_certificate_whose_renewal_awaits_approval(self, app, create_ca, create_user, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        ca, pid, cert_id, approval_id = self._queue_renew(app, create_ca, create_user, 'edge-sched')
        try:
            with app.app_context():
                config = AutoRenewalService.get_renewal_config()
                previous = dict(config)
                AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                                       'renewal_sources': ['manual']})
                try:
                    cert = db.session.get(Certificate, cert_id)
                    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal',
                                        staticmethod(lambda: [cert]))
                    stats = AutoRenewalService.run_auto_renewal()
                finally:
                    AutoRenewalService.set_renewal_config(previous)
                assert stats['skipped'] == 1 and stats['renewed'] == 0, stats
                assert (db.session.get(Certificate, cert_id).renewed_times or 0) == 0
                assert db.session.get(ApprovalRequest, approval_id).status == 'pending'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_stale_pending_requests_are_expired(self, app, auth_client, create_ca, create_user):
        from datetime import timedelta
        from services.approval_gate import expire_stale_requests
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='edge-stale CA')
        pid = _policy(app, ca['id'], 'edge-stale')
        with app.app_context():
            operator = create_user(role='operator')
            stale = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='csr',
                                    request_data='{"csr_id": 1}', status='pending', required_approvals=1,
                                    expires_at=utc_now() - timedelta(days=1))
            fresh = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='csr',
                                    request_data='{"csr_id": 2}', status='pending', required_approvals=1,
                                    expires_at=utc_now() + timedelta(days=1))
            db.session.add_all([stale, fresh])
            db.session.commit()
            stale_id, fresh_id = stale.id, fresh.id
        try:
            with app.app_context():
                assert expire_stale_requests() == 1
                assert expire_stale_requests() == 0
                s = db.session.get(ApprovalRequest, stale_id)
                assert s.status == 'expired' and s.resolved_at is not None
                assert db.session.get(ApprovalRequest, fresh_id).status == 'pending'
            # the pending list never shows a request past its expiry
            with app.app_context():
                db.session.get(ApprovalRequest, stale_id).status = 'pending'
                db.session.commit()
            r = auth_client.get('/api/v2/approvals?status=pending')
            assert r.status_code == 200
            assert stale_id not in [a['id'] for a in r.get_json()['data']]
            assert fresh_id in [a['id'] for a in r.get_json()['data']]
            with app.app_context():
                assert db.session.get(ApprovalRequest, stale_id).status == 'expired'
        finally:
            _drop_policy(app, pid)


class TestReviewFollowUps:
    """A request past its expiry never holds anything back, wherever it is
    counted; a request without an expiry has the standard lifetime; the
    scheduler steps aside only while the decision can come before the
    certificate expires; a request whose target is gone is closed."""

    def _queue_renew(self, app, create_ca, create_user, name):
        ca = create_ca(cn=f'{name} CA')
        pid = _policy(app, ca['id'], name)
        cert_id = _cert_row(app, ca['id'], f'{name}.example.test')
        user = create_user(role='operator')
        client = app.test_client()
        r = _json(client, 'post', '/api/v2/auth/login', {'username': user['username'], 'password': 'TestPass123!'})
        assert r.status_code == 200
        r = _json(client, 'post', f'/api/v2/certificates/{cert_id}/renew')
        assert r.status_code == 200 and r.get_json()['data'].get('approval_required'), r.get_json()
        return ca, pid, cert_id, r.get_json()['data']['approval_id'], user

    def _run_scheduler_on(self, app, cert_id, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        config = AutoRenewalService.get_renewal_config()
        previous = dict(config)
        AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                               'renewal_sources': ['manual']})
        try:
            cert = db.session.get(Certificate, cert_id)
            monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(lambda: [cert]))
            return AutoRenewalService.run_auto_renewal()
        finally:
            AutoRenewalService.set_renewal_config(previous)

    def test_scheduler_renews_when_the_pending_request_has_expired(self, app, create_ca, create_user, monkeypatch):
        from datetime import timedelta
        from utils.datetime_utils import utc_now
        ca, pid, cert_id, approval_id, _user = self._queue_renew(app, create_ca, create_user, 'fu-expired')
        try:
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.expires_at = utc_now() - timedelta(hours=2)
                db.session.commit()
                stats = self._run_scheduler_on(app, cert_id, monkeypatch)
                assert stats['renewed'] == 1 and stats['skipped'] == 0, stats
                assert db.session.get(ApprovalRequest, approval_id).status == 'expired'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_scheduler_renews_when_the_certificate_would_expire_first(self, app, create_ca, create_user, monkeypatch):
        from datetime import timedelta
        ca, pid, cert_id, approval_id, _user = self._queue_renew(app, create_ca, create_user, 'fu-deadline')
        try:
            with app.app_context():
                cert = db.session.get(Certificate, cert_id)
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.expires_at = cert.valid_to + timedelta(days=1)
                db.session.commit()
                stats = self._run_scheduler_on(app, cert_id, monkeypatch)
                assert stats['renewed'] == 1 and stats['skipped'] == 0, stats
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'approved' and ap.get_approvals()[-1]['comment'] == 'Renewed by the scheduler'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id)

    def test_stale_requests_are_not_counted_anywhere(self, app, auth_client, create_ca, create_user):
        from datetime import timedelta
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='fu-count CA')
        pid = _policy(app, ca['id'], 'fu-count')
        with app.app_context():
            operator = create_user(role='operator')
            stale = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='csr',
                                    request_data='{"csr_id": 1}', status='pending', required_approvals=1,
                                    expires_at=utc_now() - timedelta(days=1))
            db.session.add(stale)
            db.session.commit()
            stale_id = stale.id
        try:
            r = auth_client.get('/api/v2/approvals/stats')
            assert r.status_code == 200
            with app.app_context():
                assert db.session.get(ApprovalRequest, stale_id).status == 'expired'
                db.session.get(ApprovalRequest, stale_id).status = 'pending'
                db.session.commit()
            r = auth_client.delete(f"/api/v2/users/{operator['id']}")
            assert r.status_code in (200, 204), r.get_json()
        finally:
            _drop_policy(app, pid)

    def test_request_without_expiry_has_the_standard_lifetime(self, app, create_ca, create_user):
        from datetime import timedelta
        from services.approval_gate import approval_is_expired, expire_stale_requests, pending_target_ids
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='fu-noexp CA')
        pid = _policy(app, ca['id'], 'fu-noexp')
        with app.app_context():
            operator = create_user(role='operator')
            old = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='renewal',
                                  request_data='{"certificate_id": 777001}', status='pending',
                                  required_approvals=1, expires_at=None,
                                  created_at=utc_now() - timedelta(days=8))
            recent = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='renewal',
                                     request_data='{"certificate_id": 777002}', status='pending',
                                     required_approvals=1, expires_at=None,
                                     created_at=utc_now() - timedelta(days=1))
            db.session.add_all([old, recent])
            db.session.commit()
            try:
                assert approval_is_expired(old) is True and approval_is_expired(recent) is False
                assert pending_target_ids('renewal', 'certificate_id').keys() >= {'777002'}
                assert '777001' not in pending_target_ids('renewal', 'certificate_id')
                assert expire_stale_requests() == 1
                assert old.status == 'expired' and recent.status == 'pending'
            finally:
                _drop_policy(app, pid)

    def test_approving_a_request_whose_target_is_gone_closes_it(self, app, auth_client, create_ca, create_user, monkeypatch):
        ca = create_ca(cn='fu-gone CA')
        pid = _policy(app, ca['id'], 'fu-gone')
        csr_id = _csr_row(app, 'fu-gone.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                # gone without the service noticing (older code, restore)
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.request_data = ap.request_data.replace(str(csr_id), '999999')
                db.session.commit()
            import api.v2.policies as policies_module
            emitted = []
            monkeypatch.setattr('services.webhook_service.emit_csr_rejected',
                                lambda payload, reason=None, actor=None: emitted.append((payload, reason)))
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            body = r.get_json()['data']
            assert r.status_code == 200 and body['certificate_issued'] is False, r.get_json()
            assert body.get('request_closed') is True and 'no longer exists' in body['issue_error']
            assert emitted and emitted[0][0]['id'] == approval_id and 'no longer exists' in emitted[0][1]
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'rejected' and ap.resolved_at is not None
                assert 'no longer exists' in ap.get_approvals()[-1]['comment']
                from models import AuditLog
                last = AuditLog.query.filter_by(resource_type='approval', resource_id=str(approval_id)).order_by(AuditLog.id.desc()).first()
                assert last.action == 'approval_closed'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_renewal_rereads_the_certificate_before_deciding(self, app, create_ca):
        """The instance handed to the renewal may be stale: the row is read
        again (locked on PostgreSQL) before the revocation check."""
        from sqlalchemy import text
        from services.cert.renewal import RenewalError, renew_certificate_in_place
        ca = create_ca(cn='fu-stale CA')
        cert_id = _cert_row(app, ca['id'], 'fu-stale.example.test')
        try:
            with app.app_context():
                cert = db.session.get(Certificate, cert_id)
                assert cert.revoked is False
                db.session.execute(text('UPDATE certificates SET revoked = :flag WHERE id = :id'),
                                   {'id': cert_id, 'flag': True})
                with pytest.raises(RenewalError):
                    renew_certificate_in_place(cert, username='admin')
                db.session.rollback()
        finally:
            _drop_rows(app, cert_id)


class TestSecondReviewFollowUps:

    def test_first_of_two_votes_closes_a_request_whose_target_is_gone(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='fu2-two CA')
        with app.app_context():
            pol = CertificatePolicy(name=f'fu2-two-{ca["id"]}', policy_type='issuance', ca_id=ca['id'],
                                    requires_approval=True, min_approvers=2, is_active=True, priority=100)
            pol.set_rules({})
            db.session.add(pol)
            db.session.commit()
            pid = pol.id
        csr_id = _csr_row(app, 'fu2-two.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                ap.request_data = ap.request_data.replace(str(csr_id), '999999')
                db.session.commit()
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200 and r.get_json()['data'].get('request_closed') is True, r.get_json()
            with app.app_context():
                assert db.session.get(ApprovalRequest, approval_id).status == 'rejected'
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)

    def test_scheduler_does_not_renew_twice_a_certificate_renewed_during_its_batch(self, app, create_ca, create_user, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        ca = create_ca(cn='fu2-batch CA')
        cert_id = _cert_row(app, ca['id'], 'fu2-batch.example.test')
        try:
            with app.app_context():
                config = AutoRenewalService.get_renewal_config()
                previous = dict(config)
                AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                                       'renewal_sources': ['manual']})
                try:
                    cert = db.session.get(Certificate, cert_id)
                    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(lambda: [cert]))
                    import services.auto_renewal_service as ars

                    def renewed_by_an_operator_meanwhile(*_a, **_k):
                        db.session.query(Certificate).filter(Certificate.id == cert_id).update(
                            {Certificate.serial_number: 'deadbeef'}, synchronize_session=False)
                        db.session.commit()
                        return {}
                    monkeypatch.setattr('services.approval_gate.pending_target_ids', renewed_by_an_operator_meanwhile)
                    stats = AutoRenewalService.run_auto_renewal()
                finally:
                    AutoRenewalService.set_renewal_config(previous)
                assert stats['renewed'] == 0 and stats['failed'] == 1, stats
                assert 'another request' in stats['errors'][0]['error']
                assert 'reload' not in stats['errors'][0]['error']  # nobody to retry in a batch
                assert db.session.get(Certificate, cert_id).serial_number == 'deadbeef'
        finally:
            _drop_rows(app, cert_id)

    def test_stale_request_does_not_block_policy_deletion_and_reads_as_expired(self, app, auth_client, create_ca, create_user):
        from datetime import timedelta
        from utils.datetime_utils import utc_now
        ca = create_ca(cn='fu2-policy CA')
        pid = _policy(app, ca['id'], 'fu2-policy')
        with app.app_context():
            operator = create_user(role='operator')
            stale = ApprovalRequest(policy_id=pid, requester_id=operator['id'], request_type='csr',
                                    request_data='{"csr_id": 1}', status='pending', required_approvals=1,
                                    expires_at=utc_now() - timedelta(days=1))
            db.session.add(stale)
            db.session.commit()
            stale_id = stale.id
        try:
            r = auth_client.get(f'/api/v2/approvals/{stale_id}')
            assert r.status_code == 200 and r.get_json()['data']['status'] == 'expired'
            with app.app_context():
                db.session.get(ApprovalRequest, stale_id).status = 'pending'
                db.session.commit()
            r = auth_client.get('/api/v2/approvals?status=expired')
            assert stale_id in [a['id'] for a in r.get_json()['data']]
            with app.app_context():
                db.session.get(ApprovalRequest, stale_id).status = 'pending'
                db.session.commit()
            r = auth_client.delete(f'/api/v2/policies/{pid}')
            assert r.status_code in (200, 204), r.get_json()
        finally:
            _drop_policy(app, pid)

    def test_deadline_converts_aware_times_to_utc(self):
        from datetime import datetime, timedelta, timezone
        from services.approval_gate import request_deadline
        ap = ApprovalRequest(expires_at=datetime(2026, 9, 11, 12, 0, tzinfo=timezone(timedelta(hours=2))))
        assert request_deadline(ap) == datetime(2026, 9, 11, 10, 0)


class TestThirdReviewFollowUps:

    def test_scheduler_batch_survives_a_row_deleted_meanwhile(self, app, create_ca, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        ca = create_ca(cn='fu3-batch CA')
        gone_id = _cert_row(app, ca['id'], 'fu3-gone.example.test')
        kept_id = _cert_row(app, ca['id'], 'fu3-kept.example.test')
        try:
            with app.app_context():
                config = AutoRenewalService.get_renewal_config()
                previous = dict(config)
                AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                                       'renewal_sources': ['manual']})
                try:
                    listed = [db.session.get(Certificate, gone_id), db.session.get(Certificate, kept_id)]
                    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(lambda: listed))

                    def deleted_by_an_operator_meanwhile(*_a, **_k):
                        db.session.query(Certificate).filter(Certificate.id == gone_id).delete(synchronize_session=False)
                        db.session.commit()
                        return {}
                    monkeypatch.setattr('services.approval_gate.pending_target_ids', deleted_by_an_operator_meanwhile)
                    stats = AutoRenewalService.run_auto_renewal()
                finally:
                    AutoRenewalService.set_renewal_config(previous)
                assert stats['renewed'] == 1 and stats['skipped'] == 1 and stats['failed'] == 0, stats
                assert db.session.get(Certificate, kept_id).renewed_times == 1
        finally:
            _drop_rows(app, gone_id, kept_id)

    def test_certificate_without_serial_renewed_meanwhile_is_refused(self, app, create_ca):
        from services.cert.renewal import RenewalError, renew_certificate_in_place
        ca = create_ca(cn='fu3-noserial CA')
        cert_id = _cert_row(app, ca['id'], 'fu3-noserial.example.test')
        try:
            with app.app_context():
                db.session.query(Certificate).filter(Certificate.id == cert_id).update(
                    {Certificate.serial_number: None}, synchronize_session=False)
                db.session.commit()
                cert = db.session.get(Certificate, cert_id)
                assert cert.serial_number is None
                db.session.query(Certificate).filter(Certificate.id == cert_id).update(
                    {Certificate.serial_number: 'renewed01'}, synchronize_session=False)
                db.session.expire(cert)  # as after a commit earlier in the batch
                with pytest.raises(RenewalError) as exc:
                    renew_certificate_in_place(cert, username='admin', known_serial=None)
                assert exc.value.status == 409
                db.session.rollback()
        finally:
            _drop_rows(app, cert_id)

    def test_closure_by_revocation_or_deletion_notifies_webhooks(self, app, auth_client, create_ca, create_user, monkeypatch):
        emitted = []
        monkeypatch.setattr('services.webhook_service.emit_csr_rejected',
                            lambda payload, reason=None, actor=None: emitted.append((payload['id'], reason)))
        ca = create_ca(cn='fu3-notify CA')
        pid = _policy(app, ca['id'], 'fu3-notify')
        cert_id = _cert_row(app, ca['id'], 'fu3-notify.example.test')
        csr_id = _csr_row(app, 'fu3-notify-csr.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew')
            renewal_id = r.get_json()['data']['approval_id']
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            sign_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/revoke', {'reason': 'keyCompromise'})
            assert r.status_code in (200, 201), r.get_json()
            r = auth_client.delete(f'/api/v2/csrs/{csr_id}')
            assert r.status_code in (200, 204), r.data
            assert (renewal_id, 'Certificate revoked') in emitted, emitted
            assert (sign_id, 'Request deleted') in emitted, emitted
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, cert_id, csr_id)


class TestFourthReviewFollowUps:

    def test_first_row_of_the_batch_deleted_before_any_commit_is_skipped(self, app, create_ca, monkeypatch):
        from services.auto_renewal_service import AutoRenewalService
        ca = create_ca(cn='fu4-batch CA')
        gone_id = _cert_row(app, ca['id'], 'fu4-gone.example.test')
        try:
            with app.app_context():
                config = AutoRenewalService.get_renewal_config()
                previous = dict(config)
                AutoRenewalService.set_renewal_config({**config, 'enabled': True, 'days_before_expiry': 60,
                                                       'renewal_sources': ['manual']})
                try:
                    listed = [db.session.get(Certificate, gone_id)]
                    monkeypatch.setattr(AutoRenewalService, 'get_certificates_for_renewal', staticmethod(lambda: listed))

                    def deleted_without_expiring_the_instance(*_a, **_k):
                        # flushed in the same transaction: the listed instance is not expired
                        db.session.query(Certificate).filter(Certificate.id == gone_id).delete(synchronize_session=False)
                        return {}
                    monkeypatch.setattr('services.approval_gate.pending_target_ids', deleted_without_expiring_the_instance)
                    stats = AutoRenewalService.run_auto_renewal()
                    db.session.rollback()
                finally:
                    AutoRenewalService.set_renewal_config(previous)
                assert stats['skipped'] == 1 and stats['failed'] == 0 and stats['renewed'] == 0, stats
        finally:
            _drop_rows(app, gone_id)

    def test_reject_route_names_the_actor_to_webhooks(self, app, auth_client, create_ca, create_user, monkeypatch):
        emitted = []
        monkeypatch.setattr('services.webhook_service.emit_csr_rejected',
                            lambda payload, reason=None, actor=None: emitted.append((payload['id'], reason, actor)))
        ca = create_ca(cn='fu4-reject CA')
        pid = _policy(app, ca['id'], 'fu4-reject')
        csr_id = _csr_row(app, 'fu4-reject.example.test')
        try:
            operator = _operator(app, create_user)
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 30})
            approval_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/reject', {'comment': 'no'})
            assert r.status_code == 200, r.get_json()
            assert emitted == [(approval_id, 'no', 'admin')], emitted
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)
