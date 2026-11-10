"""Shared fixtures of the protocol approval tests: a policy requiring
approval on one CA, and the approval routes."""
import contextlib
import json
from datetime import timedelta

import pytest

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


def profile_of(cert):
    """What a direct and an approved issuance must agree on: key usage,
    extended key usage, basic constraints and the kinds of names."""
    from cryptography import x509

    def ext(cls):
        try:
            return cert.extensions.get_extension_for_class(cls).value
        except x509.ExtensionNotFound:
            return None
    ku = ext(x509.KeyUsage)
    eku = ext(x509.ExtendedKeyUsage)
    san = ext(x509.SubjectAlternativeName)
    bc = ext(x509.BasicConstraints)
    return {
        'ku': None if ku is None else tuple(
            getattr(ku, f, None) for f in ('digital_signature', 'key_encipherment', 'key_agreement',
                                           'content_commitment', 'data_encipherment',
                                           'key_cert_sign', 'crl_sign')),
        'eku': None if eku is None else sorted(o.dotted_string for o in eku),
        'san_types': None if san is None else sorted({type(n).__name__ for n in san}),
        'ca': None if bc is None else bc.ca,
        'extensions': sorted(e.oid.dotted_string for e in cert.extensions),
    }


def _referencing(table_name, column_name):
    """``(table, fk column)`` of every table pointing at *table_name.column_name*."""
    for table in db.metadata.sorted_tables:
        for fk in table.foreign_keys:
            if fk.column.table.name == table_name and fk.column.name == column_name:
                yield table, fk.parent


def _delete_with_dependents(model, keys_by_column):
    """Delete the rows of *model* whose columns hold the given keys, after
    the rows of other tables that point at them."""
    for column_name, keys in keys_by_column.items():
        if not keys:
            continue
        for table, column in _referencing(model.__tablename__, column_name):
            if table is not model.__table__:
                db.session.execute(table.delete().where(column.in_(keys)))
    ids = keys_by_column.get('id')
    if ids:
        db.session.execute(model.__table__.delete().where(model.__table__.c.id.in_(ids)))


@pytest.fixture(scope='module', autouse=True)
def made_rows_removed(app):
    """The CAs and certificates a test file makes are removed with it, so the
    shared tables stay as the file found them (conftest's leak check)."""
    from models import CA, Certificate
    with app.app_context():
        last_ca = db.session.query(db.func.max(CA.id)).scalar() or 0
        last_cert = db.session.query(db.func.max(Certificate.id)).scalar() or 0
    yield
    with app.app_context():
        db.session.rollback()
        cert_ids = [r[0] for r in db.session.query(Certificate.id).filter(Certificate.id > last_cert)]
        cas = db.session.query(CA.id, CA.refid).filter(CA.id > last_ca).all()
        _delete_with_dependents(Certificate, {'id': cert_ids})
        _delete_with_dependents(CA, {'id': [c[0] for c in cas], 'refid': [c[1] for c in cas]})
        db.session.commit()
