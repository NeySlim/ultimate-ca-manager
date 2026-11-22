"""The application's SQLite database runs in write-ahead logging (WAL): readers never wait
for a writer. The mode is stored in the file, so every later connection, raw sqlite3 included,
opens it in WAL. synchronous=FULL keeps each commit across a power loss (PRAGMA synchronous:
NORMAL in WAL may roll the last ones back), whatever default the library was built with.
"""
import logging
import sqlite3

from sqlalchemy import event

logger = logging.getLogger(__name__)

# The -wal file is cut back to this size once a checkpoint has emptied it (a VACUUM would
# otherwise leave it as large as the database)
JOURNAL_SIZE_LIMIT = 64 * 1024 * 1024


def use_wal(conn: sqlite3.Connection):
    """Puts the database of *conn* in WAL; returns the journal mode it is in afterwards.
    A database that cannot change (read-only, in memory, refused by the filesystem) keeps
    its mode: the reason is logged and the connection still serves."""
    try:
        mode = conn.execute('PRAGMA journal_mode=WAL').fetchone()[0]
        conn.execute('PRAGMA synchronous=FULL')
        conn.execute(f'PRAGMA journal_size_limit={JOURNAL_SIZE_LIMIT}')
    except sqlite3.Error as exc:
        logger.warning('SQLite database not switched to WAL: %s', exc)
        return None
    if mode not in ('wal', 'memory'):
        logger.warning('SQLite database stays in journal mode %s: WAL was refused', mode)
    return mode


def connect(path, **kwargs) -> sqlite3.Connection:
    """sqlite3.connect for the application's own database, in WAL."""
    conn = sqlite3.connect(path, **kwargs)
    use_wal(conn)
    return conn


def _on_connect(dbapi_connection, _record):
    if isinstance(dbapi_connection, sqlite3.Connection):
        use_wal(dbapi_connection)


def attach(engine) -> None:
    """Every connection *engine* opens to a SQLite database is in WAL; other backends are
    left alone. Attached to the application's engines only: the migration runner leaves a
    2.254 database as 2.254 wrote it until its copy is taken."""
    if engine.dialect.name == 'sqlite' and not event.contains(engine, 'connect', _on_connect):
        event.listen(engine, 'connect', _on_connect)
