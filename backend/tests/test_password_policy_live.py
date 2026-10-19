"""A password policy change applies at once, in every worker.

The policy was cached per process and only dropped by a restore, so a saved
minimum length or character class had no effect until a restart.
"""
import json
import uuid

import pytest

from models import SystemConfig, db
from security.password_policy import validate_password

KEYS = ('min_password_length', 'password_require_special')


@pytest.fixture
def restore_policy(app):
    with app.app_context():
        saved = {k: (SystemConfig.query.filter_by(key=k).first() or SystemConfig(key=k, value=None)).value
                 for k in KEYS}
    yield
    with app.app_context():
        for k, v in saved.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None:
                if row:
                    db.session.delete(row)
            else:
                row.value = v
        db.session.commit()


def _set_row(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row is None:
        db.session.add(SystemConfig(key=key, value=value))
    else:
        row.value = value
    db.session.commit()


def test_a_change_written_by_another_worker_applies(app, restore_policy):
    with app.app_context():
        _set_row('min_password_length', '8')
        assert validate_password('Tq7#vLm2pXw9')[0]
        # Another worker saved a stricter policy: this one must see it.
        _set_row('min_password_length', '20')
        ok, errors = validate_password('Tq7#vLm2pXw9')
    assert not ok
    assert any(e['key'] == 'password_policy.minLength' for e in errors)


def test_the_settings_page_change_applies_to_user_creation(app, auth_client, restore_policy):
    def create(name, password):
        return auth_client.post('/api/v2/users', data=json.dumps({
            'username': name, 'password': password, 'email': f'{name}@test.local', 'role': 'viewer',
        }), content_type='application/json')

    r = auth_client.patch('/api/v2/settings/general', data=json.dumps({'min_password_length': 8}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    assert create(f'policy_live_a_{uuid.uuid4().hex[:8]}', 'Tq7#vLm2pXw9').status_code in (200, 201)

    r = auth_client.patch('/api/v2/settings/general', data=json.dumps({'min_password_length': 20}),
                          content_type='application/json')
    assert r.status_code == 200, r.data
    r = create(f'policy_live_b_{uuid.uuid4().hex[:8]}', 'Tq7#vLm2pXw9')
    assert r.status_code == 400, r.data
