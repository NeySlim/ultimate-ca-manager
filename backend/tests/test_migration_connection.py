"""The runner's PostgreSQL session: the keepalives of the application pool, and a statement whose
client was killed is stopped by the server within seconds, its locks with it."""
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

import migration_runner

BACKEND = Path(__file__).resolve().parent.parent
PG_URL = os.getenv('UCM_TEST_PG_URL')
_PG = 'postgresql://u:p@db.invalid/ucm'


class _Refused(Exception):
    pass


@pytest.mark.parametrize('call', [
    lambda: migration_runner.run_all_migrations(),
    lambda: migration_runner.mark_all_applied(),
    lambda: migration_runner.show_status(),
    lambda: migration_runner.mark_node_stopped('n1'),
    lambda: migration_runner._full_stop_holders_now(),
])
def test_every_runner_engine_has_the_pool_keepalives(monkeypatch, call):
    seen = []

    def record(url, **kwargs):
        seen.append(kwargs)
        raise _Refused()
    monkeypatch.setenv('DATABASE_URL', _PG)
    from config.settings import Config
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.delenv('UCM_PG_PREPARE_THRESHOLD', raising=False)
    monkeypatch.setattr(migration_runner, 'create_engine', record)
    try:
        call()
    except (_Refused, SystemExit):
        pass
    assert seen, 'no engine created'
    args = seen[0]['connect_args']
    assert args['keepalives'] == 1 and args['keepalives_idle'] == 30 and args['connect_timeout'] == 10


def test_sqlite_gets_no_postgresql_argument(monkeypatch):
    seen = []
    monkeypatch.setattr(migration_runner, 'create_engine', lambda url, **kw: seen.append(kw) or _Refused())
    migration_runner._engine('sqlite:////nowhere/ucm.db')
    assert 'connect_args' not in seen[0]


_KILLED = """
import sys
from sqlalchemy import text
import migration_runner
engine = migration_runner._engine(sys.argv[1])
with engine.connect() as conn:
    conn.execute(text("SET application_name = :n"), {"n": sys.argv[2]})
    conn.execute(text("SELECT pg_sleep(600)"))
"""


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_a_killed_migration_session_ends_on_the_server_within_seconds():
    from sqlalchemy import create_engine, text
    name = f'ucm-killed-{uuid.uuid4().hex[:8]}'
    child = subprocess.Popen([sys.executable, '-c', _KILLED, PG_URL, name], cwd=BACKEND)
    watcher = create_engine(PG_URL)
    query = text("SELECT count(*) FROM pg_stat_activity WHERE application_name = :n")
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            with watcher.connect() as conn:
                if conn.execute(text("SELECT count(*) FROM pg_stat_activity WHERE application_name = :n "
                                     "AND query LIKE '%pg_sleep%'"), {'n': name}).scalar():
                    break
            time.sleep(0.2)
        else:
            pytest.fail('the child session never started its statement')
        os.kill(child.pid, signal.SIGKILL)
        child.wait()
        killed = time.monotonic()
        # Without a check of the client the server would run the statement its 600 s through
        while time.monotonic() - killed < 30:
            with watcher.connect() as conn:
                if conn.execute(query, {'n': name}).scalar() == 0:
                    return
            time.sleep(0.5)
        pytest.fail('the session of the killed process still runs 30 s later')
    finally:
        if child.poll() is None:
            child.kill()
        with watcher.connect() as conn:
            conn.execute(text("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE application_name = :n"),
                         {'n': name})
        watcher.dispose()
