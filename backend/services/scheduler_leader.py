"""Scheduler leadership across HA nodes: a PostgreSQL session advisory lock.

PostgreSQL frees a session lock when its connection ends, so the leader is the
node whose dedicated connection still holds it; nothing on disk is shared.
"""
import logging

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Advisory lock key, database wide: the ASCII of 'UCMsched'
LEADER_LOCK_KEY = 0x55434D7363686564

# A dead peer must not keep the session (and its lock) open for the kernel's default hours
_KEEPALIVE_ARGS = {'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10,
                   'keepalives_count': 3, 'connect_timeout': 10}

_HELD_SQL = text(
    "SELECT pg_backend_pid() = :pid AND EXISTS ("
    " SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND pid = :pid AND granted"
    " AND classid::bigint = :hi AND objid::bigint = :lo AND objsubid = 1)")


def _dedicated_engine(url):
    """An engine outside the application pool: its one connection lives as long as the lock."""
    from utils.db_url import postgres_connect_args
    url_text = url if isinstance(url, str) else url.render_as_string(hide_password=False)
    args = dict(_KEEPALIVE_ARGS, **postgres_connect_args(url_text))
    return create_engine(url, poolclass=NullPool, hide_parameters=True, connect_args=args)


def application_url():
    """The URL of the application database, with its options (search_path...)."""
    from models import db
    return db.engine.url


class PgAdvisoryLock:
    """SingletonLock on a session advisory lock: acquire() -> bool, still_held() -> bool, release()."""

    def __init__(self, url, key=None):
        self._url = url
        self.key = LEADER_LOCK_KEY if key is None else key
        self._engine = None
        self._conn = None
        self.backend_pid = None
        self._connect_error_logged = False

    def acquire(self) -> bool:
        self.release()
        if self._engine is None:
            self._engine = _dedicated_engine(self._url)
        try:
            conn = self._engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        except Exception as e:
            if not self._connect_error_logged:
                logger.error(f"Scheduler leader lock: no connection to the database ({type(e).__name__})")
                self._connect_error_logged = True
            return False
        self._connect_error_logged = False
        try:
            got = conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': self.key}).scalar()
            pid = conn.execute(text('SELECT pg_backend_pid()')).scalar()
        except Exception as e:
            logger.error(f"Scheduler leader lock not taken: {type(e).__name__}")
            self._close(conn)
            return False
        if not got:
            self._close(conn)
            return False
        self._conn, self.backend_pid = conn, pid
        return True

    def still_held(self) -> bool:
        """Asks the server: a reconnected session or a dropped one no longer holds the lock."""
        conn = self._conn
        if conn is None:
            return False
        try:
            held = conn.execute(_HELD_SQL, {
                'pid': self.backend_pid,
                'hi': (self.key >> 32) & 0xFFFFFFFF, 'lo': self.key & 0xFFFFFFFF,
            }).scalar()
        except Exception as e:
            logger.error(f"Scheduler leader lock connection lost: {type(e).__name__}")
            held = False
        if not held:
            self._conn, self.backend_pid = None, None
            self._close(conn)
        return bool(held)

    def release(self) -> None:
        conn, self._conn, self.backend_pid = self._conn, None, None
        if conn is None:
            return
        try:
            conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': self.key})
        except Exception:
            pass  # a dead session already freed it
        self._close(conn)

    def dispose(self) -> None:
        self.release()
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    @staticmethod
    def _close(conn) -> None:
        try:
            conn.close()
        except Exception:
            pass

