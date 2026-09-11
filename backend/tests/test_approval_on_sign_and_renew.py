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
