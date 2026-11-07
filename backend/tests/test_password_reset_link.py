"""The reset link in the e-mail points at the configured public origin, never at
localhost nor at the Host header of the (unauthenticated) request."""
import pytest

from models import db, SystemConfig, User


@pytest.fixture
def mailbox(app, monkeypatch):
    from api.v2 import auth as auth_api
    from services.notification_service import NotificationService
    sent = []
    monkeypatch.setattr(auth_api, '_is_email_configured', lambda: True)
    monkeypatch.setattr(NotificationService, 'send_email',
                        staticmethod(lambda **kw: sent.append(kw) or True))
    with app.app_context():
        User.query.filter_by(username='reset-link-user').delete()
        u = User(username='reset-link-user', email='reset-link@example.test', role='viewer',
                 active=True, full_name='R')
        u.set_password('Unused-Passw0rd!')
        db.session.add(u)
        db.session.commit()
    yield sent
    with app.app_context():
        User.query.filter_by(username='reset-link-user').delete()
        SystemConfig.query.filter_by(key='base_url').delete()
        db.session.commit()


def _base_url(app, value):
    with app.app_context():
        SystemConfig.query.filter_by(key='base_url').delete()
        if value:
            db.session.add(SystemConfig(key='base_url', value=value))
        db.session.commit()


def _ask(app, host='ucm.example.test'):
    client = app.test_client()
    return client.post('/api/v2/auth/forgot-password', json={'email': 'reset-link@example.test'},
                       base_url=f'https://{host}')


def test_link_uses_the_configured_base_url_not_the_request_host(app, mailbox):
    _base_url(app, 'https://pki.example.test:443')
    r = _ask(app, host='attacker.example')
    assert r.status_code == 200
    assert len(mailbox) == 1
    url = mailbox[0]['context']['reset_url']
    assert url.startswith('https://pki.example.test/reset-password?token='), url


def test_without_any_public_origin_the_reset_is_refused(app, mailbox, monkeypatch):
    from api.v2 import auth as auth_api
    _base_url(app, None)
    monkeypatch.setattr(auth_api, 'get_admin_canonical_origin', lambda: None)
    r = _ask(app)
    assert r.status_code == 503
    assert 'Base URL' in r.get_json()['message']
    assert mailbox == []
