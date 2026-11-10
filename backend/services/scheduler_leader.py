"""Scheduler leadership across HA nodes: a PostgreSQL session advisory lock.

PostgreSQL frees a session lock when its connection ends, so the leader is the
node whose dedicated connection still holds it; nothing on disk is shared.
"""
import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Advisory lock keys, database wide: the ASCII of 'UCMsched' and 'UCMboot!'
LEADER_LOCK_KEY = 0x55434D7363686564
BOOT_LOCK_KEY = 0x55434D626F6F7421
# How long a starting node waits for another one's migrations before it gives up
BOOT_LOCK_TIMEOUT_SECONDS = 120

# A dead peer must not keep the session (and its lock) open for the kernel's default hours
_KEEPALIVE_ARGS = {'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10,
                   'keepalives_count': 3, 'connect_timeout': 10}

_HELD_SQL = text(
    "SELECT pg_backend_pid() = :pid AND EXISTS ("
    " SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND pid = :pid AND granted"
    " AND classid::bigint = :hi AND objid::bigint = :lo AND objsubid = 1)")


def _dedicated_engine(url):
    """An engine outside the application pool: its one connection lives as long as the lock."""
    from utils.db_url import postgres_connect_args, sqlalchemy_url
    if isinstance(url, str):
        url = sqlalchemy_url(url)
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




class BootLockTimeout(RuntimeError):
    """Another node held the startup lock longer than BOOT_LOCK_TIMEOUT_SECONDS."""


@contextmanager
def boot_lock(url, timeout=None, key=None):
    """Serialise migrations and schema initialisation between nodes (HA only).

    Blocks on a session advisory lock, at most ``timeout`` seconds, then fails explicitly.
    """
    from utils.ha import ha_enabled
    if not ha_enabled():
        yield
        return
    timeout = BOOT_LOCK_TIMEOUT_SECONDS if timeout is None else timeout
    key = BOOT_LOCK_KEY if key is None else key
    engine = _dedicated_engine(url)
    try:
        conn = engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        try:
            conn.execute(text("SELECT set_config('lock_timeout', :v, false)"),
                         {'v': f'{int(timeout * 1000)}ms'})
            logger.info("Waiting for the cluster startup lock (migrations)...")
            try:
                conn.execute(text('SELECT pg_advisory_lock(:k)'), {'k': key})
            except Exception as e:
                if getattr(getattr(e, 'orig', None), 'sqlstate', None) == '55P03':
                    raise BootLockTimeout(
                        f"Another node held the startup lock for more than {timeout}s: "
                        "its migrations are still running or it is stuck. Refusing to start."
                    ) from None
                raise
            logger.info("Cluster startup lock acquired")
            try:
                yield
            finally:
                try:
                    conn.execute(text('SELECT pg_advisory_unlock(:k)'), {'k': key})
                except Exception:
                    pass  # closing the session frees it anyway
        finally:
            conn.close()
    finally:
        engine.dispose()


# A node whose scheduler process missed this many passes counts as gone
STALE_PASSES = 3


def write_heartbeat(node_id, leader, started_at) -> None:
    """Refresh this node's row; the leader also takes the flag off every other row."""
    from config.settings import Config
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    now = utc_now()
    node = db.session.get(ClusterNode, node_id)
    if node is None:
        node = ClusterNode(node_id=node_id, started_at=started_at)
        db.session.add(node)
    elif node.pid != os.getpid():
        node.started_at = started_at  # a new process on the same node
    node.heartbeat_at, node.is_leader = now, bool(leader)
    node.version, node.pid = Config.APP_VERSION, os.getpid()
    if leader:
        ClusterNode.query.filter(ClusterNode.node_id != node_id, ClusterNode.is_leader.is_(True)) \
            .update({'is_leader': False}, synchronize_session=False)
    db.session.commit()


def _is_stale(node, wake_interval, now) -> bool:
    return (now - node.heartbeat_at).total_seconds() > STALE_PASSES * wake_interval


def cluster_summary(wake_interval) -> dict:
    """{leader_node_id, nodes, stale} as /health reports it; a stale leader is no leader."""
    from models import ClusterNode
    from utils.datetime_utils import utc_now
    now = utc_now()
    nodes = ClusterNode.query.all()
    stale = {n.node_id for n in nodes if _is_stale(n, wake_interval, now)}
    leader = next((n.node_id for n in nodes if n.is_leader and n.node_id not in stale), None)
    return {'leader_node_id': leader, 'nodes': len(nodes), 'stale': len(stale)}


def node_registered(node_id) -> bool:
    from models import ClusterNode, db
    return db.session.get(ClusterNode, node_id) is not None


def node_is_leader(node_id, wake_interval) -> bool:
    """Whether this node's scheduler process holds the lock, as its last fresh heartbeat says."""
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    node = db.session.get(ClusterNode, node_id)
    return bool(node and node.is_leader and not _is_stale(node, wake_interval, utc_now()))


def fresh_node_ids(wake_interval) -> set:
    from models import ClusterNode
    from utils.datetime_utils import utc_now
    now = utc_now()
    return {n.node_id for n in ClusterNode.query.all() if not _is_stale(n, wake_interval, now)}
