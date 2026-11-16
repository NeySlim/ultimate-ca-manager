"""INDEXED BY reaches SQLite, and nothing else does: a hint written for every dialect, or for
another one, stays out of the SQLite statement as it did before the helper existed."""
from sqlalchemy import Column, Integer, MetaData, Table, select
from sqlalchemy.dialects import postgresql, sqlite

from utils.sqlite_hints import indexed_by

_t = Table('t', MetaData(), Column('id', Integer), Column('n', Integer))


def _sql(statement, dialect):
    return str(statement.compile(dialect=dialect.dialect()))


def test_indexed_by_is_rendered_on_sqlite_only():
    statement = indexed_by(select(_t.c.id).where(_t.c.n == 1), _t, 'ix_t_n')
    assert 'FROM t INDEXED BY ix_t_n' in _sql(statement, sqlite)
    assert 'INDEXED BY' not in _sql(statement, postgresql)


def test_a_hint_that_is_not_indexed_by_stays_out_of_sqlite():
    for kwargs in ({}, {'dialect_name': 'sqlite'}, {'dialect_name': 'mysql'}):
        statement = select(_t.c.id).with_hint(_t, 'USE INDEX (ix_t_n)', **kwargs)
        assert 'USE INDEX' not in _sql(statement, sqlite), kwargs
