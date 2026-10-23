"""A forced password change holds on the server, not only in the UI prompt.

The first-boot admin carries the documented default password: until it is
replaced, that session reaches nothing but the change itself (GHSA-wgv8-q932-f5px).
"""
from contextlib import contextmanager
from uuid import uuid4

import pytest

from models import User, db
from models.api_key import APIKey
from models.user import UserSession
from tests.conftest import assert_success
from utils.datetime_utils import utc_now
from websocket import socketio

_FIRST = 'FirstBoot-Pass-123!'
_NEW = 'Replaced-Pass-456!'


@pytest.fixture
def flagged_admin(app):
    """An admin account still holding the password it was created with."""
    username = f'fpc-{uuid4().hex[:8]}'
    with app.app_context():
        user = User(username=username, email=f'{username}@test.local', role='admin', active=True)
        user.set_password(_FIRST)
        user.force_password_change = True
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id, username
    with app.app_context():
        db.session.rollback()
        UserSession.query.filter_by(user_id=user_id).delete()
        APIKey.query.filter_by(user_id=user_id).delete()
        user = db.session.get(User, user_id)
        if user is not None:
            db.session.delete(user)
        db.session.commit()


def _login(app, username, password=_FIRST):
    client = app.test_client()
    r = client.post('/api/v2/auth/login', json={'username': username, 'password': password})
    return client, assert_success(r)


def _set_flag(app, user_id, value):
    with app.app_context():
        db.session.get(User, user_id).force_password_change = value
        db.session.commit()


def _refused(r):
    return r.status_code == 403 and (r.get_json() or {}).get('must_change_password') is True


@pytest.mark.parametrize('method,path,body', [
    ('get', '/api/v2/cas', None),
    ('get', '/api/v2/users', None),
    ('get', '/api/v2/settings/general', None),
    ('post', '/api/v2/account/apikeys', {'name': 'k', 'permissions': ['read:cas']}),
    ('post', '/api/v2/users', {'username': 'x', 'email': 'x@test.local', 'password': _NEW}),
])
def test_the_session_reaches_nothing_else(app, flagged_admin, method, path, body):
    _, username = flagged_admin
    client, data = _login(app, username)
    assert data['force_password_change'] is True
    r = getattr(client, method)(path, json=body) if body is not None else getattr(client, method)(path)
    assert _refused(r), (r.status_code, r.data)


@pytest.mark.parametrize('path', ['/api/v2/auth/verify', '/api/v2/users/password-policy'])
def test_what_the_change_prompt_needs_still_answers(app, flagged_admin, path):
    _, username = flagged_admin
    client, _ = _login(app, username)
    assert client.get(path).status_code == 200


def test_logout_still_answers(app, flagged_admin):
    _, username = flagged_admin
    client, _ = _login(app, username)
    assert client.post('/api/v2/auth/logout').status_code == 200


def test_changing_the_password_lifts_the_gate(app, flagged_admin):
    user_id, username = flagged_admin
    client, _ = _login(app, username)
    assert_success(client.post('/api/v2/account/password', json={'new_password': _NEW}))
    with app.app_context():
        assert db.session.get(User, user_id).force_password_change is False
    client, data = _login(app, username, _NEW)
    assert data['force_password_change'] is False
    assert client.get('/api/v2/cas').status_code == 200


def test_an_api_key_made_with_full_access_keeps_working(app, flagged_admin):
    """Keys are not gated: making one already needed a session past the change."""
    user_id, username = flagged_admin
    _set_flag(app, user_id, False)
    client, _ = _login(app, username)
    key = assert_success(client.post('/api/v2/account/apikeys', json={
        'name': 'fpc', 'permissions': ['read:cas']}), 201)['key']
    _set_flag(app, user_id, True)
    assert app.test_client().get('/api/v2/cas', headers={'X-API-Key': key}).status_code == 200


@contextmanager
def _socket(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        now = utc_now().isoformat()
        sess.update(user_id=user_id, login_time=now, last_activity=now)
    ws = socketio.test_client(app, flask_test_client=client)
    try:
        yield ws
    finally:
        if ws.is_connected():
            ws.disconnect()


def test_the_websocket_refuses_the_session(app, flagged_admin):
    user_id, _ = flagged_admin
    with _socket(app, user_id) as ws:
        assert not ws.is_connected()
    _set_flag(app, user_id, False)
    with _socket(app, user_id) as ws:
        assert ws.is_connected()


def test_a_forced_2fa_enrolment_comes_first(app, flagged_admin):
    """Both gates on one session: enrolment stays reachable, or neither could be met."""
    from auth.twofa_enforcement import ENROLL_SESSION_KEY
    _, username = flagged_admin
    client, _ = _login(app, username)
    with client.session_transaction() as sess:
        sess[ENROLL_SESSION_KEY] = True
    r = client.post('/api/v2/account/2fa/enable')
    assert not _refused(r) and r.status_code < 400, (r.status_code, r.data)
