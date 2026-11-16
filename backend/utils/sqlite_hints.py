"""SQLite's INDEXED BY through SQLAlchemy's with_hint, which the SQLite dialect drops by default."""
from sqlalchemy.dialects.sqlite.base import SQLiteCompiler


def _from_hint_text(self, table, text):
    return text


# Only hints given for the 'sqlite' dialect reach this method, so nothing else changes
SQLiteCompiler.get_from_hint_text = _from_hint_text


def indexed_by(statement, from_, index):
    """`statement` reads `from_` through `index` on SQLite, whatever sqlite_stat1 says (stale
    statistics of a small table make a correlated lookup a full scan); other engines ignore it."""
    return statement.with_hint(from_, f'INDEXED BY {index}', dialect_name='sqlite')
