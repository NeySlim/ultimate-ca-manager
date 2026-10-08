"""Renewal takes an optional duration (#378): absent, the original duration is
kept; given, it is bounded like issuance, carried through approval and still
capped by policy.
"""
import base64
import json
from datetime import datetime, timezone

import pytest
from cryptography import x509

from models import Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy
from tests.test_approval_on_sign_and_renew import _cert_row, _csr_row, _drop_policy, _drop_rows, _json, _operator


def _days_left(app, cert_id):
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        cert = x509.load_pem_x509_certificate(base64.b64decode(row.crt))
        return (cert.not_valid_after_utc - datetime.now(timezone.utc)).total_seconds() / 86400


def _serial(app, cert_id):
    with app.app_context():
        return db.session.get(Certificate, cert_id).serial_number


def _policy(app, ca_id, name, *, approval, rules):
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', policy_type='issuance', ca_id=ca_id,
                                requires_approval=approval, min_approvers=1, is_active=True, priority=100)
        pol.set_rules(rules)
        db.session.add(pol)
        db.session.commit()
        return pol.id


@pytest.fixture
def cert_30d(app, create_ca):
    ca = create_ca(cn='Renew validity CA')
    cert_id = _cert_row(app, ca['id'], f'renew-validity-{ca["id"]}.example.test')
    yield ca, cert_id
    _drop_rows(app, cert_id)


class TestRenewDuration:
    def test_requested_duration_is_used(self, app, auth_client, cert_30d):
        _, cert_id = cert_30d
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 10})
        assert r.status_code == 200, r.get_json()
        assert 9.5 < _days_left(app, cert_id) <= 10.01

    @pytest.mark.parametrize('payload', [{}, {'validity_days': None}, {'validity_days': ''}])
    def test_absent_duration_keeps_the_original(self, app, auth_client, cert_30d, payload):
        _, cert_id = cert_30d
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', payload)
        assert r.status_code == 200, r.get_json()
        assert 29 < _days_left(app, cert_id) <= 30.01

    @pytest.mark.parametrize('bad', [0, -3, 3651, 'abc', True, 1.5])
    def test_out_of_bounds_is_refused_before_renewing(self, app, auth_client, cert_30d, bad):
        _, cert_id = cert_30d
        before = _serial(app, cert_id)
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': bad})
        assert r.status_code == 400
        assert 'validity_days' in r.get_json()['message']
        assert _serial(app, cert_id) == before

    def test_non_object_body_renews_with_the_original_duration(self, app, auth_client, cert_30d):
        _, cert_id = cert_30d
        r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', data='[1]',
                             content_type='application/json')
        assert r.status_code == 200, r.get_json()

    def test_policy_still_caps_the_requested_duration(self, app, auth_client, cert_30d):
        ca, cert_id = cert_30d
        pid = _policy(app, ca['id'], 'renew-cap', approval=False, rules={'max_validity_days': 5})
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 20})
            assert r.status_code == 200, r.get_json()
            assert _days_left(app, cert_id) <= 5.01
        finally:
            _drop_policy(app, pid)

    def test_microsoft_ca_certificate_refuses_a_duration(self, app, auth_client, cert_30d):
        _, cert_id = cert_30d
        with app.app_context():
            row = db.session.get(Certificate, cert_id)
            row.source = 'msca'
            db.session.commit()
        r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 10})
        assert r.status_code == 400


class TestRenewDurationThroughApproval:
    def test_duration_is_kept_and_applied_on_approval(self, app, auth_client, create_user, cert_30d):
        ca, cert_id = cert_30d
        pid = _policy(app, ca['id'], 'renew-approval-duration', approval=True, rules={})
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 7})
            assert r.status_code == 200, r.get_json()
            approval_id = r.get_json()['data']['approval_id']
            with app.app_context():
                stored = json.loads(db.session.get(ApprovalRequest, approval_id).request_data)
                assert stored['validity_days'] == 7
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert 6.5 < _days_left(app, cert_id) <= 7.01
        finally:
            _drop_policy(app, pid)


class TestRenewalNotices:
    def test_a_shortened_duration_is_reported(self, app, auth_client, cert_30d):
        ca, cert_id = cert_30d
        pid = _policy(app, ca['id'], 'renew-notice', approval=False, rules={'max_validity_days': 5})
        try:
            r = _json(auth_client, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 20})
            assert r.status_code == 200, r.get_json()
            notices = (r.get_json().get('meta') or {}).get('notices') or []
            assert notices, 'a renewal capped by policy must say so'
        finally:
            _drop_policy(app, pid)

    def test_a_shortened_duration_is_reported_on_approval(self, app, auth_client, create_user, cert_30d):
        ca, cert_id = cert_30d
        cap = _policy(app, ca['id'], 'renew-notice-cap', approval=False, rules={'max_validity_days': 5})
        gate = _policy(app, ca['id'], 'renew-notice-gate', approval=True, rules={})
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', f'/api/v2/certificates/{cert_id}/renew', {'validity_days': 20})
            approval_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            assert (r.get_json().get('meta') or {}).get('notices')
        finally:
            _drop_policy(app, gate)
            _drop_policy(app, cap)


class TestBulkRenewDuration:
    def test_bulk_renewal_refuses_a_duration(self, app, auth_client, cert_30d):
        _, cert_id = cert_30d
        before = _serial(app, cert_id)
        r = _json(auth_client, 'post', '/api/v2/certificates/bulk/renew', {'ids': [cert_id], 'validity_days': 10})
        assert r.status_code == 400
        assert _serial(app, cert_id) == before


class TestIssuanceApprovalNotices:
    def test_a_policy_cap_is_reported_to_the_approver(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='Issue approval notice CA')
        pid = _policy(app, ca['id'], 'issue-approval-cap', approval=True, rules={'max_validity_days': 5})
        operator = _operator(app, create_user)
        cn = f'issue-approval-cap-{ca["id"]}.example.test'
        try:
            r = _json(operator, 'post', '/api/v2/certificates',
                      {'cn': cn, 'ca_id': ca['id'], 'san_dns': [cn], 'validity_days': 20})
            assert r.status_code == 200, r.get_json()
            approval_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            assert (r.get_json().get('meta') or {}).get('notices')
        finally:
            _drop_policy(app, pid)
            with app.app_context():
                for row in Certificate.query.filter(Certificate.subject.contains(f'CN={cn}')).all():
                    db.session.delete(row)
                db.session.commit()


class TestCsrApprovalNotices:
    def test_a_policy_cap_is_reported_to_requester_and_approver(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='CSR approval notice CA')
        pid = _policy(app, ca['id'], 'csr-approval-cap', approval=True, rules={'max_validity_days': 5})
        csr_id = _csr_row(app, f'csr-approval-cap-{ca["id"]}.example.test')
        operator = _operator(app, create_user)
        try:
            r = _json(operator, 'post', f'/api/v2/csrs/{csr_id}/sign', {'ca_id': ca['id'], 'validity_days': 20})
            assert r.status_code == 200, r.get_json()
            assert (r.get_json().get('meta') or {}).get('notices')
            approval_id = r.get_json()['data']['approval_id']
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'ok'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            assert (r.get_json().get('meta') or {}).get('notices')
        finally:
            _drop_policy(app, pid)
            _drop_rows(app, csr_id)
