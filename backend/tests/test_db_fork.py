"""A gunicorn worker never shares the master's PostgreSQL connections.

With preload_app the master opens connections before forking and its scheduler
keeps using them; a worker reusing one shared the socket, and the replies of
both processes interleaved (PGRES_TUPLES_OK without message, rows of another
query, an unhealthy container).
"""
import importlib.util
import logging
import os
import sys
import types
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
    module.post_worker_init(_worker())

    with app.app_context():
        assert order[0] == ('forget', list(db.engines.values()))
        assert bind in order[0][1] and db.engine in order[0][1]
    assert ('http', app) in order
