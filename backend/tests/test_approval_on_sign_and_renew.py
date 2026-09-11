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
    with app.app_context():
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
