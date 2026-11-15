"""The marker the image entrypoint reads to tell an ordinary start from a possible upgrade."""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import migration_runner  # noqa: E402

MARKER = '.ucm-started-version'


@pytest.fixture
def sqlite_db(tmp_path, monkeypatch):
    db = tmp_path / 'ucm.db'
    sqlite3.connect(db).close()
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.delenv('UCM_HA', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(db))
    return db


def test_a_migrated_start_writes_the_version_next_to_the_database(sqlite_db):
    migration_runner.record_started_version('3.0')
    assert (sqlite_db.parent / MARKER).read_text().strip() == '3.0'


def test_a_pending_serial_replay_leaves_the_marker_out(sqlite_db):
    # step 144 runs again at the next start: that start may still need the upgrade's room
    (sqlite_db.parent / MARKER).write_text('2.254.1\n')
    with sqlite3.connect(sqlite_db) as c:
        c.execute('CREATE TABLE system_config (key TEXT, value TEXT)')
        c.execute("INSERT INTO system_config VALUES ('serial_unique_index_pending', '1')")
    migration_runner.record_started_version('3.0')
    assert not (sqlite_db.parent / MARKER).exists()


@pytest.mark.parametrize('version', ['', 'unknown'])
def test_an_unknown_version_writes_no_marker(sqlite_db, version):
    migration_runner.record_started_version(version)
    assert not (sqlite_db.parent / MARKER).exists()


def test_postgresql_writes_no_marker(sqlite_db, monkeypatch):
    monkeypatch.setenv('DATABASE_URL', 'postgresql://u@127.0.0.1:1/x')
    migration_runner.record_started_version('3.0')
    assert not (sqlite_db.parent / MARKER).exists()


def test_a_read_only_directory_never_fails_the_start(sqlite_db, monkeypatch):
    def refuse(*a, **k):
        raise PermissionError('read-only')
    monkeypatch.setattr(Path, 'write_text', refuse)
    migration_runner.record_started_version('3.0')


def test_create_app_records_the_started_version(app):
    url = migration_runner._get_db_url()
    if not url.startswith('sqlite:///'):
        pytest.skip('the marker is SQLite only')
    marker = Path(url.replace('sqlite:///', '', 1)).parent / MARKER
    assert marker.read_text().strip() == app.config['APP_VERSION']
