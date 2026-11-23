"""SQLite in WAL, web server: a statement that meets another writer's lock waits in Python
(a few ms in sqlite3's busy handler, then sleeps that yield), never loops on a stale snapshot,
and never runs again once it wrote rows. Outside the web server sqlite3 waits in C."""
import sqlite3
import threading
import time
import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError

from utils import sqlite_wait


@pytest.fixture
def wal_engine(app, tmp_path):
    path = tmp_path / 'wal.db'
    conn = sqlite3.connect(path)
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('CREATE TABLE t (v INTEGER)')
    conn.commit()
    conn.close()
    sqlite_wait.install()
    engine = create_engine(f'sqlite:///{path}')
    yield engine, str(path)
    engine.dispose()


def _writer(path):
    # Committed from a timer's thread
    other = sqlite3.connect(path, timeout=0, isolation_level=None, check_same_thread=False)
    other.execute('BEGIN IMMEDIATE')
    other.execute('INSERT INTO t VALUES (100)')
    return other


def test_a_request_waits_for_another_writer_in_python_then_writes(app, wal_engine):
    engine, path = wal_engine
    other = _writer(path)
    release = threading.Timer(0.6, lambda: other.execute('COMMIT'))
    with app.test_request_context():
        with engine.connect() as conn:
            # sqlite3's own wait is cut to a few ms: the rest of the wait is Python's
            assert conn.exec_driver_sql('PRAGMA busy_timeout').scalar() == sqlite_wait.IN_C_MS
            started = time.monotonic()
            release.start()
            conn.exec_driver_sql('INSERT INTO t VALUES (1)')
            conn.commit()
            took = time.monotonic() - started
    release.join()
    other.close()
    assert 0.5 < took < 3, took
    check = sqlite3.connect(path)
    assert sorted(v for (v,) in check.execute('SELECT v FROM t')) == [1, 100]
    check.close()


def _locked_for(path, seconds):
    other = _writer(path)
    release = threading.Timer(seconds, lambda: other.execute('ROLLBACK'))
    release.start()
    return other, release


def test_a_lock_met_late_in_a_request_still_has_the_wait_left(app, wal_engine, monkeypatch):
    """The budget is the time the request spent waiting, not a window from its first lock."""
    monkeypatch.setattr(sqlite_wait, 'WEB_LOCK_WAIT_SECONDS', 1.0)
    engine, path = wal_engine
    with app.test_request_context():
        with engine.connect() as conn:
            other, release = _locked_for(path, 0.1)
            conn.exec_driver_sql('INSERT INTO t VALUES (1)')
            conn.commit()
            release.join()
            other.close()
            time.sleep(1.2)  # past a window opened by the first lock
            other, release = _locked_for(path, 0.3)
            started = time.monotonic()
            conn.exec_driver_sql('INSERT INTO t VALUES (2)')
            conn.commit()
            took = time.monotonic() - started
            release.join()
            other.close()
    assert 0.2 < took < 1.0, took


def test_the_waits_of_a_request_add_up_to_its_budget(app, wal_engine, monkeypatch):
    monkeypatch.setattr(sqlite_wait, 'WEB_LOCK_WAIT_SECONDS', 1.0)
    engine, path = wal_engine
    with app.test_request_context():
        with engine.connect() as conn:
            other, release = _locked_for(path, 0.6)
            conn.exec_driver_sql('INSERT INTO t VALUES (1)')
            conn.commit()
            release.join()
            other.close()
            other, release = _locked_for(path, 3)
            started = time.monotonic()
            with pytest.raises(OperationalError):
                conn.exec_driver_sql('INSERT INTO t VALUES (2)')
            took = time.monotonic() - started
            conn.rollback()
            release.cancel()
            other.execute('ROLLBACK')
            other.close()
    # About 0.4 s left of the second's budget, never a fresh second
    assert 0.15 < took < 0.75, took


def test_outside_the_web_server_sqlite3_waits_in_c(app, wal_engine):
    engine, _ = wal_engine
    with engine.connect() as conn:
        assert conn.exec_driver_sql('PRAGMA busy_timeout').scalar() == 5000


def test_a_stale_snapshot_is_never_retried(app, wal_engine):
    """A transaction that read, then wants to write after another writer committed, gets
    SQLITE_BUSY_SNAPSHOT: it fails at once (503 BUSY), not after the request's whole wait."""
    engine, path = wal_engine
    other = sqlite3.connect(path, isolation_level=None)
    with app.test_request_context():
        with engine.connect() as conn:
            conn.exec_driver_sql('BEGIN')
            assert conn.exec_driver_sql('SELECT COUNT(*) FROM t').scalar() == 0
            other.execute('INSERT INTO t VALUES (2)')
            started = time.monotonic()
            with pytest.raises(OperationalError) as caught:
                conn.exec_driver_sql('INSERT INTO t VALUES (3)')
            took = time.monotonic() - started
            conn.rollback()
        refused = sqlite_wait.locked_refusal(caught.value)
    other.close()
    assert sqlite_wait.is_busy_snapshot(caught.value)
    assert took < 0.5, f'retried a stale snapshot for {took:.1f}s'
    assert refused.status_code == 503 and refused.headers['Retry-After']
    assert sqlite_wait.BUSY_MESSAGE in refused.get_data(as_text=True)


class _Cursor:
    """An executemany whose first call writes `written` rows, then meets the lock."""

    def __init__(self, written):
        self.connection = types.SimpleNamespace(total_changes=0)
        self.calls, self._written = 0, written

    def executemany(self, statement, parameters):
        self.calls += 1
        if self.calls == 1:
            self.connection.total_changes += self._written
            raise sqlite3.OperationalError('database is locked')


def _context():
    info = {sqlite_wait._WAL: True}
    return types.SimpleNamespace(dialect=types.SimpleNamespace(name='sqlite'),
                                 root_connection=types.SimpleNamespace(
                                     connection=types.SimpleNamespace(info=info)))


@pytest.mark.parametrize('written, retried', [(0, True), (2, False)])
def test_an_executemany_that_wrote_rows_is_never_run_again(app, written, retried):
    cursor = _Cursor(written)
    with app.test_request_context():
        if retried:
            assert sqlite_wait._do_executemany(cursor, 'INSERT', [(1,), (2,), (3,)], _context())
        else:
            with pytest.raises(sqlite3.OperationalError):
                sqlite_wait._do_executemany(cursor, 'INSERT', [(1,), (2,), (3,)], _context())
    assert cursor.calls == (2 if retried else 1)
