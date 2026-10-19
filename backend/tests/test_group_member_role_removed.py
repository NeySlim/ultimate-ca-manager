"""A group member has no per-group role.

The API accepted `member`/`admin` per membership and stored it, but nothing
read it: managing a group always takes the global admin role. The field is no
longer accepted or returned, so nobody believes they made a group admin.
"""
import json
import uuid

from models import db
from models.group import GroupMember


def _post(client, url, body):
    return client.post(url, data=json.dumps(body), content_type='application/json')


def test_role_is_ignored_and_not_returned(app, auth_client, create_user):
    group = _post(auth_client, '/api/v2/groups', {'name': f'role-less-{uuid.uuid4().hex[:8]}'}).get_json()['data']
    user = create_user(username=f'grp_{uuid.uuid4().hex[:8]}')
    r = _post(auth_client, f"/api/v2/groups/{group['id']}/members", {'user_id': user['id'], 'role': 'admin'})
    assert r.status_code == 201, r.data
    assert 'role' not in r.get_json()['data']
    with app.app_context():
        member = GroupMember.query.filter_by(group_id=group['id'], user_id=user['id']).one()
        assert member.role != 'admin'
    listed = auth_client.get(f"/api/v2/groups/{group['id']}/members").get_json()['data']
    assert listed and all('role' not in m for m in listed)


def test_an_unknown_role_value_no_longer_matters(auth_client, create_user):
    group = _post(auth_client, '/api/v2/groups', {'name': f'role-less-{uuid.uuid4().hex[:8]}'}).get_json()['data']
    user = create_user(username=f'grp_{uuid.uuid4().hex[:8]}')
    r = _post(auth_client, f"/api/v2/groups/{group['id']}/members", {'user_id': user['id'], 'role': 'owner'})
    assert r.status_code == 201, r.data
