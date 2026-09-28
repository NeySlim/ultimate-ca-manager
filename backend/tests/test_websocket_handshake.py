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
    @pytest.fixture
    def redis_present(self, monkeypatch):
        monkeypatch.setattr(importlib.util, 'find_spec', lambda name: object())

    @pytest.fixture
    def built(self, monkeypatch):
        calls = []

        class FakeManager:
            def __init__(self, url, **kw):
                calls.append((url, kw))

        monkeypatch.setattr(events.socketio_pkg, 'RedisManager', FakeManager)
        return calls

    def test_none_without_redis_url(self, app, monkeypatch):
        monkeypatch.delenv('REDIS_URL', raising=False)
        monkeypatch.delenv('UCM_REDIS_URL', raising=False)
        assert events._message_queue(app) is None

    def test_none_when_library_missing(self, app, monkeypatch):
        monkeypatch.setenv('REDIS_URL', 'redis://cache:6379/0')
        monkeypatch.setattr(importlib.util, 'find_spec', lambda name: None)
        assert events._message_queue(app) is None

    @pytest.mark.parametrize('url', ['amqp://cache:5672/', 'redis+sentinel://s1:26379/0/ucm'])
    def test_unsupported_scheme_stays_local(self, app, monkeypatch, redis_present, built, url):
        monkeypatch.setenv('REDIS_URL', url)
        assert events._message_queue(app) is None
        assert built == []

    @pytest.mark.parametrize('url', [
        'redis://cache:6379/0', 'rediss://cache:6380/0',
        'unix:///run/redis/redis.sock',
    ])
    def test_manager_bounds_connect_time(self, app, monkeypatch, redis_present, built, url):
        monkeypatch.setenv('REDIS_URL', url)
        assert events._message_queue(app) is not None
        (seen_url, kw), = built
        assert seen_url == url
        assert kw['redis_options']['socket_connect_timeout'] == 2
        assert kw['redis_options']['socket_keepalive'] is True

    def test_legacy_variable_name_is_read(self, app, monkeypatch, redis_present, built):
        monkeypatch.delenv('REDIS_URL', raising=False)
        monkeypatch.setenv('UCM_REDIS_URL', 'redis://cache:6379/0')
        assert events._message_queue(app) is not None

    @pytest.mark.parametrize('url,db', [
        ('redis://cache:6379', '0'),
        ('redis://cache:6379/1', '1'),
        ('rediss://:secret@cache:6380/4', '4'),
        ('unix:///run/redis/redis.sock?db=2', '2'),
    ])
    def test_channel_follows_database(self, url, db):
        assert events._queue_channel(url, 'ucm:session:') == f'ucm:session:socketio:{db}'

    def test_instances_on_other_databases_do_not_share_events(self):
        a = events._queue_channel('redis://cache:6379/0', 'ucm:session:')
        b = events._queue_channel('redis://cache:6379/1', 'ucm:session:')
        assert a != b

    def test_init_passes_manager_to_socketio(self, app, monkeypatch):
        seen = {}
        manager = object()
        monkeypatch.setattr(events, '_message_queue', lambda _app: manager)
        monkeypatch.setattr(events.socketio, 'init_app',
                            lambda _app, **kw: seen.update(kw))
        events.init_websocket(app)
        assert seen['client_manager'] is manager


class TestRedisUrl:
    def test_prefers_redis_url(self, monkeypatch):
        from config.settings import redis_url
        monkeypatch.setenv('REDIS_URL', 'redis://a:6379/0')
        monkeypatch.setenv('UCM_REDIS_URL', 'redis://b:6379/0')
        assert redis_url() == 'redis://a:6379/0'

    def test_falls_back_to_documented_name(self, monkeypatch):
        from config.settings import redis_url
        monkeypatch.delenv('REDIS_URL', raising=False)
        monkeypatch.setenv('UCM_REDIS_URL', 'redis://b:6379/0')
        assert redis_url() == 'redis://b:6379/0'

    def test_readiness_ignores_skipped_redis_check(self, client, monkeypatch):
        import api.health_routes as health
        monkeypatch.setenv('REDIS_URL', 'redis://cache:6379/0')
        monkeypatch.setattr(health, '_check_redis',
                            lambda url: {'status': 'skipped'})
        r = client.get('/api/v2/health/ready')
        assert r.status_code == 200, r.data
