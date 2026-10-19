"""Locking an account sends the security_alert e-mail, at both login doors."""
import json
import uuid

import pytest

from models import db, User
from models.email_notification import NotificationConfig
from models.sso import SSOProvider

PASSWORD = 'Locked-Passw0rd!'


@pytest.fixture
def sent(app, monkeypatch):
    """Security alerts enabled with one recipient; returns the e-mails sent."""
    import services.notification.events as events

    mails = []

    def _send_email(**kwargs):
        mails.append(kwargs)
        return True, 'sent'

    monkeypatch.setattr(events.EmailService, 'send_email', staticmethod(_send_email))
    with app.app_context():
        cfg = NotificationConfig.query.filter_by(type='security_alert').first()
        created = cfg is None
        if created:
            cfg = NotificationConfig(type='security_alert', recipients='[]')
            db.session.add(cfg)
        saved = (cfg.enabled, cfg.recipients, cfg.cooldown_hours)
        cfg.enabled, cfg.recipients, cfg.cooldown_hours = True, json.dumps(['sec@example.test']), 0
        db.session.commit()
    yield mails
    with app.app_context():
        cfg = NotificationConfig.query.filter_by(type='security_alert').first()
        if created:
            db.session.delete(cfg)
        else:
            cfg.enabled, cfg.recipients, cfg.cooldown_hours = saved
        db.session.commit()


@pytest.fixture(autouse=True)
def five_attempts(app):
    """Pin the lockout threshold: other files in the same database may change it."""
    from models import SystemConfig
    with app.app_context():
        row = SystemConfig.query.filter_by(key='max_login_attempts').first()
        saved = row.value if row else None
        if row is None:
            row = SystemConfig(key='max_login_attempts')
            db.session.add(row)
        row.value = '5'
        db.session.commit()
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='max_login_attempts').first()
        if saved is None:
            db.session.delete(row)
        else:
            row.value = saved
        db.session.commit()


@pytest.fixture
def user(app):
    username = f'lock{uuid.uuid4().hex[:8]}'
    with app.app_context():
        u = User(username=username, email=f'{username}@example.test', role='viewer')
        u.set_password(PASSWORD)
        db.session.add(u)
        db.session.commit()
    yield username
    with app.app_context():
        User.query.filter_by(username=username).delete()
        db.session.commit()


@pytest.fixture
def ldap_provider(app, monkeypatch):
    import api.v2.sso.ldap_routes as ldap_routes
    monkeypatch.setattr(ldap_routes, '_ldap_authenticate_user',
                        lambda provider, user, password: (None, 'Invalid credentials'))
    with app.app_context():
        provider = SSOProvider(
            name=f'lock-ldap-{uuid.uuid4().hex[:6]}', provider_type='ldap', enabled=True,
            ldap_server='ldap.example.test', ldap_port=389, ldap_base_dn='dc=example,dc=test',
            ldap_user_filter='(uid={username})', ldap_username_attr='uid',
        )
        db.session.add(provider)
        db.session.commit()
        provider_id = provider.id
    yield provider_id
    with app.app_context():
        db.session.delete(db.session.get(SSOProvider, provider_id))
        db.session.commit()


def _alerts_for(mails, username):
    return [m for m in mails if m['notification_type'] == 'security_alert'
            and m['resource_id'] == f'account_locked:{username}']


def test_password_lockout_sends_one_alert(client, sent, user):
    for _ in range(5):
        r = client.post('/api/v2/auth/login/password',
                        json={'username': user, 'password': 'wrong'})
        assert r.status_code == 401
    alerts = _alerts_for(sent, user)
    assert len(alerts) == 1
    assert alerts[0]['recipients'] == ['sec@example.test']
    # Further attempts hit the lock and do not re-alert.
    r = client.post('/api/v2/auth/login/password', json={'username': user, 'password': 'wrong'})
    assert r.status_code == 429
    assert len(_alerts_for(sent, user)) == 1


def test_no_alert_before_the_threshold(client, sent, user):
    for _ in range(4):
        client.post('/api/v2/auth/login/password', json={'username': user, 'password': 'wrong'})
    assert _alerts_for(sent, user) == []


def test_ldap_lockout_sends_one_alert(client, sent, user, ldap_provider):
    for _ in range(5):
        r = client.post('/api/v2/sso/ldap/login',
                        json={'username': user, 'password': 'wrong', 'provider_id': ldap_provider})
        assert r.status_code == 401
    assert len(_alerts_for(sent, user)) == 1
