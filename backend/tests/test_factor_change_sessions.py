"""A second factor set up, changed or removed closes the account's other sessions.

OWASP ASVS 5.0 §7.4.3: other sessions end after a change of any authentication
factor. Each operation gets the password change's treatment: the session making it
stays, every other one of the account gets 401, on the file store, on the SQL store
(SQLite) and on the SQL store shared by two nodes on PostgreSQL (HA). The audit
entry says how many sessions were closed.
"""
import json
import os
import uuid

import pyotp
import pytest

from models import AuditLog, User, db
from models.webauthn import WebAuthnCredential
from tests.test_webauthn_second_factor import SoftKey

PG_URL = os.getenv('UCM_TEST_APP_PG_URL') or os.getenv('UCM_TEST_PG_URL')
PASSWORD = 'Fact0r-Change-Sessions!'


@pytest.fixture(autouse=True)
def _drop_session_table_from_metadata():
    """The SQL store registers flask_sessions on the shared metadata; never leak it."""
    yield
    t = db.metadata.tables.get('flask_sessions')
    if t is not None:
        db.metadata.remove(t)


def _sql_store_app(monkeypatch, url, database_type):
    from config.settings import TestingConfig
    from utils.db_url import sqlalchemy_url
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', sqlalchemy_url(url))
    monkeypatch.setattr(TestingConfig, 'DATABASE_TYPE', database_type)
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
    from app import create_app
    return create_app('testing')


def _dispose(*applications):
    for application in applications:
        with application.app_context():
            db.session.remove()
            db.engine.dispose()


@pytest.fixture(params=[
    'files',
    'sql-sqlite',
    pytest.param('sql-postgresql', marks=[
        pytest.mark.postgres,
        pytest.mark.skipif(not PG_URL, reason='no PostgreSQL URL for the two-node session test')]),
])
def nodes(request, app, monkeypatch, tmp_path):
    """(node of the first session, node of the second): one store behind both."""
    from tests import pg_app_harness
    if request.param == 'files':
        yield app, app
        return
    if request.param == 'sql-sqlite':
        if pg_app_harness.ENABLED:
            pytest.skip('file-database store, not meaningful in PostgreSQL mode')
        url = f'sqlite:///{tmp_path / "factor-sessions.db"}'
        node = _sql_store_app(monkeypatch, url, 'sqlite')
        try:
            yield node, node
        finally:
            _dispose(node)
        return
    import psycopg
    schema = f'ucm_factor_{uuid.uuid4().hex[:8]}'
    admin = psycopg.connect(PG_URL, autocommit=True)
    admin.execute(f'CREATE SCHEMA "{schema}"')
    sep = '&' if '?' in PG_URL else '?'
    url = f'{PG_URL}{sep}options=-csearch_path%3D{schema}'
    monkeypatch.setenv('DATABASE_URL', url)
    # The shared-suite wrapper would give each application its own schema
    pg_app_harness._creating_session_app.append(True)
    created = []
    try:
        created.append(_sql_store_app(monkeypatch, url, 'postgresql'))
        created.append(_sql_store_app(monkeypatch, url, 'postgresql'))
        yield created[0], created[1]
    finally:
        pg_app_harness._creating_session_app.pop()
        _dispose(*created)
        admin.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        admin.close()


def _make_user(application, totp=False, key=None, choice=False, key_enabled=True):
    with application.app_context():
        user = User(username=f'factor-{uuid.uuid4().hex[:8]}', role='operator',
                    email=f'{uuid.uuid4().hex[:8]}@example.test', webauthn_2fa=choice)
        user.set_password(PASSWORD)
        if totp:
            user.totp_secret = pyotp.random_base32()
            user.totp_confirmed = True
        db.session.add(user)
        db.session.flush()
        key_id = None
        if key:
            credential = WebAuthnCredential(user_id=user.id, credential_id=key.credential_id,
                                            public_key=key.cose, sign_count=0, name='soft',
                                            enabled=key_enabled)
            db.session.add(credential)
            db.session.flush()
            key_id = credential.id
        db.session.commit()
        info = {'id': user.id, 'username': user.username, 'secret': user.totp_secret,
                'key': key, 'key_id': key_id}
        db.session.remove()
        return info


def _cleanup(application, user):
    from models.second_factor_failure import SecondFactorFailure
    from models.webauthn import WebAuthnChallenge
    with application.app_context():
        SecondFactorFailure.query.filter_by(target=str(user['id'])).delete()
        WebAuthnChallenge.query.filter_by(user_id=user['id']).delete()
        WebAuthnCredential.query.filter_by(user_id=user['id']).delete()
        row = db.session.get(User, user['id'])
        if row:
            db.session.delete(row)
        db.session.commit()
        db.session.remove()


def _post(c, url, body=None):
    return c.post(url, data=json.dumps(body or {}), content_type='application/json')


def _fresh_steps(application, user):
    """Each login and operation below uses the current TOTP code once."""
    with application.app_context():
        db.session.execute(db.update(User).where(User.id == user['id']).values(totp_last_step=None))
        db.session.commit()
        db.session.remove()


def _code(application, user):
    _fresh_steps(application, user)
    return pyotp.TOTP(user['secret']).now()


def _open_session(application, user):
    c = application.test_client()
    r = _post(c, '/api/v2/auth/login/password', {'username': user['username'], 'password': PASSWORD})
    assert r.status_code == 200, r.data
    methods = (r.get_json().get('data') or {}).get('methods') or []
    if 'totp' in methods:
        r = _post(c, '/api/v2/auth/login/2fa', {'code': _code(application, user)})
    elif 'webauthn' in methods:
        r = _post(c, '/api/v2/auth/login/2fa/webauthn/options', {})
        challenge = r.get_json()['data']['options']['challenge']
        r = _post(c, '/api/v2/auth/login/2fa/webauthn/verify',
                  {'response': user['key'].assert_(challenge)})
    assert r.status_code == 200, r.data
    assert _signed_in(c)
    return c


def _signed_in(c):
    return c.get('/api/v2/account/profile').status_code == 200


def _confirm_totp(application, c, user):
    r = _post(c, '/api/v2/account/2fa/enable')
    assert r.status_code == 200, r.data
    user['secret'] = r.get_json()['data']['secret']
    return _post(c, '/api/v2/account/2fa/confirm', {'code': pyotp.TOTP(user['secret']).now()})


def _disable_totp(application, c, user):
    return _post(c, '/api/v2/account/2fa/disable', {'code': _code(application, user)})


def _regenerate_codes(application, c, user):
    return _post(c, '/api/v2/account/2fa/recovery-codes/regenerate', {'code': _code(application, user)})


def _add_key(application, c, user):
    r = _post(c, '/api/v2/webauthn/register/options', {})
    assert r.status_code == 200, r.data
    return _post(c, '/api/v2/webauthn/register/verify',
                 {'credential': SoftKey().attest(r.get_json()['data']['challenge']), 'name': 'new'})


def _delete_key(application, c, user):
    return c.delete(f"/api/v2/webauthn/credentials/{user['key_id']}")


def _toggle_key(enabled):
    def _toggle(application, c, user):
        return _post(c, f"/api/v2/webauthn/credentials/{user['key_id']}/toggle", {'enabled': enabled})
    return _toggle


def _key_choice(enabled):
    def _put(application, c, user):
        body = {'enabled': enabled} if enabled else {'enabled': False, 'password': PASSWORD}
        return c.put('/api/v2/account/2fa/webauthn', json=body)
    return _put


# operation: (user it starts from, request made in the first session, audit action)
OPERATIONS = {
    'confirm-totp': ({}, _confirm_totp, 'mfa_enable'),
    'disable-totp': ({'totp': True}, _disable_totp, 'mfa_disable'),
    'regenerate-recovery-codes': ({'totp': True}, _regenerate_codes, 'mfa_recovery_regenerate'),
    'add-key': ({}, _add_key, 'webauthn_register'),
    'delete-key': ({'key': True}, _delete_key, 'webauthn_delete'),
    'disable-key': ({'key': True}, _toggle_key(False), 'webauthn_toggle'),
    'enable-key': ({'key': True, 'key_enabled': False}, _toggle_key(True), 'webauthn_toggle'),
    'key-second-factor-on': ({'key': True}, _key_choice(True), 'mfa_webauthn_enable'),
    'key-second-factor-off': ({'key': True, 'choice': True}, _key_choice(False),
                              'mfa_webauthn_disable'),
}


def _audit_details(application, action, user):
    with application.app_context():
        row = (AuditLog.query.filter_by(action=action, resource_name=user['username'])
               .order_by(AuditLog.id.desc()).first())
        if row is None:
            row = (AuditLog.query.filter_by(action=action, username=user['username'])
                   .order_by(AuditLog.id.desc()).first())
        details = row.details if row else None
        db.session.remove()
        return details


@pytest.mark.parametrize('operation', sorted(OPERATIONS))
def test_the_other_sessions_close_and_this_one_stays(nodes, operation):
    first_node, second_node = nodes
    start, call, action = OPERATIONS[operation]
    start = dict(start)
    if start.pop('key', False):
        start['key'] = SoftKey()
    user = _make_user(first_node, **start)
    try:
        other = _open_session(second_node, user)
        this = _open_session(first_node, user)
        r = call(first_node, this, user)
        assert r.status_code == 200, r.data
        assert r.get_json()['meta']['other_sessions_closed'] == 1
        assert _signed_in(this)
        assert not _signed_in(other)
        assert _signed_in(this)
        assert '1 other session closed' in (_audit_details(first_node, action, user) or '')
    finally:
        _cleanup(first_node, user)


@pytest.mark.parametrize('method', ['delete', 'patch'])
def test_an_administrator_changing_a_key_closes_the_holders_sessions(app, auth_client, method):
    """The holder loses or regains a factor: their sessions close, the administrator's stays."""
    user = _make_user(app, key=SoftKey())
    try:
        holder = _open_session(app, user)
        url = f"/api/v2/users/{user['id']}/webauthn/{user['key_id']}"
        r = auth_client.delete(url) if method == 'delete' else auth_client.patch(
            url, json={'enabled': False})
        assert r.status_code == 200, r.data
        assert r.get_json()['meta']['other_sessions_closed'] == 1
        assert not _signed_in(holder)
        assert auth_client._client.get('/api/v2/account/profile').status_code == 200
    finally:
        _cleanup(app, user)


def test_sessions_closed_earlier_are_not_counted_again(nodes):
    first_node, second_node = nodes
    user = _make_user(first_node, key=SoftKey())
    try:
        stale = _open_session(second_node, user)
        this = _open_session(first_node, user)
        # The stale session makes no request: it stays in the store, at its old version
        assert _post(this, '/api/v2/account/sessions/revoke-all').status_code == 200
        other = _open_session(second_node, user)
        r = _toggle_key(False)(first_node, this, user)
        assert r.status_code == 200, r.data
        assert r.get_json()['meta']['other_sessions_closed'] == 1
        assert not _signed_in(other) and not _signed_in(stale) and _signed_in(this)
    finally:
        _cleanup(first_node, user)


def _admin_key(method):
    def _call(application, c, user, admin):
        url = f"/api/v2/users/{user['id']}/webauthn/{user['key_id']}"
        return admin.delete(url) if method == 'delete' else admin.patch(url, json={'enabled': False})
    return _call


def _own(call):
    def _call(application, c, user, admin):
        return call(application, c, user)
    return _call


def _key_state(application, user):
    """(the account's keys as (id, enabled), session_version)."""
    with application.app_context():
        keys = sorted((k.id, k.enabled) for k in
                      WebAuthnCredential.query.filter_by(user_id=user['id']).all())
        version = db.session.get(User, user['id']).session_version or 0
        db.session.remove()
        return keys, version


class _FailingCommit:
    """Makes the first commit fail that carries a key change ('key') or the
    session_version bump ('bump'), as a database error would."""

    def __init__(self, target):
        self.target = target
        self.failed = False

    def on_execute(self, state):
        if state.is_update and 'session_version' in str(state.statement):
            state.session.info['bumped'] = True

    def on_flush(self, session, _context):
        if any(isinstance(o, WebAuthnCredential)
               for o in list(session.new) + list(session.dirty) + list(session.deleted)):
            session.info['key_changed'] = True

    def on_commit(self, session):
        self.on_flush(session, None)  # what the commit's own flush is about to write
        hit = session.info.pop('bumped' if self.target == 'bump' else 'key_changed', False)
        session.info.pop('bumped', None)
        session.info.pop('key_changed', None)
        if hit and not self.failed:
            self.failed = True
            raise RuntimeError('commit refused by the test')

    def on_end(self, session):
        session.info.pop('bumped', None)
        session.info.pop('key_changed', None)


# key operation: (user it starts from, request)
KEY_CHANGES = {
    'add-key': ({}, _own(_add_key)),
    'delete-key': ({}, _own(_delete_key)),
    'disable-key': ({}, _own(_toggle_key(False))),
    'enable-key': ({'key_enabled': False}, _own(_toggle_key(True))),
    'admin-delete-key': ({}, _admin_key('delete')),
    'admin-disable-key': ({}, _admin_key('patch')),
}


@pytest.mark.parametrize('target', ['key', 'bump'])
@pytest.mark.parametrize('operation', sorted(KEY_CHANGES))
def test_a_key_change_and_the_session_closure_commit_together(app, auth_client, operation,
                                                              target):
    """Whichever of the two writes fails, neither stays: no key changed with sessions open."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    start, call = KEY_CHANGES[operation]
    user = _make_user(app, key=SoftKey(), **start)
    before = _key_state(app, user)
    failing = _FailingCommit(target)
    listeners = [('do_orm_execute', failing.on_execute), ('after_flush', failing.on_flush),
                 ('before_commit', failing.on_commit), ('after_commit', failing.on_end),
                 ('after_rollback', failing.on_end)]
    try:
        other = _open_session(app, user)
        this = _open_session(app, user)
        before = _key_state(app, user)
        for name, fn in listeners:
            event.listen(Session, name, fn)
        try:
            r = call(app, this, user, auth_client)
        finally:
            for name, fn in listeners:
                event.remove(Session, name, fn)
        assert failing.failed
        assert r.status_code != 200, r.data
        assert _key_state(app, user) == before
        assert _signed_in(other)
    finally:
        _cleanup(app, user)


@pytest.mark.parametrize('operation', sorted(KEY_CHANGES))
def test_a_key_change_moves_the_key_and_the_session_version(app, auth_client, operation):
    start, call = KEY_CHANGES[operation]
    user = _make_user(app, key=SoftKey(), **start)
    try:
        this = _open_session(app, user)
        keys, version = _key_state(app, user)
        r = call(app, this, user, auth_client)
        assert r.status_code == 200, r.data
        new_keys, new_version = _key_state(app, user)
        assert new_keys != keys and new_version == version + 1
    finally:
        _cleanup(app, user)
