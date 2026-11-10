"""Shared fixtures of the protocol approval tests: a policy requiring
approval on one CA, and the approval routes."""
import contextlib
import json
from datetime import timedelta

from models import db
from models.policy import ApprovalRequest, CertificatePolicy
from utils.datetime_utils import utc_now


@contextlib.contextmanager
def approval_policy(app, ca_id, name, operations=None):
    """A policy requiring one approval for the requests of CA *ca_id*; it
    and its requests are removed afterwards."""
    with app.app_context():
        policy = CertificatePolicy(name=name, policy_type='issuance', ca_id=ca_id,
                                   requires_approval=True, min_approvers=1, is_active=True,
                                   priority=1, notify_on_violation=False)
        if operations is not None:
            policy.operations = json.dumps(list(operations))
        db.session.add(policy)
        db.session.commit()
        policy_id = policy.id
    try:
        yield policy_id
    finally:
        with app.app_context():
            ApprovalRequest.query.filter_by(policy_id=policy_id).delete()
            row = db.session.get(CertificatePolicy, policy_id)
            if row is not None:
                db.session.delete(row)
            db.session.commit()


def requests_of(app, policy_id, request_type=None):
    with app.app_context():
        query = ApprovalRequest.query.filter_by(policy_id=policy_id)
        if request_type:
            query = query.filter_by(request_type=request_type)
        return [(r.id, r.status, json.loads(r.request_data or '{}'), r.certificate_id)
                for r in query.order_by(ApprovalRequest.id).all()]


def approve(auth_client, approval_id):
    r = auth_client.post(f'/api/v2/approvals/{approval_id}/approve', json={'comment': 'ok'})
    assert r.status_code == 200, r.get_json()
    body = r.get_json()['data']
    assert body.get('certificate_issued') is True, body
    return body


def reject(auth_client, approval_id, comment='not this one'):
    r = auth_client.post(f'/api/v2/approvals/{approval_id}/reject', json={'comment': comment})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()['data']['status'] == 'rejected'


def expire(app, approval_id):
    """Push the request past its deadline and run the hourly expiry."""
    from services.approval_gate import expire_stale_requests
    with app.app_context():
        row = db.session.get(ApprovalRequest, approval_id)
        row.expires_at = utc_now() - timedelta(minutes=1)
        db.session.commit()
        assert expire_stale_requests() >= 1
        assert db.session.get(ApprovalRequest, approval_id).status == 'expired'
