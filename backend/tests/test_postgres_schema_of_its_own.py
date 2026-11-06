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
