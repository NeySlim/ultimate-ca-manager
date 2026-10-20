"""Revoking or deleting a user certificate needs ownership or a privileged role.

A caller holding write/delete:user_certificates without being admin, operator
or auditor reaches only their own enrolments; anything else answers 404, the
same as a missing id, before any approval policy is evaluated.
"""
import json
import uuid

import pytest

from models import Certificate, User, db
from models.auth_certificate import AuthCertificate
from models.policy import ApprovalRequest, CertificatePolicy

BASE = '/api/v2/user-certificates'
PERMS = ['read:user_certificates', 'write:user_certificates', 'delete:user_certificates']


def _login(app, username):
    client = app.test_client()
    r = client.post('/api/v2/auth/login',
                    data=json.dumps({'username': username, 'password': 'TestPass123!'}),
                    content_type='application/json')
    assert r.status_code == 200, r.data
    return client


def _custom_user(app, auth_client, create_user, username):
    """A viewer promoted by a custom role carrying the three permissions."""
    r = auth_client.post('/api/v2/rbac/roles', content_type='application/json',
                         data=json.dumps({'name': f'ownership-{username}', 'permissions': PERMS}))
    assert r.status_code == 200, r.data
    role_id = json.loads(r.data)['data']['id']
    user = create_user(username=username, role='viewer')
    r = auth_client.put(f'/api/v2/users/{user["id"]}', content_type='application/json',
                        data=json.dumps({'custom_role_id': role_id}))
    assert r.status_code == 200, r.data
    return user, _login(app, username)


def _enrol(app, create_cert, user_id, label, ca_id=None):
    kwargs = {'ca_id': ca_id} if ca_id else {}
    cert = create_cert(cn=f'{label}.example', **kwargs)
    with app.app_context():
        issued = db.session.get(Certificate, cert['id'])
        row = AuthCertificate(user_id=user_id, cert_serial=issued.serial_number,
                              cert_subject=issued.subject or f'CN={label}.example',
                              cert_issuer=issued.issuer, cert_fingerprint='',
                              name=label, enabled=True)
        db.session.add(row)
        db.session.commit()
        return row.id, issued.id


def _exists(app, enrolment_id):
    with app.app_context():
        db.session.expire_all()
        return db.session.get(AuthCertificate, enrolment_id) is not None


def _revoked(app, cert_id):
    with app.app_context():
        db.session.expire_all()
        return bool(db.session.get(Certificate, cert_id).revoked)


def _body(response):
    return {k: v for k, v in response.get_json().items() if k != 'instance'}


def _post_revoke(client, enrolment_id):
    return client.post(f'{BASE}/{enrolment_id}/revoke', data=json.dumps({}),
                       content_type='application/json')


@pytest.fixture
def actors(app, auth_client, create_user):
    n = uuid.uuid4().hex[:8]
    a, client_a = _custom_user(app, auth_client, create_user, f'own_a_{n}')
    b, client_b = _custom_user(app, auth_client, create_user, f'own_b_{n}')
    return a, client_a, b, client_b


class TestRevoke:
    def test_stranger_gets_404_and_nothing_is_revoked(self, app, create_cert, actors):
        a, _ca, _b, client_b = actors
        eid, cid = _enrol(app, create_cert, a['id'], 'rev-stranger')
        r = _post_revoke(client_b, eid)
        assert r.status_code == 404
        assert not _revoked(app, cid)

    def test_missing_and_foreign_answer_identically(self, app, create_cert, actors):
        a, _ca, _b, client_b = actors
        eid, _ = _enrol(app, create_cert, a['id'], 'rev-same')
        foreign = _post_revoke(client_b, eid)
        missing = _post_revoke(client_b, 987654)
        assert foreign.status_code == missing.status_code == 404
        assert _body(foreign) == _body(missing)

    def test_owner_revokes_own(self, app, create_cert, actors):
        a, client_a, _b, _cb = actors
        eid, cid = _enrol(app, create_cert, a['id'], 'rev-owner')
        r = _post_revoke(client_a, eid)
        assert r.status_code == 200, r.data
        assert _revoked(app, cid)

    def test_operator_revokes_someone_elses(self, app, create_user, create_cert, actors):
        a, *_ = actors
        name = f'own_op_{uuid.uuid4().hex[:8]}'
        create_user(username=name, role='operator')
        op = _login(app, name)
        eid, cid = _enrol(app, create_cert, a['id'], 'rev-operator')
        assert _post_revoke(op, eid).status_code == 200
        assert _revoked(app, cid)

    def test_approval_policy_not_evaluated_for_stranger(self, app, create_ca, create_cert, actors):
        a, client_a, _b, client_b = actors
        ca = create_ca(cn='Ownership Policy CA')
        with app.app_context():
            pol = CertificatePolicy(name='ownership-rev-policy', ca_id=ca['id'],
                                    requires_approval=True, min_approvers=1,
                                    is_active=True, priority=100)
            pol.set_rules({})
            pol.set_operations(['revocation'])
            db.session.add(pol)
            db.session.commit()
            pid = pol.id
        try:
            eid, cid = _enrol(app, create_cert, a['id'], 'rev-policy', ca_id=ca['id'])
            r = _post_revoke(client_b, eid)
            assert r.status_code == 404
            assert 'approval' not in r.get_data(as_text=True).lower()
            with app.app_context():
                assert ApprovalRequest.query.filter_by(policy_id=pid).count() == 0
            # The owner, in contrast, is routed to approval
            r = _post_revoke(client_a, eid)
            assert r.status_code == 200
            assert 'approval_id' in r.get_json()['data']
        finally:
            with app.app_context():
                for ap in ApprovalRequest.query.filter_by(policy_id=pid).all():
                    db.session.delete(ap)
                db.session.delete(db.session.get(CertificatePolicy, pid))
                db.session.commit()


class TestDelete:
    def test_stranger_gets_404_and_row_survives(self, app, create_cert, actors):
        a, _ca, _b, client_b = actors
        eid, _ = _enrol(app, create_cert, a['id'], 'del-stranger')
        assert client_b.delete(f'{BASE}/{eid}').status_code == 404
        assert _exists(app, eid)

    def test_missing_and_foreign_answer_identically(self, app, create_cert, actors):
        a, _ca, _b, client_b = actors
        eid, _ = _enrol(app, create_cert, a['id'], 'del-same')
        foreign = client_b.delete(f'{BASE}/{eid}')
        missing = client_b.delete(f'{BASE}/987654')
        assert foreign.status_code == missing.status_code == 404
        assert _body(foreign) == _body(missing)

    def test_owner_deletes_own(self, app, create_cert, actors):
        a, client_a, _b, _cb = actors
        eid, _ = _enrol(app, create_cert, a['id'], 'del-owner')
        assert client_a.delete(f'{BASE}/{eid}').status_code in (200, 204)
        assert not _exists(app, eid)

    def test_admin_deletes_someone_elses(self, app, auth_client, create_cert, actors):
        a, *_ = actors
        eid, _ = _enrol(app, create_cert, a['id'], 'del-admin')
        assert auth_client.delete(f'{BASE}/{eid}').status_code in (200, 204)
        assert not _exists(app, eid)

    def test_approval_conflict_not_revealed_to_stranger(self, app, create_ca, create_cert, actors):
        a, _ca, _b, client_b = actors
        ca = create_ca(cn='Ownership Delete Policy CA')
        with app.app_context():
            pol = CertificatePolicy(name='ownership-del-policy', ca_id=ca['id'],
                                    requires_approval=True, min_approvers=1,
                                    is_active=True, priority=100)
            pol.set_rules({})
            pol.set_operations(['revocation'])
            db.session.add(pol)
            db.session.commit()
            pid = pol.id
        try:
            eid, _ = _enrol(app, create_cert, a['id'], 'del-policy', ca_id=ca['id'])
            assert client_b.delete(f'{BASE}/{eid}').status_code == 404
            assert _exists(app, eid)
        finally:
            with app.app_context():
                db.session.delete(db.session.get(CertificatePolicy, pid))
                db.session.commit()
