"""Each listed request tells the signed-in user which decision the server would take from them,
by the rules of approve and reject: the approver group, one's own request, one vote each."""
import json
from datetime import timedelta

import pytest

from models import db
from models.group import Group, GroupMember
from models.policy import ApprovalRequest, CertificatePolicy
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.usefixtures('drop_new_users')


def _login(app, user):
    client = app.test_client()
    r = client.post('/api/v2/auth/login', data=json.dumps(
        {'username': user['username'], 'password': 'TestPass123!'}), content_type='application/json')
    assert r.status_code == 200, r.data
    return client


@pytest.fixture
def setting(app, create_user):
    alice, bob, carol = (create_user(role='operator') for _ in range(3))
    with app.app_context():
        group = Group(name=f'approvers-{alice["id"]}')
        db.session.add(group)
        db.session.flush()
        db.session.add(GroupMember(group_id=group.id, user_id=bob['id']))
        db.session.add(GroupMember(group_id=group.id, user_id=alice['id']))
        policy = CertificatePolicy(name=f'rights-{alice["id"]}', policy_type='issuance', requires_approval=True,
                                   min_approvers=2, is_active=True, priority=100, approval_group_id=group.id)
        db.session.add(policy)
        db.session.flush()
        req = ApprovalRequest(request_type='certificate', policy_id=policy.id, requester_id=alice['id'],
                              status='pending', required_approvals=2, expires_at=utc_now() + timedelta(days=1))
        db.session.add(req)
        db.session.commit()
        ids = {'req': req.id, 'policy': policy.id, 'group': group.id}
    yield {'alice': alice, 'bob': bob, 'carol': carol, **ids}
    with app.app_context():
        db.session.query(ApprovalRequest).filter_by(id=ids['req']).delete()
        db.session.query(CertificatePolicy).filter_by(id=ids['policy']).delete()
        db.session.query(GroupMember).filter_by(group_id=ids['group']).delete()
        db.session.query(Group).filter_by(id=ids['group']).delete()
        db.session.commit()


def _rights(client, req_id):
    r = client.get(f'/api/v2/approvals/{req_id}')
    assert r.status_code == 200, r.data
    one = r.get_json()['data']['decision_rights']
    r = client.get('/api/v2/approvals?status=pending')
    listed = next(x for x in r.get_json()['data'] if x['id'] == req_id)['decision_rights']
    assert listed == one
    return one


def test_the_rights_say_what_the_server_refuses(app, setting):
    req = setting['req']
    alice, bob, carol = (_login(app, setting[k]) for k in ('alice', 'bob', 'carol'))
    # The requester may withdraw (reject) but not approve
    assert _rights(alice, req) == {'approve': 'own_request', 'reject': None}
    assert alice.post(f'/api/v2/approvals/{req}/approve', json={}).status_code == 403
    # Outside the approver group, neither
    assert _rights(carol, req) == {'approve': 'not_in_group', 'reject': 'not_in_group'}
    assert carol.post(f'/api/v2/approvals/{req}/reject', json={'comment': 'no'}).status_code == 403
    # A member decides once
    assert _rights(bob, req) == {'approve': None, 'reject': None}
    assert bob.post(f'/api/v2/approvals/{req}/approve', json={}).status_code == 200
    assert _rights(bob, req) == {'approve': 'already_voted', 'reject': 'already_voted'}
    assert bob.post(f'/api/v2/approvals/{req}/reject', json={'comment': 'no'}).status_code == 409


def test_an_admin_passes_the_group_gate(app, auth_client, setting):
    assert _rights(auth_client, setting['req']) == {'approve': None, 'reject': None}
