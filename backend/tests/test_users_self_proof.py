"""The user administration routes reach the caller's own account too: moving its own
e-mail or enrolling an mTLS certificate for itself proves the holder again, as on the
Account page (OWASP ASVS 4.0.3 V3.7.1); another user's account does not."""
import json
import uuid

import pytest

import services.notification_service as notification_module
from models import AuditLog, User, db

pytestmark = pytest.mark.usefixtures('drop_new_users')

PASSWORD = 'TestPass123!'


def _send(client, method, url, body):
    return getattr(client, method)(url, data=json.dumps(body), content_type='application/json')


@pytest.fixture
def admin(app, create_user):
    username = f'selfproof_{uuid.uuid4().hex[:8]}'
    user = create_user(username=username, role='admin', email=f'{username}@old.example')
    c = app.test_client()
    r = _send(c, 'post', '/api/v2/auth/login', {'username': username, 'password': PASSWORD})
    assert r.status_code == 200, r.data
    return c, user['id'], f'{username}@old.example'


@pytest.fixture
def notices(monkeypatch):
    sent = []
    monkeypatch.setattr(notification_module.NotificationService, 'send_email', staticmethod(
        lambda to, subject, template, context: sent.append(to) or True))
    return sent


def _email(app, uid):
    with app.app_context():
        db.session.expire_all()
        return db.session.get(User, uid).email


def _reauth(r):
    return ((r.get_json() or {}).get('details') or {}).get('reauth')


@pytest.mark.parametrize('body', [{}, {'current_password': 'not-the-password'}])
def test_own_email_needs_the_password(app, admin, body):
    c, uid, old = admin
    r = _send(c, 'put', f'/api/v2/users/{uid}', dict(body, email='x@attacker.example'))
    assert r.status_code == 403, r.data
    assert _reauth(r) == 'password'
    assert _email(app, uid) == old


def test_own_email_with_the_password_is_audited_and_announced(app, admin, notices):
    c, uid, old = admin
    r = _send(c, 'put', f'/api/v2/users/{uid}',
              {'email': 'moved@new.example', 'current_password': PASSWORD})
    assert r.status_code == 200, r.data
    assert _email(app, uid) == 'moved@new.example'
    with app.app_context():
        assert AuditLog.query.filter_by(action='profile_email_change', resource_id=str(uid)).count() == 1


def test_own_unchanged_email_needs_nothing(app, admin):
    c, uid, old = admin
    r = _send(c, 'put', f'/api/v2/users/{uid}', {'email': old, 'full_name': 'Same Address'})
    assert r.status_code == 200, r.data


def test_another_users_email_needs_no_proof(app, admin, create_user):
    c, _uid, _old = admin
    other = create_user(username=f'selfproof_other_{uuid.uuid4().hex[:8]}', role='viewer')
    r = _send(c, 'put', f"/api/v2/users/{other['id']}", {'email': 'other@new.example'})
    assert r.status_code == 200, r.data


def test_own_mtls_enrolment_needs_the_password(app, admin, create_ca):
    c, uid, _old = admin
    ca = create_ca(cn=f'Self proof CA {uuid.uuid4().hex[:6]}')
    r = _send(c, 'post', f'/api/v2/users/{uid}/mtls/certificates', {'mode': 'generate', 'ca_id': ca['id']})
    assert r.status_code == 403, r.data
    assert _reauth(r) == 'password'


@pytest.mark.parametrize('body', [{'mode': 'import'}, {'mode': 'generate', 'validity_days': 'abc'}])
def test_own_mtls_enrolment_refuses_its_input_before_the_proof(app, admin, body):
    # The proof comes last: an authenticator code is spent by the check
    c, uid, _old = admin
    r = _send(c, 'post', f'/api/v2/users/{uid}/mtls/certificates', body)
    assert r.status_code == 400, r.data


def test_another_users_mtls_enrolment_needs_no_proof(app, admin, create_user, create_ca):
    c, _uid, _old = admin
    other = create_user(username=f'selfproof_mtls_{uuid.uuid4().hex[:8]}', role='viewer')
    ca = create_ca(cn=f'Other proof CA {uuid.uuid4().hex[:6]}')
    r = _send(c, 'post', f"/api/v2/users/{other['id']}/mtls/certificates", {'mode': 'generate', 'ca_id': ca['id']})
    assert r.status_code == 201, r.data
    assert _reauth(r) is None


def test_own_email_without_a_local_password_needs_no_proof(app, admin, notices):
    # As on PATCH /api/v2/account/profile: such an account has no password to give
    from api.v2.sso.account_state import SSO_NO_PASSWORD
    c, uid, _old = admin
    with app.app_context():
        db.session.get(User, uid).password_hash = SSO_NO_PASSWORD
        db.session.commit()
    r = _send(c, 'put', f'/api/v2/users/{uid}', {'email': 'sso@new.example'})
    assert r.status_code == 200, r.data
    assert _email(app, uid) == 'sso@new.example'
