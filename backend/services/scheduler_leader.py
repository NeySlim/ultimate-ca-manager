"""Scheduler leadership across HA nodes: a PostgreSQL session advisory lock.

PostgreSQL frees a session lock when its connection ends, so the leader is the
node whose dedicated connection still holds it; nothing on disk is shared.
"""
import logging
import os
import secrets
import time
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import Boolean, DateTime, bindparam, create_engine, text
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Advisory lock keys, database wide: the ASCII of 'UCMsched' and 'UCMboot!'
LEADER_LOCK_KEY = 0x55434D7363686564
BOOT_LOCK_KEY = 0x55434D626F6F7421
# How long a starting node waits for another one's migrations before it gives up
BOOT_LOCK_TIMEOUT_SECONDS = 120

# Client side: this node notices a dead server within about a minute
_KEEPALIVE_ARGS = {'keepalives': 1, 'keepalives_idle': 30, 'keepalives_interval': 10,
                   'keepalives_count': 3, 'connect_timeout': 10}

# Server side: PostgreSQL drops the lock session of a vanished node (power loss, partition)
# within about a minute instead of its kernel's default two hours, which frees the lock
_SERVER_TIMEOUTS_SQL = text(
    "SELECT set_config('tcp_keepalives_idle', '30', false),"
    " set_config('tcp_keepalives_interval', '10', false),"
    " set_config('tcp_keepalives_count', '3', false),"
    " set_config('tcp_user_timeout', '60000', false)")

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
        if self.backend_pid is not None:
            self.release()
        reused = self._conn is not None
        got = self._try_lock()
        if got is None and reused:
            got = self._try_lock()  # the kept session had dropped: one new one, at once
        return bool(got)

    def _try_lock(self):
        """True/False from the server, None when the session failed (it is then closed)."""
        conn = self._session()
        if conn is None:
            return None
        try:
            got = conn.execute(text('SELECT pg_try_advisory_lock(:k)'), {'k': self.key}).scalar()
            pid = conn.execute(text('SELECT pg_backend_pid()')).scalar()
        except Exception as e:
            logger.error(f"Scheduler leader lock not taken: {type(e).__name__}")
            self._conn = None
            self._close(conn)
            return None
        if got:
            self.backend_pid = pid
        return bool(got)

    def _session(self):
        """The dedicated connection, kept open between attempts and reopened only once dropped."""
        if self._conn is not None:
            return self._conn
        if self._engine is None:
            self._engine = _dedicated_engine(self._url)
        try:
            conn = self._engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        except Exception as e:
            if not self._connect_error_logged:
                logger.error(f"Scheduler leader lock: no connection to the database ({type(e).__name__})")
                self._connect_error_logged = True
            return None
        self._connect_error_logged = False
        try:
            conn.execute(_SERVER_TIMEOUTS_SQL)
        except Exception as e:
            logger.warning(f"Scheduler leader lock: server-side keepalives not set ({type(e).__name__})")
        self._conn = conn
        return conn

    def still_held(self) -> bool:
        """Asks the server: a reconnected session or a dropped one no longer holds the lock."""
        conn = self._conn
        if conn is None or self.backend_pid is None:
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
        conn, held = self._conn, self.backend_pid is not None
        self._conn, self.backend_pid = None, None
        if conn is None:
            return
        if held:
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

_SERVER_NOW_SQL = text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")


def cluster_utc_now(executor=None):
    """HA on PostgreSQL: the server's clock (naive UTC), the one clock every node's instants
    are written and compared on; otherwise this host's utc_now()."""
    from utils.datetime_utils import utc_now
    from utils.ha import ha_enabled
    if not ha_enabled():
        return utc_now()
    if executor is None:
        from models import db
        executor = db.session
    dialect = executor.dialect if hasattr(executor, 'dialect') else executor.get_bind().dialect
    if dialect.name != 'postgresql':
        return utc_now()
    return executor.execute(_SERVER_NOW_SQL).scalar()


def to_cluster_clock(local_instant, local_now, executor=None):
    """A past instant read on this host's clock, moved onto cluster_utc_now()'s clock."""
    return local_instant + (cluster_utc_now(executor) - local_now)


# Carries the node process's token to the scheduler process it spawns (scheduler_supervisor)
INSTANCE_TOKEN_ENV = 'UCM_NODE_INSTANCE_TOKEN'
# How often a starting node looks again at its row while another token holds it
CLAIM_POLL_SECONDS = 5.0

# A row is free for ``token`` when nobody holds it, the token already does, or its heartbeat is stale
_FREE_FOR = ("cluster_nodes.instance_token IS NULL OR cluster_nodes.instance_token = excluded.instance_token"
             " OR cluster_nodes.heartbeat_at < :fresh_from")
_HEARTBEAT_SQL = text(
    "INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, version, pid,"
    " kek_fingerprint, package_family, instance_token)"
    " VALUES (:n, :started, :now, :leader, :version, :pid, :kek, :family, :token)"
    " ON CONFLICT (node_id) DO UPDATE SET started_at = excluded.started_at,"
    " heartbeat_at = excluded.heartbeat_at, is_leader = excluded.is_leader,"
    " version = excluded.version, pid = excluded.pid, kek_fingerprint = excluded.kek_fingerprint,"
    " package_family = excluded.package_family, instance_token = excluded.instance_token"
    f" WHERE {_FREE_FOR}").bindparams(
    bindparam('started', type_=DateTime), bindparam('now', type_=DateTime),
    bindparam('fresh_from', type_=DateTime), bindparam('leader', type_=Boolean))
# Taken from another token: what the previous process published is reset until the first heartbeat
_SAME = "cluster_nodes.instance_token = excluded.instance_token"
_CLAIM_SQL = text(
    "INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, version, pid, instance_token)"
    " VALUES (:n, :now, :now, :false, :version, :pid, :token)"
    " ON CONFLICT (node_id) DO UPDATE SET heartbeat_at = excluded.heartbeat_at,"
    " instance_token = excluded.instance_token, version = excluded.version, pid = excluded.pid,"
    f" started_at = CASE WHEN {_SAME} THEN cluster_nodes.started_at ELSE excluded.started_at END,"
    f" is_leader = CASE WHEN {_SAME} THEN cluster_nodes.is_leader ELSE :false END,"
    f" kek_fingerprint = CASE WHEN {_SAME} THEN cluster_nodes.kek_fingerprint ELSE NULL END"
    f" WHERE {_FREE_FOR}").bindparams(
    bindparam('now', type_=DateTime), bindparam('fresh_from', type_=DateTime),
    bindparam('false', type_=Boolean))
_RELEASE_SQL = text("UPDATE cluster_nodes SET instance_token = NULL WHERE node_id = :n AND instance_token = :token")


def instance_token() -> str:
    """This node process's random token, drawn once and inherited by the processes it starts."""
    token = os.environ.get(INSTANCE_TOKEN_ENV)
    if not token:
        token = secrets.token_hex(16)
        os.environ[INSTANCE_TOKEN_ENV] = token
    return token


def _stale_seconds(wake_interval=None) -> float:
    if wake_interval is None:
        from services.scheduler_service import WAKE_INTERVAL_SECONDS
        wake_interval = WAKE_INTERVAL_SECONDS
    return STALE_PASSES * wake_interval


def write_heartbeat(node_id, leader, started_at, token=None, wake_interval=None) -> bool:
    """Refresh this node's row unless another token holds it fresh (False, nothing written);
    the leader also takes the flag off every other row. One conditional statement: no race.

    ``started_at`` is on the cluster clock (to_cluster_clock), as heartbeat_at is.
    """
    from config.settings import Config
    from models import ClusterNode, db
    from security.encryption import key_encryption
    from services.updates import package_family
    now = cluster_utc_now()
    written = db.session.execute(_HEARTBEAT_SQL, {
        'n': node_id, 'started': started_at, 'now': now, 'leader': bool(leader),
        'version': Config.APP_VERSION, 'pid': os.getpid(),
        'kek': key_encryption.configured_kek_fingerprint(), 'family': package_family(),
        'token': token or instance_token(),
        'fresh_from': now - timedelta(seconds=_stale_seconds(wake_interval))}).rowcount
    if not written:
        db.session.rollback()
        return False
    if leader:
        ClusterNode.query.filter(ClusterNode.node_id != node_id, ClusterNode.is_leader.is_(True)) \
            .update({'is_leader': False}, synchronize_session=False)
    db.session.commit()
    return True


def _claim(node_id, token, stale_seconds) -> bool:
    from config.settings import Config
    from models import db
    now = cluster_utc_now()
    taken = db.session.execute(_CLAIM_SQL, {
        'n': node_id, 'now': now, 'false': False, 'version': Config.APP_VERSION, 'pid': os.getpid(),
        'token': token, 'fresh_from': now - timedelta(seconds=stale_seconds)}).rowcount
    db.session.commit()
    return bool(taken)


def _holder(node_id):
    """(instance_token, heartbeat_at) of the row, as last committed."""
    from models import ClusterNode, db
    db.session.expire_all()
    node = db.session.get(ClusterNode, node_id)
    return None if node is None else (node.instance_token, node.heartbeat_at)


class NodeIdTaken(SystemExit):
    """Another live process holds this node identifier."""


def claim_node_at_start(node_id=None, token=None, stale_seconds=None, poll=None, sleep=time.sleep,
                        release_at_exit=True) -> float:
    """HA: take this node's row for this process's token, or refuse to start.

    A row another token holds fresh is waited on: its heartbeat moving on means a live process
    (refused), its heartbeat expiring means a previous run of this node (taken), so at most the
    stale window. Returns the seconds waited.
    """
    from config.settings import Config
    node_id = node_id or Config.NODE_ID
    token = token or instance_token()
    stale = _stale_seconds() if stale_seconds is None else stale_seconds
    poll = CLAIM_POLL_SECONDS if poll is None else poll
    began = time.monotonic()
    seen = None
    while not _claim(node_id, token, stale):
        row = _holder(node_id)
        if seen is None:
            seen = row
            logger.warning(f"HA: node identifier {node_id} is held by another process: waiting at most "
                           f"{stale:.0f}s for its heartbeat to expire")
        elif row is not None and row[0] is not None and (row[0] != seen[0] or row[1] != seen[1]):
            raise NodeIdTaken(
                f"HA: node identifier {node_id} is already used by another live UCM process. "
                "Give each node a distinct UCM_NODE_ID. Refusing to start.")
        if time.monotonic() - began > stale + 2 * poll:
            raise NodeIdTaken(
                f"HA: node identifier {node_id} stayed held by another process for more than "
                f"{stale:.0f}s. Give each node a distinct UCM_NODE_ID. Refusing to start.")
        sleep(poll)
    waited = time.monotonic() - began
    if seen is not None:
        logger.info(f"HA: node identifier {node_id} taken over after {waited:.0f}s: the previous "
                    "process's heartbeat expired")
    if release_at_exit:
        _release_at_exit(node_id, token)
    return waited


def release_node(node_id, token, executor=None) -> bool:
    """Give the row up (clean stop): the next start of this node takes it at once."""
    from models import db
    executor = executor or db.session
    released = executor.execute(_RELEASE_SQL, {'n': node_id, 'token': token}).rowcount
    executor.commit()
    return bool(released)


def _release_at_exit(node_id, token) -> None:
    import atexit
    url, pid = application_url(), os.getpid()
    if url.get_backend_name() != 'postgresql':
        return  # HA runs on PostgreSQL only (validate_ha_config)

    def release():
        # Forked web workers inherit the handler: only the process that claimed the row gives it up
        if os.getpid() != pid:
            return
        engine = _dedicated_engine(url)
        try:
            with engine.connect() as conn:
                release_node(node_id, token, conn)
        except Exception as e:
            logger.warning(f"HA: node identifier {node_id} not released at exit: {type(e).__name__}")
        finally:
            engine.dispose()
    atexit.register(release)


def node_held_elsewhere(node_id, wake_interval) -> bool:
    """This node's row carries another process's token and a fresh heartbeat."""
    from models import ClusterNode, db
    node = db.session.get(ClusterNode, node_id)
    return bool(node and node.instance_token is not None and node.instance_token != instance_token()
                and not _is_stale(node, wake_interval, cluster_utc_now()))


def _is_stale(node, wake_interval, now) -> bool:
    return (now - node.heartbeat_at).total_seconds() > STALE_PASSES * wake_interval


def cluster_summary(wake_interval) -> dict:
    """{leader_node_id, nodes, stale, command_seen} as the public /health reports it; a stale
    leader is no leader. The leader is the only node it names; command_seen is the answering node's."""
    from config.settings import Config
    from models import ClusterNode
    now = cluster_utc_now()
    nodes = ClusterNode.query.all()
    stale = {n.node_id for n in nodes if _is_stale(n, wake_interval, now)}
    leader = next((n.node_id for n in nodes if n.is_leader and n.node_id not in stale), None)
    own = next((n.command_seen for n in nodes if n.node_id == Config.NODE_ID), None)
    return {'leader_node_id': leader, 'nodes': len(nodes), 'stale': len(stale), 'command_seen': own}


def cluster_nodes_detail(wake_interval) -> list:
    """Every registered node, for authenticated status pages only."""
    from models import ClusterNode
    from utils.datetime_utils import utc_isoformat
    now = cluster_utc_now()
    return [{'node_id': n.node_id, 'leader': bool(n.is_leader),
             'stale': _is_stale(n, wake_interval, now), 'version': n.version,
             'started_at': utc_isoformat(n.started_at), 'heartbeat_at': utc_isoformat(n.heartbeat_at),
             'command_seen': n.command_seen, 'kek_fingerprint': n.kek_fingerprint,
             'package_family': n.package_family}
            for n in ClusterNode.query.order_by(ClusterNode.node_id).all()]


def node_registered(node_id) -> bool:
    from models import ClusterNode, db
    return db.session.get(ClusterNode, node_id) is not None


def node_is_leader(node_id, wake_interval) -> bool:
    """Whether this node's scheduler process holds the lock, as its last fresh heartbeat says."""
    from models import ClusterNode, db
    node = db.session.get(ClusterNode, node_id)
    return bool(node and node.is_leader and node.instance_token in (None, instance_token())
                and not _is_stale(node, wake_interval, cluster_utc_now()))


def fresh_node_ids(wake_interval) -> set:
    from models import ClusterNode
    now = cluster_utc_now()
    return {n.node_id for n in ClusterNode.query.all() if not _is_stale(n, wake_interval, now)}
