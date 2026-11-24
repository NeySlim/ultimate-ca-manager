"""Every end of a session closes its WebSockets at once, after the store holds the end.

Not only a sign-out or a lock: a session found closed by a credential change, expired, or
replaced by a new sign-in closes its sockets in the request that ends it, without waiting for
the 60 s revalidation. The cut runs once the record is gone, so a socket that reconnects in
between is refused by the handshake instead of staying open until the next revalidation.
"""
from contextlib import contextmanager

import pytest

from tests.test_session_lock_and_info import (  # noqa: F401 (fixture)
    PASSWORD, _password_session, _post, make_user)
from tests.test_websocket_session_lock import _key_of, _sid, _socket
from websocket import events


@pytest.fixture
def two_sessions(app, make_user):  # noqa: F811
    """Two sessions of one account, each with its socket open (revalidation not due)."""
    user = make_user()
    first, second = _password_session(app, user), _password_session(app, user)
    with _socket(app, first) as ws_first, _socket(app, second) as ws_second:
        assert ws_first.is_connected() and ws_second.is_connected()
        yield user, (first, ws_first), (second, ws_second)


@contextmanager
def _cuts_seen(app, monkeypatch):
    """Each cut asked, with whether the session's record was still stored at that moment."""
    seen = []
    cut = events.end_session_sockets
    iface = app.session_interface

    def recording(session_id):
        stored = bool(session_id) and iface._record_exists(iface._get_store_id(session_id))
        seen.append((events.session_key(session_id), stored))
        return cut(session_id)

    monkeypatch.setattr(events, 'end_session_sockets', recording)
    yield seen


def test_a_session_closed_by_a_credential_change_cuts_its_socket_at_its_next_request(
        app, two_sessions):
    _user, (first, ws_first), (second, ws_second) = two_sessions
    assert _post(second, '/api/v2/account/sessions/revoke-all').status_code == 200
    assert first.get('/api/v2/account/profile').status_code == 401
    assert not ws_first.is_connected()
    assert _sid(ws_second) in events.connected_clients and ws_second.is_connected()


def test_an_expired_session_cuts_its_socket_at_its_next_request(app, two_sessions, monkeypatch):
    from auth.unified import AuthManager
    _user, (first, ws_first), (_second, ws_second) = two_sessions
    monkeypatch.setattr(AuthManager, 'session_ended', staticmethod(lambda *a, **k: True))
    assert first.get('/api/v2/account/profile').status_code == 401
    monkeypatch.undo()
    assert not ws_first.is_connected()
    assert ws_second.is_connected()


def test_a_new_sign_in_over_a_session_cuts_the_replaced_session_socket(app, two_sessions):
    user, (first, ws_first), (_second, ws_second) = two_sessions
    r = _post(first, '/api/v2/auth/login/password',
              {'username': user['username'], 'password': PASSWORD})
    assert r.status_code == 200, r.data
    assert not ws_first.is_connected()
    assert ws_second.is_connected()


@pytest.mark.parametrize('end', ['sign-out', 'credential-change'])
def test_the_cut_runs_once_the_record_is_gone(app, two_sessions, monkeypatch, end):
    """Cut before the removal, a socket reconnecting in between would pass the handshake."""
    _user, (first, ws_first), (second, _ws_second) = two_sessions
    key = _key_of(ws_first)
    with _cuts_seen(app, monkeypatch) as seen:
        if end == 'sign-out':
            assert _post(first, '/api/v2/auth/logout').status_code == 200
        else:
            assert _post(second, '/api/v2/account/sessions/revoke-all').status_code == 200
            seen.clear()
            assert first.get('/api/v2/account/profile').status_code == 401
    assert (key, False) in seen
    assert (key, True) not in seen
    assert not ws_first.is_connected()
