"""What a network call would hold the database's write lock across."""
from contextlib import contextmanager

from sqlalchemy import event

from models import db


@contextmanager
def watching_writes():
    """Yields a probe: the writes not yet committed, once autoflush has run as a real call does."""
    writes = []

    def record(_conn, _cursor, statement, *_args):
        if statement.split(None, 1)[0].upper() in ('INSERT', 'UPDATE', 'DELETE'):
            writes.append(statement)

    def forget(_conn):
        writes.clear()

    engine = db.engine
    listeners = (('before_cursor_execute', record), ('commit', forget), ('rollback', forget))
    for name, listener in listeners:
        event.listen(engine, name, listener)

    def probe():
        db.session.flush()
        return list(writes)

    try:
        yield probe
    finally:
        for name, listener in listeners:
            event.remove(engine, name, listener)
