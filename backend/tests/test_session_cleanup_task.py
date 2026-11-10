"""The scheduled session purge follows the configured store."""
import os
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from models import db
from services.session_cleanup_task import SessionCleanupTask


def _flask_sessions_table():
    """Flask-Session 0.8's table shape, built apart from migration 138 (a no-op on SQLite)."""
    from sqlalchemy import Column, DateTime, Integer, LargeBinary, MetaData, String, Table
    return Table('flask_sessions', MetaData(),
                 Column('id', Integer, primary_key=True),
                 Column('session_id', String(255), unique=True),
                 Column('data', LargeBinary), Column('expiry', DateTime))


@pytest.fixture
def sql_store(app, monkeypatch):
    """The test database with the Flask-Session table, the SQL store selected."""
    monkeypatch.setitem(app.config, 'SESSION_TYPE', 'sqlalchemy')
    monkeypatch.setitem(app.config, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions')
    with app.app_context():
        _flask_sessions_table().create(db.engine, checkfirst=True)
        db.session.execute(text('DELETE FROM flask_sessions'))
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(text('DROP TABLE IF EXISTS flask_sessions'))
        db.session.commit()


def test_sql_store_drops_only_expired_rows(app, sql_store):
    now = datetime.utcnow()
    with app.app_context():
        for sid, delta in (('old', -timedelta(hours=1)), ('older', -timedelta(days=3)),
                           ('live', timedelta(hours=1))):
            db.session.execute(text("INSERT INTO flask_sessions (session_id, data, expiry) "
                                    "VALUES (:s, :d, :e)"), {'s': sid, 'd': b'x', 'e': now + delta})
        db.session.commit()

        SessionCleanupTask.execute()

        left = db.session.execute(text('SELECT session_id FROM flask_sessions')).scalars().all()
    assert left == ['live']


def test_filesystem_store_still_drops_old_files(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'SESSION_TYPE', 'filesystem')
    monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(tmp_path))
    stale, fresh = tmp_path / 'stale', tmp_path / 'fresh'
    stale.write_bytes(b'x')
    fresh.write_bytes(b'x')
    old = time.time() - 30 * 86400
    os.utime(stale, (old, old))

    with app.app_context():
        SessionCleanupTask.execute()

    assert not stale.exists() and fresh.exists()


def test_redis_store_is_left_to_redis(app, tmp_path, monkeypatch):
    monkeypatch.setitem(app.config, 'SESSION_TYPE', 'redis')
    monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(tmp_path))
    stale = tmp_path / 'stale'
    stale.write_bytes(b'x')
    old = time.time() - 30 * 86400
    os.utime(stale, (old, old))

    with app.app_context():
        SessionCleanupTask.execute()

    assert stale.exists()
