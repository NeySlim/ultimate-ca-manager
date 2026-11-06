"""PostgreSQL in a schema other than public, as a search_path in the URL puts it.

Runs only when the session app is on PostgreSQL (UCM_TEST_APP_PG_URL), whose
harness gives each process a schema of its own.
"""
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
