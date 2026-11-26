"""Changing the profile e-mail of an account with a password asks for it (the address
receives the reset link), is audited, and tells the old address; a notice that cannot
be sent leaves the change in place."""
import json
import uuid

import pytest

import services.notification_service as notification_module
from models import AuditLog, User, db

pytestmark = pytest.mark.usefixtures('drop_new_users')

URL = '/api/v2/account/profile'
PASSWORD = 'TestPass123!'


def _patch(client, body):
    return client.patch(URL, data=json.dumps(body), content_type='application/json')


@pytest.fixture
def signed_in(app, create_user):
    made = []

    def _make(role='viewer'):
        username = f'mailchange_{role}_{uuid.uuid4().hex[:8]}'
        user = create_user(username=username, role=role, email=f'{username}@old.example')
        made.append(user)
        c = app.test_client()
        r = c.post('/api/v2/auth/login', data=json.dumps(
            {'username': username, 'password': PASSWORD}), content_type='application/json')
        assert r.status_code == 200, r.data
        return c, user['id'], f'{username}@old.example'
    return _make


@pytest.fixture
def notices(monkeypatch):
    sent = []

    def _send(to, subject, template, context):
        sent.append((to, subject, context.get('message', '')))
        return True
    monkeypatch.setattr(notification_module.NotificationService, 'send_email', staticmethod(_send))
    return sent


def _email(app, uid):
    with app.app_context():
        db.session.expire_all()
        return db.session.get(User, uid).email


@pytest.mark.parametrize('role', ['auditor', 'operator', 'admin'])
def test_without_the_password_the_email_stays(app, signed_in, notices, role):
    c, uid, old = signed_in(role)
    r = _patch(c, {'email': 'x@attacker.example'})
    assert r.status_code == 403, r.data
    assert r.get_json()['details']['reauth'] == 'password'
    r = _patch(c, {'email': 'x@attacker.example', 'current_password': 'wrong-one'})
    assert r.status_code == 403, r.data
    assert _email(app, uid) == old
    assert notices == []


@pytest.mark.parametrize('role', ['auditor', 'operator', 'admin'])
def test_with_the_password_it_changes_is_audited_and_told(app, signed_in, notices, role):
    c, uid, old = signed_in(role)
    new = old.replace('@old.example', '@new.example')
    r = _patch(c, {'email': new, 'current_password': PASSWORD})
    assert r.status_code == 200, r.data
    assert _email(app, uid) == new
    assert [(to, subject) for to, subject, _ in notices] == [(old, 'UCM - Account email changed')]
    assert new in notices[0][2]
    with app.app_context():
        row = AuditLog.query.filter_by(action='profile_email_change', resource_id=str(uid)).one()
        assert old in row.details and new in row.details


def test_the_same_email_and_other_fields_ask_nothing(app, signed_in, notices):
    c, uid, old = signed_in()
    r = _patch(c, {'email': old, 'full_name': 'Same Address'})
    assert r.status_code == 200, r.data
    assert notices == []
    with app.app_context():
        assert AuditLog.query.filter_by(action='profile_email_change', resource_id=str(uid)).count() == 0


def test_a_notice_that_fails_leaves_the_change(app, signed_in, monkeypatch):
    def _broken(to, subject, template, context):
        raise OSError('relay down')
    monkeypatch.setattr(notification_module.NotificationService, 'send_email', staticmethod(_broken))
    c, uid, _old = signed_in()
    new = _old.replace('@old.example', '@kept.example')
    r = _patch(c, {'email': new, 'current_password': PASSWORD})
    assert r.status_code == 200, r.data
    assert _email(app, uid) == new


def test_an_account_without_a_password_changes_it_without_one(app, signed_in, notices):
    from api.v2.sso.account_state import SSO_NO_PASSWORD
    c, uid, old = signed_in()
    with app.app_context():
        db.session.get(User, uid).password_hash = SSO_NO_PASSWORD
        db.session.commit()
    r = _patch(c, {'email': old.replace('@old.example', '@sso.example')})
    assert r.status_code == 200, r.data
    assert [to for to, _s, _m in notices] == [old]


def test_the_notice_leaves_the_request_and_a_failure_is_logged(app, signed_in, monkeypatch, caplog):
    """Outside tests the relay is reached from a thread: a slow relay never holds the reply."""
    import api.v2.account.profile as profile_module
    started = []

    class _Held:
        def __init__(self, target, name=None, daemon=None):
            self.target, self.daemon = target, daemon

        def start(self):
            started.append(self)
    calls = []

    def _broken(to, subject, template, context):
        calls.append(to)
        raise OSError('relay down')
    monkeypatch.setattr(profile_module.threading, 'Thread', _Held)
    monkeypatch.setattr(notification_module.NotificationService, 'send_email', staticmethod(_broken))
    monkeypatch.setitem(app.config, 'TESTING', False)
    c, uid, old = signed_in()
    r = _patch(c, {'email': old.replace('@old.example', '@late.example'), 'current_password': PASSWORD})
    assert r.status_code == 200, r.data
    assert calls == [] and len(started) == 1 and started[0].daemon
    with caplog.at_level('WARNING'):
        started[0].target()
    assert calls == [old]
    assert 'Email change notice' in caplog.text
