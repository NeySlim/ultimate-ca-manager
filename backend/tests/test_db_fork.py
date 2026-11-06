"""A gunicorn worker never shares the master's PostgreSQL connections.

With preload_app the master opens connections before forking and its scheduler
keeps using them; a worker reusing one shared the socket, and the replies of
both processes interleaved (PGRES_TUPLES_OK without message, rows of another
query, an unhealthy container).
"""
import importlib.util
import logging
import os
import signal
import sys
import time
import types
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from utils.db_fork import forget_inherited_connections

BACKEND = Path(__file__).resolve().parent.parent


def _backend_pid(engine):
    with engine.connect() as conn:
        return conn.execute(text('SELECT pg_backend_pid()')).scalar()


def _child_backend_pid(engine, reset):
    """Backend pid of the first query a forked child makes."""
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        try:
            os.close(read_fd)
            if reset:
                forget_inherited_connections([engine])
            os.write(write_fd, str(_backend_pid(engine)).encode())
        finally:
            os._exit(0)
    os.close(write_fd)
    os.waitpid(pid, 0)
    with os.fdopen(read_fd) as pipe:
        return int(pipe.read())


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
@pytest.mark.parametrize('reset', [False, True], ids=['inherited', 'forgotten'])
def test_a_forked_child_gets_its_own_connection(reset):
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    try:
        parent = _backend_pid(engine)  # the connection goes back to the pool
        child = _child_backend_pid(engine, reset)
        if reset:
            assert child != parent
        else:
            assert child == parent  # the shared socket the hook exists to avoid
        # The parent's connection survives the child: never closed under it
        assert _backend_pid(engine) == parent
    finally:
        engine.dispose()


def test_every_engine_is_forgotten(tmp_path):
    engines = [create_engine(f'sqlite:///{tmp_path}/{name}.db') for name in ('default', 'bind')]
    pools = [engine.pool for engine in engines]
    forget_inherited_connections(engines)
    assert all(engine.pool is not pool for engine, pool in zip(engines, pools))


def _load_gunicorn_config(monkeypatch, app):
    import gevent
    import gevent.monkey

    monkeypatch.setattr(gevent.monkey, 'patch_all', lambda *a, **k: None)
    monkeypatch.delenv('UCM_SCHEDULER_IN_WORKER', raising=False)  # set by the config
    spec = importlib.util.spec_from_file_location('_ucm_gunicorn_config_fork',
                                                  BACKEND / 'gunicorn_config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    wsgi = types.ModuleType('wsgi')
    wsgi.app = app
    monkeypatch.setitem(sys.modules, 'wsgi', wsgi)
    monkeypatch.setattr(gevent, 'get_hub', lambda: types.SimpleNamespace(handle_error=None))
    return module


def _worker():
    return types.SimpleNamespace(cfg=types.SimpleNamespace(graceful_timeout=30),
                                 log=logging.getLogger('test.worker'))


def test_post_worker_init_forgets_the_inherited_pool_first(app, monkeypatch, tmp_path):
    import protocol_http_server
    from models import db
    import utils.db_fork

    module = _load_gunicorn_config(monkeypatch, app)
    bind = create_engine(f'sqlite:///{tmp_path}/bind.db')
    monkeypatch.setitem(db._app_engines[app], 'extra_bind', bind)

    order = []
    monkeypatch.setattr(utils.db_fork, 'forget_inherited_connections',
                        lambda engines: order.append(('forget', list(engines))))
    monkeypatch.setattr(protocol_http_server, 'start_http_protocol_server',
                        lambda a, **kw: order.append(('http', a)))
    monkeypatch.setattr('services.scheduler_service.start_scheduler',
                        lambda a, in_worker=False: order.append(('scheduler', a, in_worker)))
    monkeypatch.setattr('services.syslog_service.syslog_forwarder.forget_inherited_socket',
                        lambda: order.append(('syslog',)))
    module.post_worker_init(_worker())

    with app.app_context():
        assert order[0] == ('forget', list(db.engines.values()))
        assert bind in order[0][1] and db.engine in order[0][1]
    assert ('http', app) in order
    assert ('scheduler', app, True) in order
    assert order.index(('syslog',)) < order.index(('http', app))  # before anything can log


def test_under_gunicorn_the_master_leaves_the_loop_to_a_worker(app, monkeypatch):
    _load_gunicorn_config(monkeypatch, app)
    assert os.environ.get('UCM_SCHEDULER_IN_WORKER') == '1'


def test_a_worker_told_to_exit_hands_the_scheduler_over(monkeypatch):
    import gevent
    from services import scheduler_service
    from workers import MTLSGeventWebSocketWorker

    scheduler = scheduler_service.SchedulerService()
    scheduler._running = True
    monkeypatch.setattr(scheduler_service, '_scheduler', scheduler)
    monkeypatch.setattr(gevent, 'spawn', lambda fn, *a: fn(*a))
    worker = object.__new__(MTLSGeventWebSocketWorker)
    worker.alive = True
    worker.handle_exit(signal.SIGTERM, None)
    assert worker.alive is False
    assert scheduler._running is False and scheduler._wake.is_set()


def _fork_scheduler(sched, prepare=None):
    """A forked child that starts ``sched`` the way post_worker_init does, then idles."""
    pid = os.fork()
    if pid == 0:
        try:
            if prepare:
                prepare()
            sched.start()
            while True:
                time.sleep(1)
        finally:
            os._exit(0)
    return pid


def _runs(path):
    return [int(line) for line in path.read_text().split()] if path.exists() else []


def _wait_for(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _reap(*pids):
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except (ProcessLookupError, ChildProcessError):
            pass


def _recording_scheduler(log, record):
    from services.scheduler_service import SchedulerService

    sched = SchedulerService(wake_interval=0.1)

    def task():
        with open(log, 'a') as handle:
            handle.write(f'{record()}\n')
    sched.register_task('record', task, interval=0)
    sched.tasks['record']._created_at -= timedelta(seconds=60)  # past the first-run grace
    return sched


def test_one_forked_worker_runs_the_scheduler_and_another_takes_over(tmp_path, monkeypatch):
    from services import scheduler_service

    monkeypatch.setattr('config.settings.DATA_DIR', str(tmp_path), raising=False)
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', 0.2)
    log = tmp_path / 'runs'
    sched = _recording_scheduler(log, os.getpid)  # registered, never started, like the master

    first = _fork_scheduler(sched)
    second = _fork_scheduler(sched)
    try:
        assert _wait_for(lambda: len(_runs(log)) >= 3, 10)
        elected = set(_runs(log))
        assert len(elected) == 1 and elected <= {first, second}
        assert os.getpid() not in elected
        holder = elected.pop()
        other = second if holder == first else first

        os.kill(holder, signal.SIGKILL)
        os.waitpid(holder, 0)
        killed_at = time.monotonic()
        assert _wait_for(lambda: other in _runs(log), 5)
        assert time.monotonic() - killed_at < 2  # a dead holder frees the lock at once
    finally:
        _reap(first, second)


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_the_scheduled_tasks_never_run_on_the_masters_connection(tmp_path, monkeypatch):
    from services import scheduler_service

    monkeypatch.setattr('config.settings.DATA_DIR', str(tmp_path), raising=False)
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    try:
        master = _backend_pid(engine)
        log = tmp_path / 'runs'
        sched = _recording_scheduler(log, lambda: _backend_pid(engine))
        # The master holds a connection of its own across the fork, as a request would
        with engine.connect() as borrowed:
            held = borrowed.execute(text('SELECT pg_backend_pid()')).scalar()
            child = _fork_scheduler(sched, prepare=lambda: forget_inherited_connections([engine]))
            try:
                assert _wait_for(lambda: len(_runs(log)) >= 2, 10)
            finally:
                _reap(child)
        assert not set(_runs(log)) & {master, held}
        assert _backend_pid(engine) == master  # the master's pool survived the child
    finally:
        engine.dispose()


class _SyslogCollector:
    """A TCP syslog server recording what each connection carried."""

    def __init__(self):
        import socket
        import threading

        self.listener = socket.create_server(('127.0.0.1', 0))
        self.port = self.listener.getsockname()[1]
        self.streams = []
        self.closed = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        import threading
        while True:
            try:
                conn, _ = self.listener.accept()
            except OSError:
                return
            index = len(self.streams)
            self.streams.append(b'')
            threading.Thread(target=self._read, args=(conn, index), daemon=True).start()

    def _read(self, conn, index):
        while True:
            data = conn.recv(65536)
            if not data:
                self.closed.append(index)
                return
            self.streams[index] += data

    def close(self):
        self.listener.close()


def _audit(action):
    return types.SimpleNamespace(success=True, timestamp=None, action=action, username=None,
                                 ip_address=None, resource_type='system', resource_id=None,
                                 resource_name=None, details=action)


@pytest.mark.parametrize('explicit', [True, False], ids=['post_worker_init', 'first_frame'])
def test_a_forked_worker_opens_its_own_syslog_connection(explicit):
    from services.syslog_service import SyslogForwarder

    collector = _SyslogCollector()
    forwarder = object.__new__(SyslogForwarder)
    forwarder._initialize()
    forwarder.configure(enabled=True, host='127.0.0.1', port=collector.port, protocol='tcp')
    try:
        assert forwarder.send(_audit('master-before'))
        assert _wait_for(lambda: b'master-before' in b''.join(collector.streams), 5)
        pid = os.fork()
        if pid == 0:
            try:
                if explicit:
                    forwarder.forget_inherited_socket()
                forwarder.send(_audit('worker'))
            finally:
                os._exit(0)
        os.waitpid(pid, 0)
        assert forwarder.send(_audit('master-after'))
        assert _wait_for(lambda: len(collector.streams) == 2
                         and b'master-after' in collector.streams[0], 5)
        master, worker = collector.streams
        assert b'worker' in worker and b'worker' not in master
        assert 0 not in collector.closed  # the worker sent no FIN on the master's stream
    finally:
        forwarder._close()
        collector.close()
