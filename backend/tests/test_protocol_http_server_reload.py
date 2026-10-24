"""The HTTP protocol server (CDP/OCSP) survives `systemctl reload`: gunicorn
starts the new worker while the old one still holds the port."""
import errno
import importlib.util
import logging
import socket
import sys
import types
from pathlib import Path

import pytest

import protocol_http_server as phs
from listen_address import get_bind_host

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def blocker():
    """A listening socket on a free port, standing for the old worker."""
    host = get_bind_host()
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    sock.bind((host, 0))
    sock.listen(1)
    yield sock
    sock.close()


@pytest.fixture
def clean(monkeypatch):
    monkeypatch.setattr(phs, '_server', None)
    yield
    if phs._server is not None:
        phs._server.stop()


@pytest.fixture
def fake_time(monkeypatch):
    """Synchronous spawn and a clock that advances by what is slept."""
    state = {'now': 0.0, 'slept': [], 'on_sleep': None, 'spawned': 0}

    def _sleep(seconds):
        state['slept'].append(seconds)
        assert len(state['slept']) < 100, 'the retry never stops'
        state['now'] += seconds
        if state['on_sleep']:
            state['on_sleep']()

    def _spawn(fn, *args):
        state['spawned'] += 1
        return fn(*args)

    monkeypatch.setattr(phs, '_sleep', _sleep)
    monkeypatch.setattr(phs, '_spawn', _spawn)
    monkeypatch.setattr(phs, '_clock', lambda: state['now'])
    return state


def _port_is_held(port):
    host = get_bind_host()
    family = socket.AF_INET6 if ':' in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((host, port))
        except OSError as e:
            return e.errno == errno.EADDRINUSE
    return False


def test_busy_port_is_bound_once_the_old_worker_lets_go(app, blocker, clean, fake_time):
    port = blocker.getsockname()[1]
    calls = []

    def release():
        calls.append(1)
        if len(calls) == 2:
            blocker.close()

    fake_time['on_sleep'] = release
    assert phs.start_http_protocol_server(app, port=port, error_after=35) is None
    assert fake_time['spawned'] == 1
    assert phs._server is not None and phs._server.address[1] == port
    assert _port_is_held(port)
    assert fake_time['slept'] == [0.25, 0.5]


def test_without_retry_a_busy_port_fails_at_once(app, blocker, clean, fake_time):
    port = blocker.getsockname()[1]
    assert phs.start_http_protocol_server(app, port=port) is None
    assert fake_time['spawned'] == 0
    assert phs._server is None


def test_retry_outlives_the_deadline_and_reports_once(app, blocker, clean, fake_time, caplog):
    """The old worker can take longer than graceful_timeout to exit."""
    port = blocker.getsockname()[1]

    reported_at = []

    def release_late():
        if not reported_at and 'still busy' in caplog.text:
            reported_at.append(fake_time['now'])
        if fake_time['now'] >= 60:
            blocker.close()

    fake_time['on_sleep'] = release_late
    with caplog.at_level(logging.ERROR, logger='protocol_http_server'):
        phs.start_http_protocol_server(app, port=port, error_after=35)
    assert phs._server is not None and phs._server.address[1] == port
    assert max(fake_time['slept']) == 1.0
    assert caplog.text.count('still busy after 35s') == 1
    assert reported_at[0] >= 35


def test_other_bind_error_during_the_retry_stops_it(app, clean, fake_time, monkeypatch, caplog):
    errors = [OSError(errno.EADDRINUSE, 'busy'), PermissionError(errno.EACCES, 'denied')]

    def bind(*_a):
        raise errors.pop(0)

    monkeypatch.setattr(phs, '_bind', bind)
    with caplog.at_level(logging.ERROR, logger='protocol_http_server'):
        assert phs.start_http_protocol_server(app, port=8080, error_after=35) is None
    assert fake_time['slept'] == [0.25]
    assert phs._server is None
    assert 'Cannot start HTTP protocol server' in caplog.text


def test_other_bind_errors_are_not_retried(app, clean, fake_time, monkeypatch):
    def denied(*_a):
        raise PermissionError(errno.EACCES, 'Permission denied')

    monkeypatch.setattr(phs, '_bind', denied)
    assert phs.start_http_protocol_server(app, port=80, error_after=35) is None
    assert fake_time['spawned'] == 0


@pytest.fixture
def gunicorn_conf(app, monkeypatch):
    """gunicorn_config.py loaded without monkey patching this process."""
    import gevent
    import gevent.monkey

    monkeypatch.setattr(gevent.monkey, 'patch_all', lambda *a, **k: None)
    spec = importlib.util.spec_from_file_location('_ucm_gunicorn_config_reload',
                                                  BACKEND / 'gunicorn_config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wsgi = types.ModuleType('wsgi')
    wsgi.app = app
    monkeypatch.setitem(sys.modules, 'wsgi', wsgi)
    # post_worker_init replaces the handle_error of the hub: use a stand-in hub
    monkeypatch.setattr(gevent, 'get_hub', lambda: types.SimpleNamespace(handle_error=None))
    calls = []
    monkeypatch.setattr(phs, 'start_http_protocol_server',
                        lambda a, **kw: calls.append((a, kw)))
    return module, calls


@pytest.mark.parametrize('graceful, expected', [(30, 35.0), (60, 65.0)])
def test_post_worker_init_reports_after_the_graceful_timeout(gunicorn_conf, app, graceful, expected):
    module, calls = gunicorn_conf
    worker = types.SimpleNamespace(cfg=types.SimpleNamespace(graceful_timeout=graceful),
                                   log=logging.getLogger('test.worker'))
    module.post_worker_init(worker)
    assert calls[0] == (app, {'error_after': expected})
