"""A fresh install cut between the creation of a table and of its indexes ends, at the next start,
with the schema of an uninterrupted fresh install, on SQLite and PostgreSQL."""
import re

import pytest
from sqlalchemy import event, inspect

from migration_runner import fresh_registry_names
from tests.upgrade_2254_support import BACKENDS, differences, fresh_metadata, make_base, snapshot


class _Cut(Exception):
    """The start stopping where the test says."""


@pytest.fixture(params=BACKENDS)
def dialect(request):
    return request.param


def _start(db, create_all):
    """A start as app.py runs it: migrations, then the schema of a fresh or existing database."""
    assert db.upgrade() is True
    migration_runner = db._route()
    migration_runner.start_schema(db.engine, fresh_metadata(), create_all)


def _cut_at_first_index_after(engine, tables):
    """Raise at the first CREATE INDEX once every table in *tables* was created."""
    created = set()

    def before(conn, cursor, statement, parameters, context, executemany):
        sql = ' '.join(statement.split()).upper()
        made = re.match(r'CREATE TABLE "?(\w+)"?', sql)
        if made:
            created.add(made.group(1).lower())
        if re.match(r'CREATE (UNIQUE )?INDEX', sql) and tables <= created:
            raise _Cut()
    event.listen(engine, 'before_cursor_execute', before)
    return lambda: event.remove(engine, 'before_cursor_execute', before)


def _indexes(engine):
    insp = inspect(engine)
    return {(t, i['name']) for t in insp.get_table_names() for i in insp.get_indexes(t)}


def test_a_fresh_install_cut_before_an_index_has_its_whole_schema_at_the_next_start(dialect, tmp_path,
                                                                                     monkeypatch):
    for ref in make_base(dialect, tmp_path, monkeypatch, 'ir', sql=''):
        _start(ref, lambda: fresh_metadata().create_all(ref.engine))
        expected = snapshot(ref.engine)
        expected_indexes = _indexes(ref.engine)
    for db in make_base(dialect, tmp_path, monkeypatch, 'ic', sql=''):
        release = _cut_at_first_index_after(db.engine, {'users', 'certificate_authorities'})
        with pytest.raises(_Cut):
            _start(db, lambda: fresh_metadata().create_all(db.engine))
        release()
        _start(db, lambda: fresh_metadata().create_all(db.engine))
        assert expected_indexes - _indexes(db.engine) == set()
        assert list(differences(snapshot(db.engine), expected)) == []
        assert db.registry() == fresh_registry_names()
