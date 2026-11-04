"""Migration 120 indexes certificates.serial_number and caref, idempotently, as the model declares."""
import importlib
import os
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from models import Certificate

PG_URL = os.getenv('UCM_TEST_PG_URL')
TABLE = Certificate.__tablename__
NAMES = {'ix_certificates_serial_number', 'ix_certificates_caref'}


def _migration():
    return importlib.import_module('migrations.120_certificates_lookup_indexes')


def test_sqlite_upgrade_is_idempotent_and_reverts():
    conn = sqlite3.connect(':memory:')
    conn.execute(f"CREATE TABLE {TABLE} (id INTEGER PRIMARY KEY, serial_number TEXT, caref TEXT)")
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert NAMES <= {row[1] for row in conn.execute(f"PRAGMA index_list({TABLE})")}
    plan = conn.execute(f"EXPLAIN QUERY PLAN SELECT id FROM {TABLE} WHERE serial_number = '1'").fetchall()
    assert any('ix_certificates_serial_number' in row[3] for row in plan), plan
    _migration().downgrade(conn)
    assert not NAMES & {row[1] for row in conn.execute(f"PRAGMA index_list({TABLE})")}


def test_the_model_declares_the_same_indexes():
    assert NAMES <= {index.name for index in Certificate.__table__.indexes}


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgresql_upgrade_is_idempotent():
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS mig120"))
        conn.execute(text("SET search_path TO mig120"))
        conn.execute(text(f"CREATE TABLE {TABLE} (id SERIAL PRIMARY KEY, serial_number TEXT, caref TEXT)"))
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        names = {r[0] for r in conn.execute(text(
            "SELECT indexname FROM pg_indexes WHERE schemaname = 'mig120'"))}
        assert NAMES <= names
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA mig120 CASCADE"))
    engine.dispose()
