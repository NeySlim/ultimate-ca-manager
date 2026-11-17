"""An administrator's new password follows the password policy.

A hidden `admin_bypass_password_policy` setting, with no screen and no
documentation, let administrators skip the policy when present in the database.
"""
import json
import uuid

from models import SystemConfig, db


def test_the_former_bypass_setting_is_ignored(app, auth_client):
    name = f'bypass_admin_{uuid.uuid4().hex[:8]}'
    password = 'Tq7#vLm2pXw9'
    r = auth_client.post('/api/v2/users', data=json.dumps({
        'username': name, 'password': password, 'email': f'{name}@test.local', 'role': 'admin'}),
        content_type='application/json')
    assert r.status_code in (200, 201), r.data
    with app.app_context():
        db.session.add(SystemConfig(key='admin_bypass_password_policy', value='true'))
        db.session.commit()
    try:
        c = app.test_client()
        r = c.post('/api/v2/auth/login', data=json.dumps({'username': name, 'password': password}),
                   content_type='application/json')
        assert r.status_code == 200, r.data
        csrf = r.get_json()['data'].get('csrf_token')
        r = c.post('/api/v2/account/password', data=json.dumps({
            'current_password': password, 'new_password': 'abc'}),
            content_type='application/json', headers={'X-CSRF-Token': csrf} if csrf else {})
        assert r.status_code == 400, r.data
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key='admin_bypass_password_policy').delete()
            db.session.commit()
