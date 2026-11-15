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


@pytest.mark.parametrize('expired', ['inactivity', 'max-lifetime'])
def test_sessions_the_application_ended_are_not_counted(nodes, expired):
    """A session past its inactivity timeout or its maximum lifetime is already over,
    even while the store still keeps it: it is not one of the sessions closed."""
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    first_node, second_node = nodes
    user = _make_user(first_node, key=SoftKey())
    try:
        old = _open_session(second_node, user)
        with old.session_transaction() as s:
            key = 'last_activity' if expired == 'inactivity' else 'login_time'
            s[key] = (utc_now() - timedelta(hours=9 if expired == 'inactivity' else 25)).isoformat()
        live = _open_session(second_node, user)
        this = _open_session(first_node, user)
        r = _toggle_key(False)(first_node, this, user)
        assert r.status_code == 200, r.data
        assert r.get_json()['meta']['other_sessions_closed'] == 1
        assert not _signed_in(live) and not _signed_in(old) and _signed_in(this)
    finally:
        _cleanup(first_node, user)


def _disable_pending_totp(application, c, user):
    """TOTP set up but never confirmed is no factor yet: dropping it changes none."""
    r = _post(c, '/api/v2/account/2fa/enable')
    assert r.status_code == 200, r.data
    secret = r.get_json()['data']['secret']
    return _post(c, '/api/v2/account/2fa/disable', {'code': pyotp.TOTP(secret).now()})


def _admin_toggle(enabled):
    def _call(application, c, user, admin):
        return admin.patch(f"/api/v2/users/{user['id']}/webauthn/{user['key_id']}",
                           json={'enabled': enabled})
    return _call


# request that leaves the factors as they are: (user it starts from, request, audit action)
NO_CHANGES = {
    'enable-key-already-enabled': ({}, _own(_toggle_key(True)), 'webauthn_toggle'),
    'disable-key-already-disabled': ({'key_enabled': False}, _own(_toggle_key(False)),
                                     'webauthn_toggle'),
    'key-second-factor-on-already-on': ({'choice': True}, _own(_key_choice(True)),
                                        'mfa_webauthn_enable'),
    'key-second-factor-off-already-off': ({}, _own(_key_choice(False)), 'mfa_webauthn_disable'),
    'disable-totp-never-confirmed': ({}, _own(_disable_pending_totp), 'mfa_disable'),
    'admin-enable-key-already-enabled': ({}, _admin_toggle(True), 'webauthn_admin_enable'),
    'admin-disable-key-already-disabled': ({'key_enabled': False}, _admin_toggle(False),
                                           'webauthn_admin_disable'),
}


@pytest.mark.parametrize('operation', sorted(NO_CHANGES))
def test_a_request_that_changes_no_factor_closes_no_session(app, auth_client, operation):
    start, call, action = NO_CHANGES[operation]
    user = _make_user(app, key=SoftKey(), **start)
    try:
        other = _open_session(app, user)
        this = _open_session(app, user)
        _keys, version = _key_state(app, user)
        r = call(app, this, user, auth_client)
        assert r.status_code == 200, r.data
        assert r.get_json()['meta']['other_sessions_closed'] == 0
        assert _signed_in(other) and _signed_in(this)
        assert _key_state(app, user)[1] == version
        assert _audit_details(app, action, user) is None
    finally:
        _cleanup(app, user)


def _delete_account(user_id):
    """The rows go as a concurrent deletion would have them gone: the request's
    objects stay loaded, its next row lock finds no account."""
    from sqlalchemy import delete
    from models.webauthn import WebAuthnChallenge
    for model, column in ((WebAuthnChallenge, WebAuthnChallenge.user_id),
                          (WebAuthnCredential, WebAuthnCredential.user_id), (User, User.id)):
        db.session.execute(delete(model).where(column == user_id)
                           .execution_options(synchronize_session=False))


def test_key_second_factor_off_for_an_account_deleted_meanwhile_answers_404(app, monkeypatch):
    """Deleted while its password was checked: the second lock finds no account."""
    import api.v2.account.twofa as twofa
    user = _make_user(app, key=SoftKey(), choice=True)
    checked = twofa.check_session_password

    def _check_then_delete(account, password, refusal):
        answer = checked(account, password, refusal)
        _delete_account(user['id'])
        return answer
    try:
        this = _open_session(app, user)
        monkeypatch.setattr(twofa, 'check_session_password', _check_then_delete)
        r = _key_choice(False)(app, this, user)
        assert r.status_code == 404, r.data
        assert r.get_json()['message'] == 'User not found'
    finally:
        _cleanup(app, user)


@pytest.mark.parametrize('operation', sorted(KEY_CHANGES))
def test_a_key_change_for_an_account_deleted_meanwhile_answers_404(app, auth_client, monkeypatch,
                                                                    operation):
    """Deleted before its row lock is taken: no change, 404 as the neighbouring routes."""
    import auth.twofa_enforcement as enforcement
    start, call = KEY_CHANGES[operation]
    user = _make_user(app, key=SoftKey(), **start)
    lock = enforcement.lock_user

    def _delete_then_lock(user_id):
        if user_id == user['id']:
            _delete_account(user_id)
        return lock(user_id)
    try:
        this = _open_session(app, user)
        if operation == 'add-key':
            options = _post(this, '/api/v2/webauthn/register/options', {})
            challenge = options.get_json()['data']['challenge']
            monkeypatch.setattr(enforcement, 'lock_user', _delete_then_lock)
            r = _post(this, '/api/v2/webauthn/register/verify',
                      {'credential': SoftKey().attest(challenge), 'name': 'new'})
        else:
            monkeypatch.setattr(enforcement, 'lock_user', _delete_then_lock)
            r = call(app, this, user, auth_client)
        assert r.status_code == 404, r.data
        assert r.get_json()['message'] == 'User not found'
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


def test_totp_disable_for_an_account_deleted_meanwhile_answers_404(app, monkeypatch):
    """Deleted while its attempt was counted: the second lock finds no account."""
    import api.v2.account.twofa as twofa
    user = _make_user(app, totp=True)
    reserve = twofa._reserve_code_check

    def _reserve_then_delete(user_id):
        answer = reserve(user_id)
        _delete_account(user['id'])
        return answer
    try:
        this = _open_session(app, user)
        code = _code(app, user)
        monkeypatch.setattr(twofa, '_reserve_code_check', _reserve_then_delete)
        r = _post(this, '/api/v2/account/2fa/disable', {'code': code})
        assert r.status_code == 404, r.data
        assert r.get_json()['message'] == 'User not found'
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


def _enrolling(c):
    with c.session_transaction() as s:
        s['must_enroll_2fa'] = True


def _gate_kept(c):
    with c.session_transaction() as s:
        return 'must_enroll_2fa' in s


def _enrolment_state(application, user):
    """(keys, session_version, webauthn_2fa) of the account."""
    keys, version = _key_state(application, user)
    with application.app_context():
        flag = bool(db.session.get(User, user['id']).webauthn_2fa)
        db.session.remove()
    return keys, version, flag


class _FailingFlagCommit:
    """Fails the first commit that writes webauthn_2fa = True."""

    def __init__(self):
        self.failed = False

    def on_flush(self, session, _context):
        from sqlalchemy import inspect
        if any(isinstance(o, User) and inspect(o).attrs.webauthn_2fa.history.added == [True]
               for o in session.dirty):
            session.info['flag_set'] = True

    def on_commit(self, session):
        self.on_flush(session, None)
        if session.info.pop('flag_set', False) and not self.failed:
            self.failed = True
            raise RuntimeError('commit refused by the test')

    def on_end(self, session):
        session.info.pop('flag_set', None)


def test_a_key_enrolled_under_the_gate_and_its_flag_commit_together(app):
    """The flag fails to commit: no key, no version, no flag, the gate stays."""
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    user = _make_user(app)
    failing = _FailingFlagCommit()
    listeners = [('after_flush', failing.on_flush), ('before_commit', failing.on_commit),
                 ('after_commit', failing.on_end), ('after_rollback', failing.on_end)]
    try:
        this = _open_session(app, user)
        _enrolling(this)
        before = _enrolment_state(app, user)
        for name, fn in listeners:
            event.listen(Session, name, fn)
        try:
            r = _add_key(app, this, user)
        finally:
            for name, fn in listeners:
                event.remove(Session, name, fn)
        assert failing.failed
        assert r.status_code != 200, r.data
        assert _enrolment_state(app, user) == before
        assert _gate_kept(this)
    finally:
        _cleanup(app, user)


def test_a_key_enrolled_under_the_gate_keeps_the_key_the_version_and_the_flag(app):
    """Non-regression of the success path: key, version and flag move together, audited."""
    user = _make_user(app)
    try:
        this = _open_session(app, user)
        _enrolling(this)
        keys, version, flag = _enrolment_state(app, user)
        r = _add_key(app, this, user)
        assert r.status_code == 200, r.data
        new_keys, new_version, new_flag = _enrolment_state(app, user)
        assert len(new_keys) == len(keys) + 1 and new_version == version + 1
        assert new_flag and not flag
        assert not _gate_kept(this)
        assert _audit_details(app, 'webauthn_register', user) is not None
    finally:
        _cleanup(app, user)


@pytest.mark.parametrize('when', ['first-lock', 'later-lock'])
def test_a_key_enrolled_for_an_account_deleted_meanwhile_never_answers_500(app, monkeypatch, when):
    """Deleted before the row lock: 404 and the gate stays; after it: no second lock fails."""
    import api.v2.webauthn as webauthn
    import auth.twofa_enforcement as enforcement
    user = _make_user(app)
    lock = enforcement.lock_user
    calls = []

    def _delete_then_lock(user_id):
        calls.append(user_id)
        if user_id == user['id'] and (when == 'first-lock') == (len(calls) == 1):
            _delete_account(user_id)
        return lock(user_id)
    try:
        this = _open_session(app, user)
        _enrolling(this)
        options = _post(this, '/api/v2/webauthn/register/options', {})
        challenge = options.get_json()['data']['challenge']
        monkeypatch.setattr(enforcement, 'lock_user', _delete_then_lock)
        monkeypatch.setattr(webauthn, 'lock_user', _delete_then_lock, raising=False)
        r = _post(this, '/api/v2/webauthn/register/verify',
                  {'credential': SoftKey().attest(challenge), 'name': 'new'})
        if when == 'first-lock':
            assert r.status_code == 404, r.data
            assert _gate_kept(this)
        else:
            assert r.status_code == 200, r.data
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


def test_recovery_codes_for_an_account_deleted_meanwhile_answer_404(app, monkeypatch):
    """Deleted while its attempt was counted: the lock after it finds no account."""
    import api.v2.account.twofa as twofa
    user = _make_user(app, totp=True)
    reserve = twofa._reserve_code_check

    def _reserve_then_delete(user_id):
        answer = reserve(user_id)
        _delete_account(user['id'])
        db.session.commit()
        return answer
    try:
        this = _open_session(app, user)
        code = _code(app, user)
        monkeypatch.setattr(twofa, '_reserve_code_check', _reserve_then_delete)
        r = _post(this, '/api/v2/account/2fa/recovery-codes/regenerate', {'code': code})
        assert r.status_code == 404, r.data
        assert r.get_json()['message'] == 'User not found'
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


@pytest.mark.postgres
def test_a_key_change_and_the_deletion_of_its_account_never_deadlock(app, auth_client,
                                                                        monkeypatch):
    """The deletion locks the account row first, as a key change does: the two meet
    (the key change holds the row, the deletion runs) and neither is aborted."""
    import threading
    import time
    from sqlalchemy import text
    import api.v2.users.crud as crud
    from services.webauthn_service import WebAuthnService
    from tests import pg_app_harness
    if not pg_app_harness.ENABLED:
        pytest.skip('row lock order: PostgreSQL app mode only')
    user = _make_user(app, key=SoftKey())
    holds_row, deletion_holds = threading.Event(), threading.Event()
    met, statuses = [], {}
    delete_key, purge = WebAuthnService.delete_credential, crud._purge_user_dependencies

    def _blocked_by(pid):
        with db.engine.connect() as probe:
            return probe.execute(text('SELECT count(*) FROM pg_stat_activity '
                                      'WHERE :pid = ANY(pg_blocking_pids(pid))'),
                                 {'pid': pid}).scalar()

    def _delete_key_once_met(credential_id, user_id):
        # Holding the account row: wait for the deletion to hold its first lock or wait on ours
        pid = db.session.execute(text('SELECT pg_backend_pid()')).scalar()
        holds_row.set()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if deletion_holds.is_set() or _blocked_by(pid):
                met.append(True)
                break
            time.sleep(0.05)
        return delete_key(credential_id, user_id)

    def _purge_then_signal(user_id):
        answer = purge(user_id)
        deletion_holds.set()
        return answer

    def _change_key():
        statuses['key'] = _delete_key(app, this, user).status_code

    def _delete_account():
        holds_row.wait(20)
        statuses['delete'] = auth_client.delete(f"/api/v2/users/{user['id']}").status_code
    try:
        this = _open_session(app, user)
        monkeypatch.setattr(WebAuthnService, 'delete_credential', staticmethod(_delete_key_once_met))
        monkeypatch.setattr(crud, '_purge_user_dependencies', _purge_then_signal)
        threads = [threading.Thread(target=_change_key), threading.Thread(target=_delete_account)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(60)
        assert met == [True], 'the two requests never met'
        assert statuses['key'] in (200, 404) and statuses['delete'] in (200, 404), statuses
    finally:
        monkeypatch.undo()
        _cleanup(app, user)


def test_the_deletion_of_an_account_locks_its_row_before_its_keys(app, auth_client):
    """A key change locks the account row, then its keys: a deletion takes them in that order."""
    from sqlalchemy import event
    user = _make_user(app, key=SoftKey())
    writes = []

    def _record(_conn, _cursor, statement, _params, _context, _many):
        head = statement.lstrip().upper()
        if head.startswith(('UPDATE USERS', 'DELETE FROM USERS', 'DELETE FROM WEBAUTHN_CREDENTIALS')):
            writes.append(' '.join(head.split()[:3]))
    try:
        with app.app_context():
            engine = db.engine
        event.listen(engine, 'before_cursor_execute', _record)
        try:
            r = auth_client.delete(f"/api/v2/users/{user['id']}")
        finally:
            event.remove(engine, 'before_cursor_execute', _record)
        assert r.status_code == 200, r.data
        assert writes and writes[0] == 'UPDATE USERS SET', writes
        assert 'DELETE FROM WEBAUTHN_CREDENTIALS' in writes
    finally:
        _cleanup(app, user)
