"""Real-time WebSocket: session handshake, managed rooms, revalidation, emission, status."""

import logging
import math
from contextlib import contextmanager
from uuid import uuid4

import pytest
from flask import Flask

from auth.twofa_enforcement import ENROLL_SESSION_KEY
from models import User, db
from models.group import Group, GroupMember
from models.rbac import CustomRole
from tests.conftest import assert_success
from utils.datetime_utils import utc_now
from websocket import emitters, events, socketio
from websocket.events import WebSocketValidationError

# A role name absent from the built-in table: the account holds only what it is granted below.
NO_BUILTIN_ROLE = 'ws-none'
READER = ['read:certificates']
PRIVILEGED = ['read:certificates', 'read:cas']


@pytest.fixture
def make_user(app):
    """Creates accounts (with an optional custom role and group) and removes them afterwards."""
    made = {'users': [], 'roles': [], 'groups': []}

    def _make(role=NO_BUILTIN_ROLE, role_perms=None, group_perms=None):
        tag = uuid4().hex[:10]
        with app.app_context():
            user = User(username=f'ws-{tag}', email=f'ws-{tag}@test.local', role=role,
                        active=True)
            user.set_password('WsTestPass123!')
            if role_perms is not None:
                custom = CustomRole(name=f'ws-role-{tag}', permissions=list(role_perms))
                db.session.add(custom)
                db.session.flush()
                user.custom_role_id = custom.id
                made['roles'].append(custom.id)
            db.session.add(user)
            db.session.flush()
            if group_perms is not None:
                group = Group(name=f'ws-group-{tag}', permissions=list(group_perms))
                db.session.add(group)
                db.session.flush()
                db.session.add(GroupMember(group_id=group.id, user_id=user.id))
                made['groups'].append(group.id)
            db.session.commit()
            made['users'].append(user.id)
            return user.id

    yield _make
    with app.app_context():
        for group_id in made['groups']:
            GroupMember.query.filter_by(group_id=group_id).delete()
            db.session.delete(db.session.get(Group, group_id))
        for user_id in made['users']:
            GroupMember.query.filter_by(user_id=user_id).delete()
            user = db.session.get(User, user_id)
            if user is not None:
                db.session.delete(user)
        db.session.flush()
        for role_id in made['roles']:
            role = db.session.get(CustomRole, role_id)
            if role is not None:
                db.session.delete(role)
        db.session.commit()


def _session_client(app, user_id=None, **extra):
    """A Flask test client whose server-side session holds what a login would put there."""
    client = app.test_client()
    with client.session_transaction() as sess:
        now = utc_now().isoformat()
        if user_id is not None:
            sess['user_id'] = user_id
        sess['login_time'] = now
        sess['last_activity'] = now
        sess.update(extra)
    return client


@contextmanager
def _socket(app, flask_client=None, **kw):
    ws = socketio.test_client(app, flask_test_client=flask_client, **kw)
    try:
        yield ws
    finally:
        if ws.is_connected():
            ws.disconnect()


def _sid(ws):
    return socketio.server.manager.sid_from_eio_sid(ws.eio_sid, '/')


def _rooms(ws):
    sid = _sid(ws)
    return set(socketio.server.rooms(sid)) - {sid}


def _named(received, name):
    return [msg['args'][0] for msg in received if msg['name'] == name]


def _set_permissions(app, user_id, role_perms):
    with app.app_context():
        user = db.session.get(User, user_id)
        db.session.get(CustomRole, user.custom_role_id).permissions = list(role_perms)
        db.session.commit()


@pytest.fixture
def revalidate_now(app, monkeypatch):
    monkeypatch.setitem(app.config, 'WEBSOCKET_REVALIDATE_SECONDS', 0)


@pytest.fixture
def reader(app, make_user):
    """A connected socket of a plain certificate reader, with its user id."""
    user_id = make_user(role_perms=READER)
    with _socket(app, _session_client(app, user_id)) as ws:
        assert ws.is_connected()
        ws.get_received()
        yield ws, user_id


@pytest.fixture
def privileged(app, make_user):
    user_id = make_user(role_perms=PRIVILEGED)
    with _socket(app, _session_client(app, user_id)) as ws:
        assert ws.is_connected()
        ws.get_received()
        yield ws, user_id


# ---------------------------------------------------------------- authentication

class TestHandshake:
    def test_refused_without_read_certificates(self, app, make_user):
        user_id = make_user(role_perms=['read:cas', 'read:audit'])
        with _socket(app, _session_client(app, user_id)) as ws:
            assert not ws.is_connected()

    def test_session_without_user_is_refused(self, app):
        with _socket(app, _session_client(app)) as ws:
            assert not ws.is_connected()

    def test_inactive_user_is_refused(self, app, make_user):
        user_id = make_user(role_perms=READER)
        with app.app_context():
            db.session.get(User, user_id).active = False
            db.session.commit()
        with _socket(app, _session_client(app, user_id)) as ws:
            assert not ws.is_connected()

    def test_real_login_connects_into_own_and_scope_rooms(self, app, auth_client, create_user):
        user = create_user(username=f'ws-viewer-{uuid4().hex[:8]}', role='viewer')
        try:
            self._login_and_connect(app, user)
        finally:
            auth_client.delete(f"/api/v2/users/{user['id']}")

    @staticmethod
    def _login_and_connect(app, user):
        client = app.test_client()
        r = client.post('/api/v2/auth/login',
                        json={'username': user['username'], 'password': 'TestPass123!'})
        assert r.status_code == 200, r.data
        with _socket(app, client) as ws:
            assert ws.is_connected()
            connected = _named(ws.get_received(), 'connected')
            assert len(connected) == 1
            assert connected[0]['status'] == 'ok'
            assert connected[0]['user_id'] == user['id']
            assert connected[0]['timestamp']
            # viewer: read:certificates and read:cas, no read:audit nor read:system
            assert _rooms(ws) == {f"user:{user['id']}", emitters.ROOM_CERTIFICATES,
                                  emitters.ROOM_CAS}

    def test_admin_wildcard_joins_every_scope(self, app, auth_client):
        with _socket(app, auth_client) as ws:
            scopes = {r for r in _rooms(ws) if r.startswith('scope:')}
            assert scopes == {emitters.ROOM_CERTIFICATES, emitters.ROOM_CAS,
                              emitters.ROOM_SYSTEM_ALERTS, emitters.ROOM_AUDIT}

    def test_custom_role_permissions_decide_the_rooms(self, app, make_user):
        user_id = make_user(role_perms=['read:certificates', 'read:audit'])
        with _socket(app, _session_client(app, user_id)) as ws:
            assert _rooms(ws) == {f'user:{user_id}', emitters.ROOM_CERTIFICATES,
                                  emitters.ROOM_AUDIT}

    def test_group_permissions_count(self, app, make_user):
        user_id = make_user(group_perms=['read:certificates', 'read:cas'])
        with _socket(app, _session_client(app, user_id)) as ws:
            assert ws.is_connected()
            assert _rooms(ws) == {f'user:{user_id}', emitters.ROOM_CERTIFICATES,
                                  emitters.ROOM_CAS}

    def test_pending_second_factor_is_refused(self, app, make_user):
        user_id = make_user(role_perms=READER)
        client = _session_client(app, pending_2fa_user_id=user_id)
        with _socket(app, client) as ws:
            assert not ws.is_connected()

    def test_forced_2fa_enrollment_session_is_refused(self, app, make_user):
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id, **{ENROLL_SESSION_KEY: True})
        with _socket(app, client) as ws:
            assert not ws.is_connected()
        # same account, full session: accepted, so the flag alone made the difference
        with _socket(app, _session_client(app, user_id)) as ws:
            assert ws.is_connected()


class TestApiKeyIsNeverAccepted:
    @pytest.fixture
    def api_key(self, app, auth_client, monkeypatch):
        monkeypatch.setitem(app.config, 'API_KEY_MAX_PER_USER', 1000)
        r = auth_client.post('/api/v2/account/apikeys', json={
            'name': 'ws-realtime', 'permissions': ['read:certificates', 'read:cas']})
        data = assert_success(r, 201)
        yield data['key']
        auth_client.delete(f"/api/v2/account/apikeys/{data['id']}")

    def test_the_key_is_valid_over_http(self, app, api_key):
        r = app.test_client().get('/api/v2/websocket/status', headers={'X-API-Key': api_key})
        assert r.status_code == 200, r.data

    @pytest.mark.parametrize('form', ['auth', 'query', 'x-api-key', 'bearer'])
    def test_refused_in_every_form(self, app, api_key, form):
        kw = {
            'auth': {'auth': {'api_key': api_key}},
            'query': {'query_string': f'api_key={api_key}&token={api_key}'},
            'x-api-key': {'headers': {'X-API-Key': api_key}},
            'bearer': {'headers': {'Authorization': f'Bearer {api_key}'}},
        }[form]
        with _socket(app, **kw) as ws:
            assert not ws.is_connected()


# ---------------------------------------------------------------- revalidation

class TestRevalidation:
    def test_expired_session_is_cut_on_ping(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)
        with _socket(app, client) as ws:
            sid = _sid(ws)
            assert sid in events.connected_clients
            client.post('/api/v2/auth/logout')
            ws.emit('ping')
            assert not ws.is_connected()
            assert sid not in events.connected_clients

    def test_disabled_user_is_cut(self, app, reader, revalidate_now):
        ws, user_id = reader
        with app.app_context():
            db.session.get(User, user_id).active = False
            db.session.commit()
        ws.emit('subscribe', {'rooms': [f'user:{user_id}']})
        assert not ws.is_connected()

    def test_withdrawn_unrelated_permission_cuts(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=['read:certificates', 'read:templates'])
        with _socket(app, _session_client(app, user_id)) as ws:
            _set_permissions(app, user_id, ['read:certificates'])
            ws.emit('unsubscribe', {'rooms': []})
            assert not ws.is_connected()

    def test_withdrawn_permission_stops_delivery(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=['read:certificates', 'read:cas'])
        with _socket(app, _session_client(app, user_id)) as ws:
            sid = _sid(ws)
            _set_permissions(app, user_id, ['read:certificates'])
            ws.emit('ping')
            assert sid not in events.connected_clients
            assert socketio.server.manager.get_rooms(sid, '/') == []
            ws.queue.clear()
            emitters.on_ca_created(5, 'n', 'cn', 'admin')
            assert ws.queue == []

    def test_grown_permissions_join_new_scopes(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=READER)
        with _socket(app, _session_client(app, user_id)) as ws:
            assert emitters.ROOM_AUDIT not in _rooms(ws)
            _set_permissions(app, user_id, ['read:certificates', 'read:audit'])
            ws.get_received()
            ws.emit('ping')
            assert ws.is_connected()
            assert _named(ws.get_received(), 'pong')
            assert emitters.ROOM_AUDIT in _rooms(ws)

    def test_other_identity_in_the_session_cuts(self, app, make_user, revalidate_now):
        first = make_user(role_perms=READER)
        second = make_user(role_perms=PRIVILEGED)
        client = _session_client(app, first)
        with _socket(app, client) as ws:
            with client.session_transaction() as sess:
                sess['user_id'] = second
            ws.emit('ping')
            assert not ws.is_connected()

    def test_failing_session_check_cuts(self, app, reader, revalidate_now, monkeypatch, caplog):
        ws, _ = reader
        sid = _sid(ws)

        def unreachable(self):
            raise ConnectionError('database unreachable')

        monkeypatch.setattr(events.AuthManager, 'verify_session', unreachable)
        with caplog.at_level(logging.WARNING, logger='websocket.events'):
            ws.emit('ping')
        assert not ws.is_connected()
        assert sid not in events.connected_clients
        assert socketio.server.manager.get_rooms(sid, '/') == []
        assert any('database unreachable' in r.getMessage() for r in caplog.records)

    def test_enrollment_flag_set_later_cuts(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)
        with _socket(app, client) as ws:
            with client.session_transaction() as sess:
                sess[ENROLL_SESSION_KEY] = True
            ws.emit('ping')
            assert not ws.is_connected()

    def test_default_delay_is_at_most_one_minute(self, app, make_user, monkeypatch):
        clock = [1000.0]
        monkeypatch.setattr(events, '_monotonic', lambda: clock[0])
        user_id = make_user(role_perms=['read:certificates', 'read:cas'])
        with _socket(app, _session_client(app, user_id)) as ws:
            _set_permissions(app, user_id, ['read:certificates'])
            clock[0] += 60
            ws.emit('ping')
            assert not ws.is_connected()

    def test_ping_answers_pong(self, reader):
        ws, _ = reader
        ws.emit('ping')
        (pong,) = _named(ws.get_received(), 'pong')
        assert pong['timestamp']


# ---------------------------------------------------------------- rooms

class TestRooms:
    def test_own_room_accepted_other_resource_refused(self, reader):
        ws, user_id = reader
        ws.emit('subscribe', {'rooms': [f'user:{user_id}', 'ca:1', 'cert:7', 'user:999999']})
        (reply,) = _named(ws.get_received(), 'subscribed')
        assert reply['rooms'] == [f'user:{user_id}']
        assert 'ca:1' not in _rooms(ws)

    def test_privileged_joins_resource_room(self, privileged):
        ws, _ = privileged
        ws.emit('subscribe', {'rooms': ['cert:42', 'ca:abc-1.2']})
        (reply,) = _named(ws.get_received(), 'subscribed')
        assert reply['rooms'] == ['cert:42', 'ca:abc-1.2']
        assert {'cert:42', 'ca:abc-1.2'} <= _rooms(ws)

    @pytest.mark.parametrize('name', [
        'global', 'scope:audit', 'admin:1', 'cert:', 'cert:-1', 'cert:a b', 'cert:a/b',
        'cert:' + 'a' * 124, 'cert:1\n', 42, None, ['cert:1'],
    ])
    def test_malformed_names_are_ignored(self, privileged, name):
        ws, _ = privileged
        before = _rooms(ws)
        ws.emit('subscribe', {'rooms': [name, 'cert:1']})
        (reply,) = _named(ws.get_received(), 'subscribed')
        assert reply['rooms'] == ['cert:1']
        assert _rooms(ws) == before | {'cert:1'}
        assert ws.is_connected()

    def test_longest_valid_name_is_accepted(self, privileged):
        ws, _ = privileged
        name = 'cert:' + 'a' * 123
        assert len(name) == 128
        ws.emit('subscribe', {'rooms': [name]})
        assert _named(ws.get_received(), 'subscribed') == [{'rooms': [name]}]

    @pytest.mark.parametrize('payload', [None, 'cert:1', ['cert:1'], {}, {'rooms': 'cert:1'}])
    def test_payload_without_room_list(self, privileged, payload):
        ws, _ = privileged
        for event, reply in (('subscribe', 'subscribed'), ('unsubscribe', 'unsubscribed')):
            if payload is None:
                ws.emit(event)
            else:
                ws.emit(event, payload)
            assert _named(ws.get_received(), reply) == [{'rooms': []}]

    def test_managed_rooms_cannot_be_left(self, app, auth_client):
        with _socket(app, auth_client) as ws:
            sid = _sid(ws)
            managed = _rooms(ws)
            own = next(r for r in managed if r.startswith('user:'))
            ws.get_received()
            ws.emit('unsubscribe', {'rooms': [own, emitters.ROOM_CERTIFICATES]})
            assert _named(ws.get_received(), 'unsubscribed') == [{'rooms': []}]
            assert _rooms(ws) == managed
            assert events.connected_clients[sid]['rooms'] == managed

    def test_subscribed_room_can_be_left(self, privileged):
        ws, _ = privileged
        ws.emit('subscribe', {'rooms': ['group:3']})
        ws.emit('unsubscribe', {'rooms': ['group:3']})
        assert _named(ws.get_received(), 'unsubscribed') == [{'rooms': ['group:3']}]
        assert 'group:3' not in _rooms(ws)

    def test_too_many_rooms_in_one_request(self, privileged):
        ws, _ = privileged
        before = _rooms(ws)
        rooms = [f'cert:{i}' for i in range(events.MAX_ROOMS_PER_REQUEST + 1)]
        ws.emit('subscribe', {'rooms': rooms})
        received = ws.get_received()
        assert _named(received, 'subscribed') == []
        (error,) = _named(received, 'subscription_error')
        assert error['error'] == 'too_many_rooms'
        assert _rooms(ws) == before

    def test_request_at_the_limit_is_accepted(self, privileged):
        ws, _ = privileged
        rooms = [f'cert:{i}' for i in range(events.MAX_ROOMS_PER_REQUEST)]
        ws.emit('subscribe', {'rooms': rooms})
        assert _named(ws.get_received(), 'subscribed') == [{'rooms': rooms}]

    def test_socket_room_cap(self, privileged, monkeypatch):
        ws, _ = privileged
        sid = _sid(ws)
        monkeypatch.setattr(events, 'SUBSCRIPTION_OPS_LIMIT', 1000)
        cap = events.MAX_ROOMS_PER_SOCKET
        n = 0
        while len(events.connected_clients[sid]['rooms']) < cap:
            ws.emit('subscribe', {'rooms': [f'cert:{n + i}' for i in range(20)]})
            n += 20
        ws.get_received()
        ws.emit('subscribe', {'rooms': ['ca:over-the-cap']})
        assert _named(ws.get_received(), 'subscribed') == [{'rooms': []}]
        assert 'ca:over-the-cap' not in _rooms(ws)
        assert len(events.connected_clients[sid]['rooms']) == cap
        assert len(_rooms(ws)) == cap


class TestRateLimit:
    def test_over_the_limit_is_refused_without_disconnecting(self, privileged):
        ws, _ = privileged
        for i in range(events.SUBSCRIPTION_OPS_LIMIT):
            ws.emit('subscribe' if i % 2 else 'unsubscribe', {'rooms': ['cert:1']})
        received = ws.get_received()
        assert _named(received, 'subscription_error') == []
        ws.emit('subscribe', {'rooms': ['cert:2']})
        received = ws.get_received()
        assert [e['error'] for e in _named(received, 'subscription_error')] == ['rate_limited']
        assert _named(received, 'subscribed') == []
        assert 'cert:2' not in _rooms(ws)
        assert ws.is_connected()

    def test_window_slides(self, privileged, monkeypatch):
        ws, _ = privileged
        clock = [5000.0]
        monkeypatch.setattr(events, '_monotonic', lambda: clock[0])
        events.connected_clients[_sid(ws)]['validated_at'] = clock[0]
        for _ in range(events.SUBSCRIPTION_OPS_LIMIT):
            ws.emit('subscribe', {'rooms': []})
        clock[0] += events.SUBSCRIPTION_WINDOW_SECONDS - 1
        ws.emit('subscribe', {'rooms': []})
        assert _named(ws.get_received(), 'subscription_error')
        events.connected_clients[_sid(ws)]['validated_at'] = clock[0]
        clock[0] += 1
        ws.emit('subscribe', {'rooms': []})
        assert _named(ws.get_received(), 'subscribed') == [{'rooms': []}]


    def test_refused_requests_count_too(self, privileged, monkeypatch):
        ws, _ = privileged
        clock = [9000.0]
        monkeypatch.setattr(events, '_monotonic', lambda: clock[0])
        state = events.connected_clients[_sid(ws)]
        limit, window = events.SUBSCRIPTION_OPS_LIMIT, events.SUBSCRIPTION_WINDOW_SECONDS

        def errors_after(n):
            state['validated_at'] = clock[0]
            ws.get_received()
            for _ in range(n):
                ws.emit('subscribe', 'not a payload')
            return [e['error'] for e in _named(ws.get_received(), 'subscription_error')]

        assert errors_after(limit) == []
        clock[0] += window / 2
        assert errors_after(limit) == ['rate_limited'] * limit
        clock[0] += window / 2
        assert errors_after(1) == ['rate_limited']  # the refused half-window still counts
        clock[0] += window
        assert errors_after(1) == []

# ---------------------------------------------------------------- emission

class TestEmission:
    def test_certificate_issued_reaches_the_scope(self, app, reader):
        ws, _ = reader
        emitters.on_certificate_issued(11, 'host.test', 3, 'Issuer CA', '2030-01-01T00:00:00Z')
        (event,) = _named(ws.get_received(), 'event')
        assert event['type'] == 'certificate.issued'
        assert event['data'] == {'id': 11, 'cn': 'host.test', 'ca_id': 3,
                                 'issuer': 'Issuer CA', 'valid_to': '2030-01-01T00:00:00Z'}
        assert event['timestamp']

    def test_audit_critical_only_reaches_audit_readers(self, app, make_user):
        cert_reader = make_user(role_perms=['read:certificates', 'read:cas'])
        auditor = make_user(role_perms=['read:certificates', 'read:audit'])
        with _socket(app, _session_client(app, cert_reader)) as ws_cert, \
                _socket(app, _session_client(app, auditor)) as ws_audit:
            ws_cert.get_received()
            ws_audit.get_received()
            events.emit_audit_critical('ca.delete', 'admin', 'ca:9', {'reason': 'test'})
            assert _named(ws_cert.get_received(), 'event') == []
            (event,) = _named(ws_audit.get_received(), 'event')
            assert event['type'] == 'audit.critical'
            assert event['data']['resource'] == 'ca:9'

    @pytest.mark.parametrize('fn,room', [
        (lambda: emitters.on_certificate_revoked(1, 'cn', 'keyCompromise', 'admin'),
         emitters.ROOM_CERTIFICATES),
        (lambda: emitters.on_ssh_certificate_deleted(1, 'k', 'admin'), emitters.ROOM_CERTIFICATES),
        (lambda: emitters.on_discovery_new_cert('h', 443, 'CN=h'), emitters.ROOM_CERTIFICATES),
        (lambda: emitters.on_ca_created(1, 'n', 'cn', 'admin'), emitters.ROOM_CAS),
        (lambda: emitters.on_crl_regenerated(1, 'n', '2030', 0), emitters.ROOM_CAS),
        (lambda: emitters.on_ssh_ca_deleted(1, 'n', 'admin'), emitters.ROOM_CAS),
        (lambda: emitters.on_user_created(1, 'u', 'admin'), emitters.ROOM_AUDIT),
        (lambda: emitters.on_group_deleted(1, 'g', 'admin'), emitters.ROOM_AUDIT),
        (lambda: emitters.on_audit_critical('a', 'u', 'r'), emitters.ROOM_AUDIT),
        (lambda: emitters.on_system_alert('t', 'm'), emitters.ROOM_SYSTEM_ALERTS),
        (lambda: emitters.on_discovery_scan_progress(1, 2, 3, 0), emitters.ROOM_SYSTEM_ALERTS),
    ])
    def test_emitters_target_their_scope(self, monkeypatch, fn, room):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        fn()
        ((args, kw),) = seen
        assert args[0] == 'event'
        assert kw['to'] == room

    def test_logout_by_keyword(self, monkeypatch):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        emitters.on_user_logout(username='x')
        ((args, kw),) = seen
        assert args[1]['type'] == 'user.logout'
        assert args[1]['data'] == {'username': 'x'}
        assert kw['to'] == emitters.ROOM_AUDIT

    @pytest.mark.parametrize('changes', [{'when': object()}, {'ratio': math.nan},
                                         {'ratio': math.inf}])
    def test_unserializable_payload(self, monkeypatch, caplog, changes):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        with caplog.at_level(logging.WARNING, logger='websocket.emitters'):
            emitters.on_ca_updated(1, 'ca', changes)  # does not raise
        assert seen == []
        assert any('Failed to emit' in r.getMessage() for r in caplog.records)
        with pytest.raises(WebSocketValidationError):
            events.emit_event('ca.updated', {'changes': changes}, room=emitters.ROOM_CAS)
        assert seen == []

    def test_transport_failure_is_logged_not_raised(self, monkeypatch, caplog):
        def boom(*a, **kw):
            raise ConnectionError('redis down')
        monkeypatch.setattr(socketio, 'emit', boom)
        with caplog.at_level(logging.WARNING, logger='websocket.events'):
            events.emit_event('ca.created', {'id': 1}, room=emitters.ROOM_CAS)
        assert any('redis down' in r.getMessage() for r in caplog.records)

    def test_emit_ws_event_without_room(self, monkeypatch, caplog):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        with caplog.at_level(logging.WARNING, logger='websocket.emitters'):
            emitters.emit_ws_event('ca.created', {'id': 1})
            emitters.emit_ws_event('ca.created', {'id': 1}, '')
        assert seen == []
        assert len([r for r in caplog.records if r.levelno == logging.WARNING]) == 2

    @pytest.mark.parametrize('room', [None, '', 7, b'scope:cas', 'global', 'scope:everything'])
    def test_base_emitter_needs_a_known_room(self, monkeypatch, room):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        with pytest.raises(WebSocketValidationError):
            events.emit_event('ca.created', {'id': 1}, room=room)
        assert seen == []

    @pytest.mark.parametrize('data', [None, [1], 'x'])
    def test_base_emitter_needs_a_dict(self, data):
        with pytest.raises(WebSocketValidationError):
            events.emit_event('ca.created', data, room=emitters.ROOM_CAS)

    @pytest.mark.parametrize('args', [
        ('maintenance', 'Down at noon', 'medium'),
        ('maintenance', 'Down at noon', None),
        ('', 'Down at noon', 'info'),
        ('maintenance', '', 'info'),
        ('maintenance', 5, 'info'),
    ])
    def test_system_alert_validation(self, monkeypatch, args):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        with pytest.raises(WebSocketValidationError):
            events.emit_system_alert(*args)
        assert seen == []

    def test_system_alert_positional(self, monkeypatch):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        events.emit_system_alert('maintenance', 'Down at noon', 'warning')
        ((args, kw),) = seen
        assert kw['to'] == emitters.ROOM_SYSTEM_ALERTS
        assert args[1]['data']['severity'] == 'warning'

    @pytest.mark.parametrize('args', [('', 'u', 'r'), ('a', None, 'r'), ('a', 'u', '  ')])
    def test_audit_critical_validation(self, args):
        with pytest.raises(WebSocketValidationError):
            events.emit_audit_critical(*args)

    @pytest.mark.parametrize('name', ['api-key', 'X-API-Key', 'pwd', 'PWD', 'auth', 'Auth',
                                      'bearer', 'Bearer_Token', 'jwt', 'JWT', 'csrf',
                                      'X-CSRF-Token'])
    def test_audit_critical_strips_secret_names(self, monkeypatch, name):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        events.emit_audit_critical('user.update', 'admin', 'user:4',
                                   {name: 'value', 'nested': {name: 'value', 'field': 'role'}})
        ((args, _),) = seen
        assert args[1]['data']['details'] == {'nested': {'field': 'role'}}

    def test_audit_critical_strips_secrets(self, monkeypatch):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        events.emit_audit_critical('user.update', 'admin', 'user:4', {
            'password': 'hunter2', 'api_key': 'ucm_abc', 'session_id': 's1',
            'private_key': 'k', 'request_body': '{"x":1}', 'traceback': 't',
            'note': '-----BEGIN PRIVATE KEY-----\nMII', 'err': 'Traceback (most recent call last):',
            'nested': {'token': 't', 'field': 'role'},
            'changed': ['role', 'email'],
        })
        ((args, _),) = seen
        assert args[1]['data']['details'] == {'nested': {'field': 'role'},
                                              'changed': ['role', 'email']}

    def test_emit_to_user_targets_the_personal_room(self, app, reader):
        ws, user_id = reader
        events.emit_to_user(user_id, 'user.updated', {'id': user_id})
        (event,) = _named(ws.get_received(), 'event')
        assert event['type'] == 'user.updated'
        with pytest.raises(WebSocketValidationError):
            events.emit_to_user('', 'user.updated', {})

    def test_scope_broadcast_accepts_only_scope_rooms(self, monkeypatch):
        seen = []
        monkeypatch.setattr(socketio, 'emit', lambda *a, **kw: seen.append((a, kw)))
        events.emit_to_scope(emitters.ROOM_CAS, 'ca.created', {'id': 1})
        with pytest.raises(WebSocketValidationError):
            events.emit_to_scope('cert:1', 'certificate.issued', {'id': 1})
        assert [kw['to'] for _, kw in seen] == [emitters.ROOM_CAS]


# ---------------------------------------------------------------- status and cleanup

class TestStatus:
    def test_info_holds_no_identifier(self, app, auth_client, reader):
        info = events.get_connected_clients_info()
        assert set(info) == {'count', 'local_worker_count', 'clients'}
        assert info['count'] == info['local_worker_count'] == len(events.connected_clients)
        for client in info['clients']:
            assert set(client) == {'connected_at', 'auth_method', 'room_count', 'privileged'}
            assert client['auth_method'] == 'session'
            assert isinstance(client['room_count'], int)
            assert isinstance(client['privileged'], bool)
        r = auth_client.get('/api/v2/websocket/clients')
        data = assert_success(r)
        assert data == info or set(data) == set(info)
        ws, user_id = reader
        text = r.get_data(as_text=True)
        for forbidden in (f'user:{user_id}', 'scope:', 'read:', 'user_id', 'username', 'sid'):
            assert forbidden not in text

    def test_status_counts_real_sockets(self, app, auth_client, make_user):
        def status():
            r = auth_client.get('/api/v2/websocket/status')
            return assert_success(r)['websocket']['connected_clients']

        base = status()
        user_id = make_user(role_perms=READER)
        with _socket(app, _session_client(app, user_id)), \
                _socket(app, _session_client(app, user_id)), \
                _socket(app, _session_client(app, user_id)):
            assert status() == base + 3
        assert status() == base

    def test_refused_sockets_are_not_counted(self, app):
        base = events.get_connected_clients_count()
        with _socket(app, _session_client(app)):
            assert events.get_connected_clients_count() == base

    def test_voluntary_disconnect_is_forgotten(self, app, make_user):
        user_id = make_user(role_perms=READER)
        ws = socketio.test_client(app, flask_test_client=_session_client(app, user_id))
        sid = _sid(ws)
        assert sid in events.connected_clients
        ws.disconnect()
        assert sid not in events.connected_clients

    def test_cut_forgets_the_socket_by_itself(self, reader, monkeypatch):
        ws, _ = reader
        sid = _sid(ws)
        closed = []
        monkeypatch.setattr(events, 'disconnect', closed.append)  # the handler never runs
        events._drop(sid, 'test')
        assert closed == [sid]
        assert sid not in events.connected_clients

    def test_forced_disconnect_is_forgotten(self, app, make_user, revalidate_now):
        user_id = make_user(role_perms=READER)
        client = _session_client(app, user_id)
        base = events.get_connected_clients_count()
        with _socket(app, client) as ws:
            assert events.get_connected_clients_count() == base + 1
            with app.app_context():
                db.session.get(User, user_id).active = False
                db.session.commit()
            ws.emit('ping')
            assert not ws.is_connected()
            assert events.get_connected_clients_count() == base

    def test_reauth_does_nothing_for_a_plain_reader(self, reader):
        ws, _ = reader
        ws.emit('reauth', {'token': 'x'})
        assert ws.get_received() == []
        assert ws.is_connected()


# ---------------------------------------------------------------- startup

class TestStartup:
    @pytest.fixture
    def init_kwargs(self, monkeypatch):
        calls = []
        monkeypatch.setattr(events.socketio, 'init_app', lambda *a, **kw: calls.append(kw))
        return calls

    @pytest.mark.parametrize('origins', [
        None, '*', ['*'], [' * '], ['https://ucm.test', '*'], [], 'https://ucm.test',
        ['ftp://ucm.test'], ['https://ucm.test/path'], ['ucm.test', 'https://'],
    ])
    def test_unusable_origins_refuse_to_start(self, app, monkeypatch, init_kwargs, origins):
        if origins is None:
            monkeypatch.delitem(app.config, 'CORS_ORIGINS', raising=False)
        else:
            monkeypatch.setitem(app.config, 'CORS_ORIGINS', origins)
        with pytest.raises(RuntimeError):
            events.init_websocket(app)
        assert init_kwargs == []

    def test_explicit_origins_are_passed_through(self, app, monkeypatch, init_kwargs):
        origins = ['https://ucm.test:8443', 'http://localhost:5173']
        monkeypatch.setitem(app.config, 'CORS_ORIGINS', origins)
        events.init_websocket(app)
        (kw,) = init_kwargs
        assert kw['cors_allowed_origins'] == origins
        assert kw['manage_session'] is False
        assert kw['async_mode'] == 'gevent'
        assert (kw['ping_timeout'], kw['ping_interval']) == (60, 25)

    def test_trailing_slashes_and_spaces_are_normalized(self, app, monkeypatch, init_kwargs):
        monkeypatch.setitem(app.config, 'CORS_ORIGINS',
                            ['https://pki.example.com/', ' https://b.test:8443// ',
                             'https://pki.example.com'])
        events.init_websocket(app)
        (kw,) = init_kwargs
        assert kw['cors_allowed_origins'] == ['https://pki.example.com', 'https://b.test:8443']

    @pytest.mark.parametrize('bad', ['https://ucm.test/path', 'ftp://ucm.test',
                                     'https://*.ucm.test', 'https://user:pw@ucm.test', 42])
    def test_invalid_entry_is_skipped_and_logged(self, app, monkeypatch, init_kwargs, caplog,
                                                 bad):
        monkeypatch.setitem(app.config, 'CORS_ORIGINS', ['https://ok.test', bad])
        with caplog.at_level(logging.WARNING, logger='websocket.events'):
            events.init_websocket(app)
        (kw,) = init_kwargs
        assert kw['cors_allowed_origins'] == ['https://ok.test']
        assert any(repr(bad) in r.getMessage() for r in caplog.records
                   if r.levelno == logging.WARNING)

    def test_real_start_with_mixed_origins(self, monkeypatch, caplog):
        # init_app rebinds the shared SocketIO object: keep what the test app relies on.
        for name in ('server', 'async_mode', 'manage_session', 'sockio_mw'):
            monkeypatch.setattr(socketio, name, getattr(socketio, name, None), raising=False)
        monkeypatch.setattr(socketio, 'server_options', dict(socketio.server_options))
        monkeypatch.setattr(events, '_message_queue', lambda _app: None)
        fresh = Flask('ws-origins')
        fresh.config['CORS_ORIGINS'] = ['https://pki.example.com/', 'https://bad.test/ucm',
                                        'gopher://x.test', 'https://ok.test']
        with caplog.at_level(logging.WARNING, logger='websocket.events'):
            assert events.init_websocket(fresh) is socketio
        assert sum('Ignoring invalid WebSocket origin' in r.getMessage()
                   for r in caplog.records) == 2
        client = fresh.test_client()

        def handshake(origin):
            return client.get('/socket.io/?EIO=4&transport=polling',
                              headers={'Origin': origin}).status_code

        assert handshake('https://pki.example.com') == 200
        assert handshake('https://ok.test') == 200
        assert handshake('https://bad.test') == 400
