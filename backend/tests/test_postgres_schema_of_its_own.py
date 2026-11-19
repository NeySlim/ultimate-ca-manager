"""PostgreSQL in a schema other than public, as a search_path in the URL puts it.

Runs only when the session app is on PostgreSQL (UCM_TEST_APP_PG_URL), whose
harness gives each process a schema of its own.
"""
import json

import pytest
from sqlalchemy import text

from models import db
from services.database_admin import helpers


@pytest.fixture
def pg_schema(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('the session app is not on PostgreSQL')
        schema = db.session.execute(text('SELECT current_schema()')).scalar()
        db.session.rollback()
    assert schema != 'public'
    return schema


def test_the_integrity_check_counts_the_tables_of_its_schema(app, auth_client, pg_schema):
    with app.app_context():
        expected = db.session.execute(text(
            'SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = :s'),
            {'s': pg_schema}).scalar()
        db.session.rollback()
    r = auth_client.post('/api/v2/system/database/integrity-check',
                         data=json.dumps({}), content_type='application/json')
    assert r.status_code == 200, r.data
    assert r.get_json()['data']['tables'] == expected > 0


def test_the_sequences_of_its_schema_are_realigned(app, pg_schema):
    with app.app_context():
        with db.engine.begin() as conn:
            conn.execute(text('CREATE TABLE seq_probe (id SERIAL PRIMARY KEY)'))
            conn.execute(text('INSERT INTO seq_probe (id) VALUES (41)'))
        try:
            helpers._reset_pg_sequences(db.engine)
            with db.engine.begin() as conn:
                next_id = conn.execute(text(
                    'INSERT INTO seq_probe DEFAULT VALUES RETURNING id')).scalar()
            assert next_id == 42
        finally:
            with db.engine.begin() as conn:
                conn.execute(text('DROP TABLE seq_probe'))


def test_the_reset_hint_names_the_schema_of_the_target():
    from services.database_admin.migration import _rollback_hint
    named = _rollback_hint('postgresql://u@h/db', {'target_written': True, 'target_schema': 'Tenant A'})
    assert 'DROP SCHEMA "Tenant A" CASCADE; CREATE SCHEMA "Tenant A";' in named
    assert 'DROP SCHEMA public CASCADE' in _rollback_hint('postgresql://u@h/db', {'target_written': True})


def test_a_failed_migration_names_the_schema_it_wrote_to(app, pg_schema, monkeypatch):
    from types import SimpleNamespace

    from services.database_admin import migration
    from tests import pg_app_harness

    target = f'{pg_schema}_target'
    pg_app_harness._new_schema(pg_app_harness._marker[0].cursor(), target)
    monkeypatch.setattr(migration, '_check_source_integrity', lambda: {})
    monkeypatch.setattr(migration, 'create_source_snapshot', lambda: SimpleNamespace(as_proof=lambda: {}))

    def refused(*_args):
        raise RuntimeError('schema refused')
    monkeypatch.setattr(migration, '_create_target_schema', refused)
    with app.app_context():
        ok, message, stats = migration.migrate_data(pg_app_harness.app_url(target))
    assert not ok and stats['target_schema'] == target
    assert f'DROP SCHEMA {target} CASCADE; CREATE SCHEMA {target};' in message
