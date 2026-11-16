"""SQLite's INDEXED BY through SQLAlchemy's with_hint, which the SQLite dialect drops by default."""
from sqlalchemy.dialects.sqlite.base import SQLiteCompiler


def _from_hint_text(self, table, text):
    # A hint written for every dialect ('*', the default of with_hint) reaches this method too:
    # only INDEXED BY is SQLite syntax, anything else stays out of the statement as before
    return text if text.startswith('INDEXED BY ') else None


SQLiteCompiler.get_from_hint_text = _from_hint_text


def indexed_by(statement, from_, index):
    """`statement` reads `from_` through `index` on SQLite, whatever sqlite_stat1 says (stale
    statistics of a small table make a correlated lookup a full scan); other engines ignore it."""
    return statement.with_hint(from_, f'INDEXED BY {index}', dialect_name='sqlite')
