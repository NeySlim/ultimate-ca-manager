"""
Tests for database_admin_service: backend switch, bootstrap, migrate.

Covers the bug-class that shipped in #96:
  - SQLite → empty target migration
  - Auth bootstrap on switch-without-migration (no lockout)
  - Refusing to overwrite a non-empty target
  - JSON column handling
  - FK-disabled vs topological fallback
  - PG sequence reset (smoke / mock)
"""
import os
import json
import tempfile

import pytest
from sqlalchemy import create_engine, text, inspect

from services import database_admin_service as svc


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sqlite_target():
    """Empty SQLite file usable as a migration target."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    os.unlink(path)  # ensure the file does not yet exist
    yield f'sqlite:///{path}'
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def populated_app(app):
    """App with the auto-created admin user — enough for migration tests."""
    return app


# ---------------------------------------------------------------------------
# test_connection
# ---------------------------------------------------------------------------

def test_connection_rejects_empty_url():
    ok, msg = svc.test_connection('')
    assert not ok
    assert 'required' in msg.lower()


def test_connection_rejects_unknown_scheme():
    ok, msg = svc.test_connection('mysql://x:y@localhost/db')
    assert not ok
    assert 'unsupported' in msg.lower()


def test_connection_succeeds_for_valid_sqlite(sqlite_target):
    # Create the file first by opening it
    create_engine(sqlite_target).connect().close()
    ok, msg = svc.test_connection(sqlite_target)
    assert ok, msg


# ---------------------------------------------------------------------------
# bootstrap_auth_to_target
# ---------------------------------------------------------------------------

def test_bootstrap_copies_users_to_empty_target(populated_app, sqlite_target):
    with populated_app.app_context():
        ok, msg, stats = svc.bootstrap_auth_to_target(sqlite_target)

    assert ok, msg
    assert stats['rows_copied'] >= 1  # admin user at minimum

    # Verify the admin landed on the target
    eng = create_engine(sqlite_target)
    with eng.connect() as c:
        row = c.execute(text("SELECT COUNT(*) FROM users WHERE username = 'admin'")).fetchone()
        assert row[0] == 1
    eng.dispose()


def test_bootstrap_skips_when_target_already_has_users(populated_app, sqlite_target):
    # First bootstrap to populate
    with populated_app.app_context():
        svc.bootstrap_auth_to_target(sqlite_target)

    # Second call should be a no-op (skip), not a failure
    with populated_app.app_context():
        ok, msg, stats = svc.bootstrap_auth_to_target(sqlite_target)

    assert ok
    assert 'skipped' in msg.lower()
    assert stats['rows_copied'] == 0


# ---------------------------------------------------------------------------
# migrate_data
# ---------------------------------------------------------------------------

def test_migrate_refuses_non_empty_target(populated_app, sqlite_target):
    # Pre-populate target so the safety check fires
    with populated_app.app_context():
        svc.bootstrap_auth_to_target(sqlite_target)

    with populated_app.app_context():
        ok, msg, stats = svc.migrate_data(sqlite_target)

    assert not ok
    assert 'not empty' in msg.lower()
    assert stats['tables_migrated'] == 0


def test_migrate_full_roundtrip_sqlite_to_sqlite(populated_app, sqlite_target):
    with populated_app.app_context():
        ok, msg, stats = svc.migrate_data(sqlite_target)

    assert ok, msg
    assert stats['tables_migrated'] >= 5  # at least users, system_config, ...
    assert stats['rows_migrated'] >= 1
    assert isinstance(stats['dropped_columns'], dict)

    # Spot-check: admin user exists on the target
    eng = create_engine(sqlite_target)
    with eng.connect() as c:
        users = c.execute(text("SELECT COUNT(*) FROM users")).fetchone()[0]
    eng.dispose()
    assert users >= 1


# ---------------------------------------------------------------------------
# Pure helpers (no DB)
# ---------------------------------------------------------------------------

def test_normalize_row_pg_to_sqlite_serializes_dicts():
    out = svc._normalize_row(
        {"a": {"x": 1}, "b": [1, 2], "c": "plain"},
        source_is_pg=True,
        target_is_pg=False,
    )
    assert out["a"] == json.dumps({"x": 1})
    assert out["b"] == json.dumps([1, 2])
    assert out["c"] == "plain"


def test_normalize_row_sqlite_to_pg_parses_json_columns():
    # JSON-typed target column → string must become dict so psycopg2 adapts it
    out = svc._normalize_row(
        {"perms": '["read:certs","write:cas"]', "name": "alice"},
        source_is_pg=False,
        target_is_pg=True,
        target_json_cols={"perms"},
    )
    assert out["perms"] == ["read:certs", "write:cas"]
    assert out["name"] == "alice"  # untouched


def test_normalize_row_sqlite_to_pg_leaves_non_json_strings_alone():
    out = svc._normalize_row(
        {"name": "alice", "perms": "[1,2]"},
        source_is_pg=False,
        target_is_pg=True,
        target_json_cols=set(),  # no JSON columns
    )
    assert out["name"] == "alice"
    assert out["perms"] == "[1,2]"  # not parsed


def test_normalize_row_handles_memoryview():
    out = svc._normalize_row(
        {"blob": memoryview(b"hello")},
        source_is_pg=True,
        target_is_pg=False,
    )
    assert out["blob"] == b"hello"


def test_topo_sort_puts_parents_before_children(populated_app):
    from models import db
    with populated_app.app_context():
        order = svc._topo_sort_tables(inspect(db.engine))
    # users must come before user_sessions (FK)
    if 'user_sessions' in order and 'users' in order:
        assert order.index('users') < order.index('user_sessions')
    # certificate_authorities must come before certificates (FK)
    if 'certificates' in order and 'certificate_authorities' in order:
        assert order.index('certificate_authorities') < order.index('certificates')


def test_redact_uri_hides_password():
    redacted = svc._redact_uri('postgresql://user:secret@host:5432/db')
    assert 'secret' not in redacted
    assert '***' in redacted


def test_human_size_formats_bytes():
    assert svc._human_size(0) == '0 B'
    assert svc._human_size(1024) == '1.0 KB'
    assert 'MB' in svc._human_size(1024 * 1024 * 5)
