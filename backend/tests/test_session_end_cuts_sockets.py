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
    # The caller's renewed session opens its socket again with its new cookie
    assert not ws_second.is_connected() and _reconnects(app, second) is not None


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


# ---- Sessions closed by another gesture: cut at the commit, not at their next request ----

NEW_PASSWORD = 'Sockets-Cut-At-Commit-0k!'


def _admin_session(app, make_user):  # noqa: F811
    from models import User, db
    admin = make_user()
    with app.app_context():
        db.session.execute(db.update(User).where(User.id == admin['id']).values(role='admin'))
        db.session.commit()
        db.session.remove()
    return _password_session(app, admin)


def _put(c, url, body):
    return c.put(url, json=body)


# gesture: (made by the account's other session (True) or an administrator, request)
GESTURES = {
    'revoke-all': (True, lambda c, uid: _post(c, '/api/v2/account/sessions/revoke-all')),
    'own-password': (True, lambda c, uid: _post(c, '/api/v2/account/password', {
        'current_password': PASSWORD, 'new_password': NEW_PASSWORD})),
    'admin-password': (False, lambda c, uid: _post(c, f'/api/v2/users/{uid}/reset-password', {
        'new_password': NEW_PASSWORD})),
    'admin-2fa-reset': (False, lambda c, uid: _post(c, f'/api/v2/users/{uid}/reset-2fa')),
    'admin-toggle-off': (False, lambda c, uid: c.patch(f'/api/v2/users/{uid}/toggle')),
    'admin-update-inactive': (False, lambda c, uid: _put(c, f'/api/v2/users/{uid}',
                                                         {'active': False})),
    'admin-delete': (False, lambda c, uid: c.delete(f'/api/v2/users/{uid}')),
}


def _still_live(ws):
    ws.get_received()
    ws.emit('ping')
    return [m['name'] for m in ws.get_received()][-1:] == ['pong']


def _copy_of(app, client):
    """Another client holding the same session cookie, as a stolen copy would."""
    copy = app.test_client()
    copy.set_cookie('session', client.get_cookie('session').value)
    return copy


def _reconnects(app, client):
    """A fresh socket on the client's cookie, as the browser's one reconnection opens; None
    when the handshake refuses it."""
    from websocket import socketio
    ws = socketio.test_client(app, flask_test_client=client)
    return ws if ws.is_connected() else None


@pytest.mark.parametrize('gesture', sorted(GESTURES))
def test_a_gesture_that_closes_the_account_sessions_cuts_their_sockets_at_once(
        app, make_user, two_sessions, gesture):  # noqa: F811
    """A socket that only listens (a stolen cookie) never sends the frame that revalidates it."""
    from websocket import socketio
    user, (_first, ws_first), (second, ws_second) = two_sessions
    own, call = GESTURES[gesture]
    actor = second if own else _admin_session(app, make_user)
    with _socket(app, actor) as ws_actor:
        r = call(actor, user['id'])
        assert r.status_code == 200, r.data
        assert not ws_first.is_connected()
        assert _sid(ws_first) not in events.connected_clients
        assert not ws_second.is_connected()
        if own:
            # The renewed session keeps no socket of its old key: its tabs reconnect once
            assert not ws_actor.is_connected()
            ws_back = _reconnects(app, second)
            assert ws_back is not None and _still_live(ws_back)
            socketio.emit('event', {'type': 'probe'}, to=f"user:{user['id']}")
            assert [m['name'] for m in ws_back.get_received()] == ['event']
            ws_back.disconnect()
        else:
            assert _still_live(ws_actor)


@pytest.mark.parametrize('gesture', ['revoke-all', 'own-password'])
def test_a_renewal_cuts_a_stolen_copy_of_the_kept_session_and_refuses_its_return(
        app, two_sessions, gesture):
    """The copy holds the caller's old cookie: its socket goes with the caller's, and only the
    renewed cookie opens one again."""
    from websocket import socketio
    user, (_first, _ws_first), (second, ws_second) = two_sessions
    thief = _copy_of(app, second)
    with _socket(app, thief) as ws_thief:
        assert ws_thief.is_connected() and _key_of(ws_thief) == _key_of(ws_second)
        assert GESTURES[gesture][1](second, user['id']).status_code == 200
        assert not ws_thief.is_connected() and not ws_second.is_connected()
        assert _reconnects(app, thief) is None
        assert thief.get('/api/v2/account/profile').status_code == 401
        ws_back = _reconnects(app, second)
        assert ws_back is not None
        socketio.emit('event', {'type': 'probe'}, to=f"user:{user['id']}")
        assert [m['name'] for m in ws_back.get_received()][-1:] == ['event']
        ws_back.disconnect()


def test_the_renewed_session_socket_reopens_and_its_sign_out_cuts_it(app, two_sessions):
    _user, (_first, ws_first), (second, ws_second) = two_sessions
    _own_password = GESTURES['own-password'][1]
    assert _own_password(second, None).status_code == 200
    assert not ws_first.is_connected() and not ws_second.is_connected()
    ws_back = _reconnects(app, second)
    assert ws_back is not None
    assert _post(second, '/api/v2/auth/logout').status_code == 200
    assert not ws_back.is_connected()


def test_the_caller_socket_is_cut_when_its_session_is_not_kept(app, two_sessions, monkeypatch):
    _user, (_first, ws_first), (second, ws_second) = two_sessions

    def rotate(self, session):
        session.store_refused = 'busy'
        raise RuntimeError('session store unreachable (test)')

    monkeypatch.setattr(type(app.session_interface), 'rotate', rotate)
    r = _post(second, '/api/v2/account/sessions/revoke-all')
    assert r.status_code == 500, r.data
    assert not ws_first.is_connected()
    assert not ws_second.is_connected()


def test_a_bump_rolled_back_cuts_nothing(app, two_sessions):
    from models import User, db
    user, (_first, ws_first), (_second, ws_second) = two_sessions
    with app.app_context():
        db.session.get(User, user['id']).end_sessions()
        db.session.rollback()
        db.session.execute(db.select(User.id).where(User.id == user['id']))
        db.session.commit()
        db.session.remove()
    assert ws_first.is_connected() and ws_second.is_connected()


def test_a_restore_epoch_cuts_every_socket_opened_before_it(app, two_sessions):
    from auth.session_epoch import advance_epoch
    from models import db
    _user, (_first, ws_first), (_second, ws_second) = two_sessions
    with app.app_context():
        advance_epoch()
        db.session.remove()
    assert not ws_first.is_connected() and not ws_second.is_connected()


class TestAccountCutOnOtherProcesses:
    @staticmethod
    def _publisher(monkeypatch):
        published = []

        class Publisher:
            def publish(self, room, payload):
                published.append((room, payload))

        monkeypatch.setattr(events, '_relay_publisher', Publisher())
        monkeypatch.setattr(events, '_relay_emits_here', True)
        return published

    def test_the_relay_hears_the_account_then_the_cut_of_the_renewed_session_old_key(
            self, app, two_sessions, monkeypatch):
        user, (_first, _ws_first), (second, ws_second) = two_sessions
        spared = _key_of(ws_second)
        published = self._publisher(monkeypatch)
        assert _post(second, '/api/v2/account/sessions/revoke-all').status_code == 200
        ended = [p for room, p in published if room == events.SESSION_END_ROOM]
        assert len([p for p in ended if 'user' in p]) == 1
        assert ended[0]['user'] == user['id'] and ended[0]['spare'] == spared
        assert isinstance(ended[0]['below'], int)
        # Every node then closes the old key's sockets, a stolen copy's among them; none moves
        assert {'type': events.SESSION_END_EVENT, 'session': spared} in ended[1:]
        assert not [p for p in ended if 'moved' in p]
        # No session id, a credential, reaches the shared table
        assert second.get_cookie('session').value not in str(published)

    def test_a_relayed_cut_of_an_old_key_closes_every_socket_of_it_here(
            self, app, two_sessions):
        """A stolen copy's socket on another node: the relayed cut of the old key closes it."""
        from services import ws_relay
        from tests.test_websocket_session_lock import _wait_for
        _user, (_first, ws_first), (second, ws_second) = two_sessions
        with _socket(app, _copy_of(app, second)) as ws_thief:
            ws_relay._emit_local(events.SESSION_END_ROOM, {
                'type': events.SESSION_END_EVENT, 'session': _key_of(ws_second)})
            assert _wait_for(lambda: not ws_thief.is_connected())
            assert not ws_second.is_connected() and ws_first.is_connected()

    def test_the_redis_queue_carries_the_cut_of_an_old_key(self, app, two_sessions):
        _user, (_first, ws_first), (second, ws_second) = two_sessions
        sent = []

        class Base:
            def _handle_emit(self, message):
                sent.append(message)

        with _socket(app, _copy_of(app, second)) as ws_thief:
            events._session_ending(Base)()._handle_emit({
                'method': 'emit', 'event': events.SESSION_END_EVENT,
                'data': [{'session': _key_of(ws_second)}], 'room': events.SESSION_END_ROOM,
                'namespace': '/'})
            assert not ws_thief.is_connected() and not ws_second.is_connected()
            assert ws_first.is_connected() and sent == []

    def test_a_moved_notice_moves_no_socket(self, app, two_sessions):
        """The notice that once renamed a session's sockets is not honoured: nothing follows."""
        _user, (_first, ws_first), (_second, _ws_second) = two_sessions
        key = _key_of(ws_first)
        assert events.apply_session_end_here({'moved': key, 'to': 'f' * 32, 'version': 99}) == 0
        assert _key_of(ws_first) == key

    def test_a_relayed_account_cut_closes_the_sockets_here_but_the_spared_one(
            self, app, two_sessions):
        from services import ws_relay
        from tests.test_websocket_session_lock import _wait_for
        user, (_first, ws_first), (_second, ws_second) = two_sessions
        state = events.connected_clients[_sid(ws_first)]
        payload = {'type': events.SESSION_END_EVENT, 'user': user['id'],
                   'below': state['session_version'] + 1, 'spare': _key_of(ws_second)}
        ws_relay._emit_local(events.SESSION_END_ROOM, payload)
        assert _wait_for(lambda: not ws_first.is_connected())
        assert ws_second.is_connected()

    def test_the_redis_queue_carries_the_account_cut(self, app, two_sessions):
        user, (_first, ws_first), (_second, ws_second) = two_sessions
        sent = []

        class Base:
            def _handle_emit(self, message):
                sent.append(message)

        manager = events._session_ending(Base)()
        version = events.connected_clients[_sid(ws_first)]['session_version']
        manager._handle_emit({'method': 'emit', 'event': events.SESSION_END_EVENT,
                              'data': [{'user': user['id'], 'below': version + 1, 'spare': None}],
                              'room': events.SESSION_END_ROOM, 'namespace': '/'})
        assert not ws_first.is_connected() and not ws_second.is_connected()
        assert sent == []

    def test_a_socket_opened_under_the_new_version_is_not_cut(self, app, two_sessions):
        user, (_first, ws_first), (_second, ws_second) = two_sessions
        version = events.connected_clients[_sid(ws_first)]['session_version']
        assert events.apply_session_end_here(
            {'user': user['id'], 'below': version, 'spare': None}) == 0
        assert ws_first.is_connected() and ws_second.is_connected()
