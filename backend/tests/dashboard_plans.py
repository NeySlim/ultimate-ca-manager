"""The query plan of one statement an overview aggregate runs, on SQLite or PostgreSQL."""
from sqlalchemy import event, text

from models import db


def plan_of(app, call, marker):
    """The plan of the statement whose SQL holds *marker* among those call() runs. PostgreSQL forbids
    sequential scans first: on a test-sized table it would scan anyway, the question is whether an index serves."""
    with app.app_context():
        engine = db.engine
        statements = []
        listener = lambda *args: statements.append((args[2], args[3]))  # noqa: E731
        event.listen(engine, 'before_cursor_execute', listener)
        try:
            call()
        finally:
            event.remove(engine, 'before_cursor_execute', listener)
        sql, params = next(s for s in statements if marker in s[0])
        conn = db.session.connection()
        try:
            if engine.dialect.name == 'sqlite':
                return ' '.join(str(r) for r in conn.exec_driver_sql(f'EXPLAIN QUERY PLAN {sql}', params).all())
            conn.execute(text('SET LOCAL enable_seqscan = off'))
            return ' '.join(r[0] for r in conn.exec_driver_sql(f'EXPLAIN {sql}', params).all())
        finally:
            db.session.rollback()
