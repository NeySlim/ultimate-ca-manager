"""SQLite plans from sqlite_stat1 once it exists, and an earlier test (or "Optimize database")
may have left one: a plan or cost test sets the statistics itself, then puts back what was there."""
from contextlib import contextmanager

from sqlalchemy import text

from models import db

STATES = ('no_stats', 'stale_stats')


def _reload():
    db.session.execute(text('ANALYZE sqlite_schema'))  # also creates sqlite_stat1 when missing


@contextmanager
def planner_statistics(app, state, tables):
    """`no_stats`: none. `stale_stats`: what ANALYZE leaves when each of `tables` holds one row,
    kept as they grow. A no-op on PostgreSQL, which analyzes on its own."""
    with app.app_context():
        if db.engine.dialect.name != 'sqlite':
            yield
            return
        _reload()
        saved = db.session.execute(text('SELECT tbl, idx, stat FROM sqlite_stat1')).all()
        db.session.execute(text('DELETE FROM sqlite_stat1'))
        if state == 'stale_stats':
            for table in tables:
                for index in db.session.execute(text(f"SELECT name FROM pragma_index_list('{table}')")).scalars():
                    width = db.session.execute(text(f"SELECT count(*) FROM pragma_index_info('{index}')")).scalar()
                    db.session.execute(text('INSERT INTO sqlite_stat1 VALUES (:t, :i, :s)'),
                                       {'t': table, 'i': index, 's': ' '.join(['1'] * (width + 1))})
        _reload()
        db.session.commit()
    try:
        yield
    finally:
        with app.app_context():
            db.session.rollback()
            db.session.execute(text('DELETE FROM sqlite_stat1'))
            for tbl, idx, stat in saved:
                db.session.execute(text('INSERT INTO sqlite_stat1 VALUES (:t, :i, :s)'),
                                   {'t': tbl, 'i': idx, 's': stat})
            _reload()
            db.session.commit()
