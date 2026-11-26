"""A CSRF token belongs to the session it was issued to, and lasts as long as that session.

The tokens issued to a session are recorded in its server-side record: a restart that
changes SECRET_KEY (a container that generates one at each start) keeps them valid, while a
token signed for the same account but issued to another session, or forged, is refused. On
the file store, the SQL store (SQLite), two nodes on one PostgreSQL schema (HA) and Redis.
"""
import json
import secrets
import time

import pytest

from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    PASSWORD, _cleanup, _drop_session_table_from_metadata, _make_user, _open_session, nodes)

WRITE = '/api/v2/account/preferences'
REFUSED = 'urn:ucm:problem:csrf-invalid'


@pytest.fixture
def csrf_on(monkeypatch):
    from security.csrf import CSRFProtection
    monkeypatch.setattr(CSRFProtection, 'is_enabled', classmethod(lambda cls: True))


def _token(c):
    r = c.get('/api/v2/auth/verify')
    assert r.status_code == 200, r.data
    return r.get_json()['data']['csrf_token']


def _write(c, token):
    return c.put(WRITE, data=json.dumps({}), content_type='application/json',
                 headers={'X-CSRF-Token': token} if token else {})


def _on(application, cookie):
    c = application.test_client()
    c.set_cookie('session', cookie)
    return c


@pytest.fixture
def restarted(monkeypatch):
    """The node as a restart leaves it: a new SECRET_KEY, nothing held in memory."""
    def restart(application):
        monkeypatch.setitem(application.config, 'SECRET_KEY', secrets.token_hex(32))
        monkeypatch.setitem(application.config, 'SECRET_KEY_FALLBACKS', [])
        return application
    return restart


@pytest.fixture
def user(nodes):
    first, _second = nodes
    info = _make_user(first)
    yield info
    _cleanup(first, info)


def test_a_token_outlives_a_restart_that_changed_the_key(nodes, user, csrf_on, restarted):
    first, second = nodes
    c = _open_session(first, user)
    token = _token(c)
    assert _write(c, token).status_code == 200
    after = _on(restarted(second), c.get_cookie('session').value)
    r = _write(after, token)
    assert r.status_code == 200, r.data


def test_every_token_the_session_holds_outlives_the_restart(nodes, user, csrf_on, restarted):
    """Two tabs of one session each keep the token their own check handed out."""
    first, second = nodes
    c = _open_session(first, user)
    tokens = [_token(c), _token(c)]
    after = _on(restarted(second), c.get_cookie('session').value)
    for token in tokens:
        assert _write(after, token).status_code == 200


def test_a_token_of_another_session_of_the_account_is_refused(nodes, user, csrf_on):
    first, second = nodes
    mine = _open_session(first, user)
    other = _open_session(first, user)
    foreign = _token(other)
    _token(mine)
    r = _write(_on(second, mine.get_cookie('session').value), foreign)
    assert r.status_code == 403, r.data
    assert r.get_json()['type'] == REFUSED


def test_a_token_signed_with_the_key_but_never_issued_is_refused(nodes, user, csrf_on):
    from security.csrf import CSRFProtection
    first, _second = nodes
    c = _open_session(first, user)
    _token(c)
    with first.app_context():
        minted = CSRFProtection.generate_token(user['id'])
    assert _write(c, minted).status_code == 403


def test_a_forged_or_missing_token_is_refused(nodes, user, csrf_on):
    first, _second = nodes
    c = _open_session(first, user)
    issued = _token(c)
    stamp, nonce, _signature = issued.split(':')
    for forged in (None, f'{stamp}:{nonce}:{"0" * 64}', f'{int(time.time())}:{"ab" * 16}:{"0" * 64}',
                   f'{stamp}:{secrets.token_hex(16)}:{_signature}', 'garbage'):
        r = _write(c, forged)
        assert r.status_code == 403, (forged, r.data)
        assert r.get_json()['type'] == REFUSED


def test_a_new_sign_in_drops_the_tokens_of_the_previous_one(nodes, user, csrf_on):
    first, _second = nodes
    c = _open_session(first, user)
    old = _token(c)
    assert c.post('/api/v2/auth/login/password', data=json.dumps(
        {'username': user['username'], 'password': PASSWORD}),
        content_type='application/json').status_code == 200
    _token(c)
    assert _write(c, old).status_code == 403


def test_a_token_lost_by_a_concurrent_save_is_kept(nodes, user, csrf_on, restarted):
    """A request that read the record before a check issued a token saves after it: the
    token stays recorded."""
    first, second = nodes
    c = _open_session(first, user)
    cookie = c.get_cookie('session').value
    from flask import request
    with first.test_request_context('/api/v2/account/profile',
                                    headers={'Cookie': f'session={cookie}'}):
        interface = first.session_interface
        stale = interface.open_session(first, request)
        token = _token(c)
        stale['last_activity'] = 'touched'
        interface.save_session(first, stale, first.response_class())
    after = _on(restarted(second), cookie)
    assert _write(after, token).status_code == 200
