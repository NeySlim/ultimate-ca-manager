"""`migration_runner.py check`: the package scripts ask the 3.0 runner whether it starts on a database.

One exit code per answer (startable, fresh, refused by the pivot, unreadable, naming
migrations this release does not know), the backend on
the first line of stdout, and nothing written: the probe runs as root over another release's data.
"""
import hashlib
import os
import pathlib
import shutil
import socket
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

BACKEND = pathlib.Path(__file__).resolve().parent.parent
_PG_URL = os.environ.get('UCM_TEST_PG_URL')
_needs_pg = pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')

STARTABLE, FRESH, REFUSED, UNREADABLE, UNKNOWN = 0, 3, 4, 5, 6


def _check(url=None, path=None):
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    if url is not None:
        env['DATABASE_URL'] = url
    if path is not None:
        env['DATABASE_PATH'] = str(path)
    out = subprocess.run([sys.executable, 'migration_runner.py', 'check'], cwd=BACKEND, env=env,
                         capture_output=True, text=True, timeout=60)
    return out.returncode, out.stdout.splitlines()


def _pivot_names():
    sys.path.insert(0, str(BACKEND))
    from migrations._from_2_254 import PIVOT_NAMES
    return sorted(PIVOT_NAMES)


def _sqlite(path, registry, users=True):
    conn = sqlite3.connect(path)
    if users:
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    if registry is not None:
        conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
        conn.executemany('INSERT INTO _migrations (name) VALUES (?)', [(n,) for n in registry])
    conn.commit()
    conn.close()


def _fingerprint(directory):
    return {p.name: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
            for p in sorted(directory.iterdir())}


def _registry(kind):
    names = _pivot_names()
    return {
        '2.254': names,
        '3.0': names + ['300_upgrade_from_2_254'],
        'short': [n for n in names if n != '001_fix_dn_format'],
        'later': names + ['300_upgrade_from_2_254', '999_from_the_future'],
        'short-and-later': [n for n in names if n != '001_fix_dn_format'] + ['999_from_the_future'],
    }[kind]


class TestSQLite:
    def test_a_missing_file_is_fresh_and_is_not_created(self, tmp_path):
        db = tmp_path / 'ucm.db'
        code, lines = _check(path=db)
        assert code == FRESH
        assert lines[0] == f'sqlite {db}'
        assert list(tmp_path.iterdir()) == []

    def test_database_url_wins_over_database_path(self, tmp_path):
        db = tmp_path / 'other.db'
        _sqlite(db, None)
        code, lines = _check(url=f'sqlite:///{db}', path=tmp_path / 'ucm.db')
        assert (code, lines[0]) == (REFUSED, f'sqlite {db}')

    def test_an_empty_file_is_fresh(self, tmp_path):
        db = tmp_path / 'ucm.db'
        db.write_bytes(b'')
        assert _check(path=db)[0] == FRESH

    @pytest.mark.parametrize('kind', ['2.254', '3.0'])
    def test_a_2_254_or_3_0_database_is_startable(self, tmp_path, kind):
        db = tmp_path / 'ucm.db'
        _sqlite(db, _registry(kind))
        assert _check(path=db)[0] == STARTABLE

    @pytest.mark.parametrize('kind, reason', [
        ('short', '001_fix_dn_format'), (None, 'it has no migration registry')])
    def test_what_the_pivot_refuses_is_refused_with_its_reason(self, tmp_path, kind, reason):
        db = tmp_path / 'ucm.db'
        _sqlite(db, _registry(kind) if kind else None)
        code, lines = _check(path=db)
        assert code == REFUSED
        assert reason in ' '.join(lines[1:])

    @pytest.mark.parametrize('kind', ['later', 'short-and-later'])
    def test_a_registry_naming_unknown_migrations_has_its_own_code(self, tmp_path, kind):
        """A later release (or a hand edit) wrote it: never answered as older than 2.254."""
        db = tmp_path / 'ucm.db'
        _sqlite(db, _registry(kind))
        code, lines = _check(path=db)
        assert (code, lines[0]) == (UNKNOWN, f'sqlite {db}')
        assert '999_from_the_future' in ' '.join(lines[1:])

    def test_a_file_that_is_not_a_database_is_unreadable(self, tmp_path):
        db = tmp_path / 'ucm.db'
        db.write_bytes(b'this is not an SQLite database, it is long enough to have a header\n' * 4)
        assert _check(path=db)[0] == UNREADABLE

    def test_a_directory_in_place_of_the_file_is_unreadable(self, tmp_path):
        (tmp_path / 'ucm.db').mkdir()
        assert _check(path=tmp_path / 'ucm.db')[0] == UNREADABLE

    @pytest.mark.parametrize('kind', ['short', '3.0'])
    def test_the_probe_writes_nothing(self, tmp_path, kind):
        db = tmp_path / 'ucm.db'
        _sqlite(db, _registry(kind))
        before = _fingerprint(tmp_path)
        _check(path=db)
        assert _fingerprint(tmp_path) == before


    @pytest.mark.parametrize('directory', ['plain', 'hash#x', 'q?x', 'pct%41x'])
    @pytest.mark.parametrize('kind, code', [('short', REFUSED), ('2.254', STARTABLE)])
    def test_a_directory_name_a_url_would_cut_or_decode_gets_the_same_verdict(
            self, tmp_path, directory, kind, code):
        """Read in place by its path, never through a URL parsed again: the same verdict as
        an ordinary directory, and no file created anywhere."""
        db = tmp_path / directory / 'ucm.db'
        db.parent.mkdir()
        _sqlite(db, _registry(kind))
        before = sorted(str(p) for p in tmp_path.rglob('*'))
        assert _check(path=db)[0] == code
        assert sorted(str(p) for p in tmp_path.rglob('*')) == before

    def test_rows_still_in_the_write_ahead_log_are_read_without_writing_beside_it(self, tmp_path):
        """A -wal left by a stopped service holds committed rows: read, and no -shm appears."""
        live = tmp_path / 'live'
        left = tmp_path / 'left'
        live.mkdir()
        left.mkdir()
        conn = sqlite3.connect(live / 'ucm.db')
        conn.execute('PRAGMA journal_mode=WAL')
        conn.execute('PRAGMA wal_autocheckpoint=0')
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
        conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
        conn.commit()
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        conn.executemany('INSERT INTO _migrations (name) VALUES (?)',
                         [(n,) for n in _registry('2.254')])
        conn.commit()
        shutil.copy(live / 'ucm.db', left / 'ucm.db')
        shutil.copy(live / 'ucm.db-wal', left / 'ucm.db-wal')
        conn.close()
        before = _fingerprint(left)
        assert _check(path=left / 'ucm.db')[0] == STARTABLE
        assert _fingerprint(left) == before


def _left_by(tmp_path, mode, journal):
    """A 2.254 database as a stopped service left it: journal 'absent' (closed cleanly), 'empty'
    (a zero-length -wal or -journal), or 'holding rows' (a -wal with committed frames)."""
    live, left = tmp_path / 'live', tmp_path / 'left'
    live.mkdir()
    left.mkdir()
    conn = sqlite3.connect(live / 'ucm.db')
    conn.execute(f'PRAGMA journal_mode={mode}')
    conn.execute('PRAGMA wal_autocheckpoint=0')
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY)')
    conn.execute('CREATE TABLE _migrations (id INTEGER PRIMARY KEY, name TEXT UNIQUE)')
    conn.commit()
    if mode == 'WAL':
        conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.executemany('INSERT INTO _migrations (name) VALUES (?)', [(n,) for n in _registry('2.254')])
    conn.commit()
    if journal == 'holding rows':
        for f in live.iterdir():
            shutil.copy(f, left / f.name)
    conn.close()
    if journal != 'holding rows':
        for f in live.iterdir():
            shutil.copy(f, left / f.name)
    if journal == 'empty':
        (left / ('ucm.db-wal' if mode == 'WAL' else 'ucm.db-journal')).write_bytes(b'')
    return left / 'ucm.db'


@pytest.mark.parametrize('mode, journal, copied', [
    ('DELETE', 'absent', False), ('DELETE', 'empty', False),
    ('WAL', 'absent', False), ('WAL', 'empty', False), ('WAL', 'holding rows', True)])
def test_the_probe_copies_the_database_only_when_reading_it_in_place_would_write(
        tmp_path, monkeypatch, capsys, mode, journal, copied):
    """Nothing is written beside the database, and a database closed cleanly is read in place."""
    db = _left_by(tmp_path, mode, journal)
    assert (journal == 'holding rows') == ((db.parent / 'ucm.db-wal').exists()
                                           and (db.parent / 'ucm.db-wal').stat().st_size > 0)
    before = _fingerprint(db.parent)
    sys.path.insert(0, str(BACKEND))
    import migration_runner
    copies = []
    real = shutil.copyfile
    monkeypatch.setattr(shutil, 'copyfile', lambda a, b, **k: copies.append(a) or real(a, b, **k))
    monkeypatch.setenv('DATABASE_PATH', str(db))
    monkeypatch.delenv('DATABASE_URL', raising=False)
    assert migration_runner.check_database() == migration_runner.CHECK_STARTABLE
    assert bool(copies) is copied, copies
    assert _fingerprint(db.parent) == before
    assert _check(path=db)[0] == STARTABLE
    assert _fingerprint(db.parent) == before


@pytest.fixture
def pg_url():
    from tests.conftest import pg_bench_exclusive

    def _reset():
        engine = create_engine(_PG_URL)
        with engine.begin() as conn:
            conn.execute(text('DROP SCHEMA public CASCADE'))
            conn.execute(text('CREATE SCHEMA public'))
        engine.dispose()

    with pg_bench_exclusive():
        _reset()
        yield _PG_URL
        _reset()


def _pg(url, registry, users=True):
    engine = create_engine(url)
    with engine.begin() as conn:
        if users:
            conn.execute(text('CREATE TABLE users (id SERIAL PRIMARY KEY)'))
        if registry is not None:
            conn.execute(text('CREATE TABLE _migrations (id SERIAL PRIMARY KEY, name TEXT UNIQUE)'))
            for name in registry:
                conn.execute(text('INSERT INTO _migrations (name) VALUES (:n)'), {'n': name})
    engine.dispose()


@pytest.mark.postgres
@_needs_pg
class TestPostgreSQL:
    def test_an_empty_database_is_fresh(self, pg_url):
        code, lines = _check(url=pg_url)
        assert (code, lines[0]) == (FRESH, 'postgresql')

    @pytest.mark.parametrize('kind', ['2.254', '3.0'])
    def test_a_2_254_or_3_0_database_is_startable(self, pg_url, kind):
        _pg(pg_url, _registry(kind))
        assert _check(url=pg_url)[0] == STARTABLE

    @pytest.mark.parametrize('kind, reason', [
        ('short', '001_fix_dn_format'), (None, 'it has no migration registry')])
    def test_what_the_pivot_refuses_is_refused(self, pg_url, kind, reason):
        _pg(pg_url, _registry(kind) if kind else None)
        code, lines = _check(url=pg_url)
        assert (code, lines[0]) == (REFUSED, 'postgresql')
        assert reason in ' '.join(lines[1:])

    @pytest.mark.parametrize('kind', ['later', 'short-and-later'])
    def test_a_registry_naming_unknown_migrations_has_its_own_code(self, pg_url, kind):
        _pg(pg_url, _registry(kind))
        code, lines = _check(url=pg_url)
        assert (code, lines[0]) == (UNKNOWN, 'postgresql')
        assert '999_from_the_future' in ' '.join(lines[1:])

    def test_the_password_never_reaches_the_output(self, pg_url):
        _pg(pg_url, None)
        _, lines = _check(url=pg_url)
        password = pg_url.split('@')[0].rsplit(':', 1)[-1]
        assert password not in '\n'.join(lines)


def test_a_server_that_does_not_answer_is_unreadable():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    code, lines = _check(url=f'postgresql://u:secret-pw@127.0.0.1:{port}/ucm?connect_timeout=2')
    assert (code, lines[0]) == (UNREADABLE, 'postgresql')
    assert 'secret-pw' not in '\n'.join(lines)
