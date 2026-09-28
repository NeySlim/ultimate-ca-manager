"""WebSocket handshake: session only, and a Redis message queue from REDIS_URL."""

import importlib.util

import pytest

from tests.conftest import assert_success
from websocket import events, socketio


@pytest.fixture
def api_key(auth_client):
    r = auth_client.post('/api/v2/account/apikeys', json={
        'name': 'ws-handshake',
        'permissions': ['read:certificates', 'read:cas'],
    })
    return assert_success(r, 201)['key']


class TestHandshake:
    def test_session_connects(self, app, auth_client):
        ws = socketio.test_client(app, flask_test_client=auth_client)
        try:
            assert ws.is_connected()
        finally:
            ws.disconnect()

    def test_no_session_is_refused(self, app):
        ws = socketio.test_client(app)
        assert not ws.is_connected()

    @pytest.mark.parametrize('field', ['token', 'api_key'])
    def test_api_key_in_auth_payload_is_refused(self, app, api_key, field):
        ws = socketio.test_client(app, auth={field: api_key})
        assert not ws.is_connected()

    def test_reauth_event_is_not_handled(self, app, auth_client):
        ws = socketio.test_client(app, flask_test_client=auth_client)
        try:
            ws.get_received()
            ws.emit('reauth', {'token': 'anything'})
            assert ws.get_received() == []
            assert ws.is_connected()
        finally:
            ws.disconnect()


class TestMessageQueue:
    def test_none_without_redis_url(self, monkeypatch):
        monkeypatch.delenv('REDIS_URL', raising=False)
        assert events._message_queue_url() is None

    def test_redis_url_when_library_present(self, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://cache:6379/0')
        monkeypatch.setattr(importlib.util, 'find_spec', lambda name: object())
        assert events._message_queue_url() == 'redis://cache:6379/0'

    def test_none_when_library_missing(self, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://cache:6379/0')
        monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None)
        assert events._message_queue_url() is None

    def test_init_passes_queue_to_socketio(self, app, monkeypatch):
        seen = {}
        monkeypatch.setattr(events, '_message_queue_url', lambda: 'redis://cache:6379/0')
        monkeypatch.setattr(events.socketio, 'init_app',
                            lambda _app, **kw: seen.update(kw))
        events.init_websocket(app)
        assert seen['message_queue'] == 'redis://cache:6379/0'
