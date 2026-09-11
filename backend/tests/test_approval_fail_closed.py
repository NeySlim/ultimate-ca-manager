"""The approval workflow fails closed, and a failed issuance leaves the
approval replayable.

Before this fix, any exception raised while evaluating the issuance
policies (a malformed ``san`` payload was enough) was logged as
"non-blocking" and the certificate was issued without approval; and when the
issuance triggered by an approval failed (CA offline, HSM unreachable, policy
violation), the approver's vote was still recorded, so the request flipped to
``approved`` with no certificate and could never be approved again.
"""

import json

import pytest

from models import CA, Certificate, db
from models.policy import ApprovalRequest, CertificatePolicy


def _json(client, method, url, payload):
    return getattr(client, method)(url, data=json.dumps(payload), content_type='application/json')


def _operator_client(app, create_user):
    user = create_user(role='operator')
    client = app.test_client()
    r = _json(client, 'post', '/api/v2/auth/login',
              {'username': user['username'], 'password': 'TestPass123!'})
    assert r.status_code == 200, r.data
    return client


def _approval_policy(app, ca_id, rules=None, name='fail-closed'):
    with app.app_context():
        pol = CertificatePolicy(name=f'{name}-{ca_id}', policy_type='issuance', ca_id=ca_id,
                                requires_approval=True, min_approvers=1,
                                is_active=True, priority=100)
        pol.set_rules(rules or {})
        db.session.add(pol)
        db.session.commit()
        return pol.id


def _cleanup(app, policy_id, cn):
    with app.app_context():
        for ap in ApprovalRequest.query.filter_by(policy_id=policy_id).all():
            db.session.delete(ap)
        for row in Certificate.query.filter(Certificate.subject.contains(f'CN={cn}')).all():
            db.session.delete(row)
        pol = db.session.get(CertificatePolicy, policy_id)
        if pol:
            db.session.delete(pol)
        db.session.commit()


class TestPolicyEvaluationFailsClosed:

    def test_malformed_san_cannot_skip_approval(self, app, create_ca, create_user):
        ca = create_ca(cn='Fail-closed approval CA')
        pid = _approval_policy(app, ca['id'], {'san_restrictions': {'dns_pattern': '.corp.example'}})
        operator = _operator_client(app, create_user)
        cn = 'web.corp.example'
        base = {'cn': cn, 'ca_id': ca['id'], 'san_dns': [cn], 'validity_days': 30}
        try:
            r = _json(operator, 'post', '/api/v2/certificates', base)
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data'].get('approval_required') is True
            for bad in (1, [123], {'x': 1}):
                r = _json(operator, 'post', '/api/v2/certificates', {**base, 'san': bad})
                assert r.status_code != 201, (bad, r.status_code, r.get_json())
                with app.app_context():
                    assert Certificate.query.filter(
                        Certificate.subject.contains(f'CN={cn}')).count() == 0, bad
        finally:
            _cleanup(app, pid, cn)


class TestFailedIssuanceKeepsApprovalReplayable:

    def test_offline_ca_at_approval_time(self, app, auth_client, create_ca, create_user):
        ca = create_ca(cn='Replayable approval CA')
        pid = _approval_policy(app, ca['id'], name='replayable')
        operator = _operator_client(app, create_user)
        cn = 'replay.example.test'
        try:
            r = _json(operator, 'post', '/api/v2/certificates',
                      {'cn': cn, 'ca_id': ca['id'], 'validity_days': 30})
            assert r.status_code == 200, r.get_json()
            approval_id = r.get_json()['data']['approval_id']

            with app.app_context():
                db.session.get(CA, ca['id']).offline = True
                db.session.commit()
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'go'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is False
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'pending', ap.status
                assert ap.certificate_id is None
                assert ap.get_approvals() == []

            with app.app_context():
                db.session.get(CA, ca['id']).offline = False
                db.session.commit()
            r = _json(auth_client, 'post', f'/api/v2/approvals/{approval_id}/approve', {'comment': 'again'})
            assert r.status_code == 200, r.get_json()
            assert r.get_json()['data']['certificate_issued'] is True
            with app.app_context():
                ap = db.session.get(ApprovalRequest, approval_id)
                assert ap.status == 'approved'
                assert ap.certificate_id is not None
        finally:
            _cleanup(app, pid, cn)
