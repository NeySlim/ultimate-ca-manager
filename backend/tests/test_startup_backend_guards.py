"""Startup leftovers: SQLite-only schema helpers stay off PostgreSQL, and a node
never moves `app.version` backwards."""
import sqlite3

import pytest

from config.settings import Config
from database_health import ensure_system_config_defaults
from models import SystemConfig, db
from tests import pg_app_harness


@pytest.fixture
def sqlite_connects(monkeypatch):
    calls = []
    real = sqlite3.connect

    def witness(*args, **kwargs):
        calls.append(args)
        return real(*args, **kwargs)

    monkeypatch.setattr(sqlite3, 'connect', witness)
    return calls


@pytest.mark.skipif(not pg_app_harness.ENABLED, reason='needs UCM_TEST_APP_PG_URL')
def test_postgresql_startup_opens_no_sqlite_file(app, sqlite_connects):
    from app import init_database
    with app.app_context():
        init_database(app)
    assert sqlite_connects == []


@pytest.mark.skipif(pg_app_harness.ENABLED, reason='SQLite behaviour')
def test_sqlite_startup_still_runs_the_helpers(app, sqlite_connects):
    from app import init_database
    with app.app_context():
        init_database(app)
    assert sqlite_connects


def _stored(value):
    SystemConfig.query.filter_by(key='app.version').delete()
    if value is not None:
        db.session.add(SystemConfig(key='app.version', value=value, description='v'))
    db.session.commit()


@pytest.mark.parametrize('stored,running,expected', [
    ('2.254', '2.253', '2.254'),          # older node: no write
    ('2.254', '2.254-dev', '2.254'),      # pre-release is older
    ('2.253', '2.254', '2.254'),          # newer: write
    ('', '2.253', '2.253'),               # empty: write
    (None, '2.253', '2.253'),             # absent: write
    ('garbage', '2.253', '2.253'),        # unreadable: write
])
def test_app_version_never_moves_backwards(app, monkeypatch, stored, running, expected):
    monkeypatch.setattr(Config, 'APP_VERSION', running)
    with app.app_context():
        _stored(stored)
        ensure_system_config_defaults(app)
        assert SystemConfig.query.filter_by(key='app.version').one().value == expected


def test_a_non_sqlite_dialect_skips_the_helpers_even_on_this_backend(app, sqlite_connects, monkeypatch):
    from app import init_database
    with app.app_context():
        monkeypatch.setattr(db.engine.dialect, 'name', 'postgresql')
        init_database(app)
    assert sqlite_connects == []
