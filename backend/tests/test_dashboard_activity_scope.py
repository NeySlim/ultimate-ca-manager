"""The dashboard activity feed: the whole audit trail needs read:audit, as /audit/logs does.

Without it a user sees their own events only, never another account's actions
nor the names typed at a failed login.
"""
import json
import uuid

import pytest

from models import AuditLog, User, db

PASSWORD = 'Activ1ty-Scope-Pass!'


@pytest.fixture
def account(app):
    created = []

    def _make(role):
        name = f'act-{role}-{uuid.uuid4().hex[:6]}'
        with app.app_context():
            user = User(username=name, email=f'{name}@example.test', role=role)
            user.set_password(PASSWORD)
            db.session.add(user)
            db.session.commit()
        created.append(name)
        c = app.test_client()
        r = c.post('/api/v2/auth/login/password', data=json.dumps({'username': name, 'password': PASSWORD}),
                   content_type='application/json')
        assert r.status_code == 200, r.data
        return name, c

    yield _make
    with app.app_context():
        User.query.filter(User.username.in_(created)).delete(synchronize_session=False)
        db.session.commit()


@pytest.fixture
def typed_name(app):
    """A failed login whose typed name is someone's password."""
    typed = f'MyS3cret-{uuid.uuid4().hex[:8]}'
    with app.app_context():
        db.session.add(AuditLog(username=typed, action='login_failure', resource_type='user',
                                details=f'Login failed for username: {typed}', success=False))
        db.session.commit()
    yield typed
    with app.app_context():
        AuditLog.query.filter_by(username=typed).delete()
        db.session.commit()


def _feed(c):
    r = c.get('/api/v2/dashboard/activity?limit=100')
    assert r.status_code == 200, r.data
    return r.get_json()['data']['activity']


def test_without_read_audit_only_own_events(account, typed_name):
    name, viewer = account('viewer')
    feed = _feed(viewer)
    assert feed, 'the viewer sees its own login'
    assert {row['user'] for row in feed} == {name}
    assert typed_name not in json.dumps(feed)


def test_with_read_audit_the_whole_trail(account, typed_name):
    _name, auditor = account('auditor')
    assert typed_name in json.dumps(_feed(auditor))
