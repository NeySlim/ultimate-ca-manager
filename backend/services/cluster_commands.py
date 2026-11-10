"""HA cluster commands: a setting changed on one node takes effect on every node.

emit() adds a row in the caller's transaction, so a command exists only once the change
is committed. Each node runs an applier that replays the newer rows in id order and
records the last one it handled in cluster_nodes.command_seen. Nothing runs outside HA.
"""
import json
import logging
import os
import signal
import threading
import time
from collections import namedtuple
from datetime import timedelta

from sqlalchemy import text

from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

RELOAD_RATE_LIMITS = 'reload_rate_limits'
RELOAD_SYSLOG = 'reload_syslog'
RELOAD_ADMIN_ALLOWLIST = 'reload_admin_allowlist'
RESTART = 'restart'
# No password policy kind (read from the database on every check) and no encryption kind
# (enabling or rotating encryption is refused in HA until key envelopes ship)
KINDS = frozenset({RELOAD_RATE_LIMITS, RELOAD_SYSLOG, RELOAD_ADMIN_ALLOWLIST, RESTART})

TICK_SECONDS = 2.0
# A missing id below a newer one is a transaction still committing (or rolled back): wait this long
GAP_GRACE_SECONDS = 4.0
# An id passed over that commits later is still applied within this window
HOLE_TTL_SECONDS = 600.0
MAX_HOLES = 32
# A node waits at most this long per node ahead of it in a rolling restart
RESTART_GUARD_SECONDS = 120.0
RETENTION = timedelta(hours=24)
# A starting process replays the reloads of this window (idempotent): one committed while it
# read its settings is not lost. A restart in it is older than the process and never runs.
START_REPLAY = timedelta(seconds=60)
BATCH = 200

# A held restart: the newest id and creation instant of the restarts it stands for
_Held = namedtuple('_Held', 'id created_at')

# Imported by gunicorn_config before the master reads a setting: a restart created later runs.
# On this host's clock: the applier moves it onto the cluster clock before comparing.
PROCESS_STARTED = utc_now()

_INITIAL_SQL = text("SELECT COALESCE(MAX(id), 0) FROM cluster_commands WHERE created_at <= :t")
_NODES_SQL = text("SELECT node_id, started_at, heartbeat_at FROM cluster_nodes")
_ADVANCE_SQL = text("UPDATE cluster_nodes SET command_seen = :id WHERE node_id = :n "
                    "AND (command_seen IS NULL OR command_seen < :id)")
_ROW_SQL = text("SELECT 1 FROM cluster_nodes WHERE node_id = :n")
# Apart from command_seen: a restart applied late (from a hole) is behind the reload cursor
_CLAIM_SQL = text("UPDATE cluster_nodes SET restart_seen = :id WHERE node_id = :n "
                  "AND (restart_seen IS NULL OR restart_seen < :id)")
_CLAIMED_SQL = text("SELECT restart_seen FROM cluster_nodes WHERE node_id = :n")
_RELEASE_SQL = text("UPDATE cluster_nodes SET restart_seen = :prev WHERE node_id = :n "
                    "AND restart_seen = :id")


def emit(kind, payload=None, target=None):
    """HA: queue ``kind`` for every node (or ``target``) in the current transaction; None otherwise."""
    if kind not in KINDS:
        raise ValueError(f"Unknown cluster command {kind!r}")
    from utils.ha import ha_enabled
    if not ha_enabled():
        return None
    from config.settings import Config
    from models import ClusterCommand, db
    from services.scheduler_leader import cluster_utc_now
    command = ClusterCommand(kind=kind, created_at=cluster_utc_now(), created_by=Config.NODE_ID,
                             payload=None if payload is None else json.dumps(payload),
                             node_id=target)
    db.session.add(command)
    return command


def emit_committed(kind, payload=None, target=None) -> bool:
    """emit() for a change that is not in the database: the command is its own transaction."""
    from models import db
    try:
        if emit(kind, payload, target) is None:
            return False
        db.session.commit()
        return True
    except Exception as e:
        db.session.rollback()
        logger.error(f"Cluster command {kind} not queued: {type(e).__name__}: {e}")
        return False


ROLLING_RESTART_MESSAGE = "Rolling restart requested: the nodes restart one at a time"


def request_restart():
    """HA side of restart_service(): every node restarts, one at a time."""
    if emit_committed(RESTART):
        return True, ROLLING_RESTART_MESSAGE
    return False, "The rolling restart could not be requested"


def purge_old_commands():
    """Leader task: commands older than RETENTION are dropped."""
    from models import ClusterCommand, db
    from services.scheduler_leader import cluster_utc_now
    removed = ClusterCommand.query.filter(ClusterCommand.created_at < cluster_utc_now() - RETENTION) \
        .delete(synchronize_session=False)
    db.session.commit()
    if removed:
        logger.info(f"Purged {removed} cluster command(s) older than {RETENTION}")


def pending_predecessors(me, nodes, issued_at, now, stale_seconds):
    """Nodes sorted before ``me`` that still run a process started before the restart command.

    A node is back once its heartbeat carries a later started_at; a stale one is gone.
    """
    pending = []
    for node_id, started_at, heartbeat_at in nodes:
        if node_id >= me:
            continue
        if (now - heartbeat_at).total_seconds() > stale_seconds:
            continue
        if started_at > issued_at:
            continue
        pending.append(node_id)
    return sorted(pending)


def restart_this_node(master_pid=None):
    """DEB/RPM: the watcher's signal file; container: the gunicorn master stops, the orchestrator restarts it."""
    from config.settings import DATA_DIR, is_docker
    if is_docker():
        os.kill(master_pid or os.getpid(), signal.SIGTERM)
        return
    (DATA_DIR / '.restart_requested').write_text('restart')


def _reload_rate_limits(payload):
    """The stored settings over this node's own environment (idempotent on the emitter)."""
    from security.rate_limiter import RateLimitConfig
    RateLimitConfig.compose(payload if payload is not None else RateLimitConfig.read_stored())
    logger.info("Rate limits recomposed: this node's environment plus the stored settings")


def _reload_syslog(payload):
    from services.syslog_service import syslog_forwarder
    syslog_forwarder.load_from_db()


def _reload_admin_allowlist(payload):
    from utils import admin_allowlist
    admin_allowlist.invalidate_cache()


HANDLERS = {
    RELOAD_RATE_LIMITS: _reload_rate_limits,
    RELOAD_SYSLOG: _reload_syslog,
    RELOAD_ADMIN_ALLOWLIST: _reload_admin_allowlist,
}


class CommandApplier:
    """Replays cluster_commands in this process, on a connection of its own.

    ``record``: this process owns the node's cursor and its restart (the web worker);
    another process of the node (the scheduler) only reloads its own memory.
    """

    def __init__(self, app, node_id, *, started_at=None, record=True, restart_action=None,
                 handlers=None, tick=None, guard=None, stale_seconds=None, clock=None):
        from services.scheduler_leader import STALE_PASSES
        self.app = app
        self.node_id = node_id
        self.started_at = started_at or PROCESS_STARTED  # this host's clock until the first pass
        self.clock = clock or utc_now  # this host's clock
        self._on_cluster_clock = False
        self.record = record
        self.restart_action = restart_action or restart_this_node
        self.handlers = dict(HANDLERS if handlers is None else handlers)
        self.tick = TICK_SECONDS if tick is None else tick
        self.guard = RESTART_GUARD_SECONDS if guard is None else guard
        self.stale_seconds = STALE_PASSES * 60 if stale_seconds is None else stale_seconds
        self.seen = None
        self.restarting = False
        self._holes = []  # [lo, hi, monotonic deadline]: ids passed over that may still commit
        self._gap = None  # (first missing id, monotonic time it was noticed)
        self._restart_wait = None  # (command id, monotonic first sight, nodes ahead then)
        self._held = None  # the restart waiting for this node's turn; later reloads still apply
        self._engine = None
        self._conn = None
        self._error_logged = False
        self._stop = threading.Event()
        self._stopping = False  # stop() was called: a failed restart does not resume the loop
        self._thread = None

    # -- lifecycle -------------------------------------------------------
    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name='ClusterCommandApplier')
        self._thread.start()
        return self

    def stop(self, timeout=10):
        self._stopping = True
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        self._close()
        if self._engine is not None:
            self._engine.dispose()
            self._engine = None

    def _loop(self):
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self.tick)

    # -- connection ------------------------------------------------------
    def _connection(self):
        if self._conn is not None:
            return self._conn
        if self._engine is None:
            from services.scheduler_leader import _dedicated_engine, application_url
            with self.app.app_context():
                self._engine = _dedicated_engine(application_url())
        self._conn = self._engine.connect().execution_options(isolation_level='AUTOCOMMIT')
        return self._conn

    def _close(self):
        conn, self._conn = self._conn, None
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    # -- one pass --------------------------------------------------------
    def run_once(self):
        """Apply what is new; errors are logged once and retried on the next tick."""
        try:
            conn = self._connection()
            if not self._on_cluster_clock:
                # created_at is on the cluster clock: a host whose clock drifts compares right
                self.started_at = self._cluster_clock(conn, self.started_at)
                self._on_cluster_clock = True
            if self.seen is None:
                self.seen = conn.execute(_INITIAL_SQL, {'t': self.started_at - START_REPLAY}).scalar() or 0
                self._mark_seen(conn, self.seen)
            self._drain(conn)
            self._error_logged = False
        except Exception as e:
            self._close()
            if not self._error_logged:
                logger.error(f"Cluster commands not read on node {self.node_id}: {type(e).__name__}: {e}")
                self._error_logged = True

    def _drain(self, conn):
        now = time.monotonic()
        self._holes = [h for h in self._holes if h[2] > now][-MAX_HOLES:]
        held_before = self._held is not None
        self._drain_rows(conn, now)
        # After the rows: a newer restart committed with the node ahead's return is absorbed first;
        # one held (or failed) during this pass is retried on the next
        if held_before and self._held is not None and not self._stop.is_set():
            self._restart(conn, self._held)

    def _drain_rows(self, conn, now):
        where, params = ['id > :seen'], {'seen': self.seen, 'n': BATCH}
        for i, (lo, hi, _) in enumerate(self._holes):
            where.append(f'id BETWEEN :lo{i} AND :hi{i}')
            params[f'lo{i}'], params[f'hi{i}'] = lo, hi
        rows = conn.execute(text(
            "SELECT id, kind, payload, created_at, node_id FROM cluster_commands "
            f"WHERE {' OR '.join(where)} ORDER BY id LIMIT :n"), params).fetchall()
        for row in rows:
            if self._stop.is_set():
                return  # this process is leaving
            if row.id <= self.seen:
                # Committed after this node moved past it. _apply settles every row for good
                # (applied, absorbed, held in memory, or the process leaves): the hole closes now
                self._fill_hole(row.id)
            elif row.id > self.seen + 1 and not self._gap_passed(row.id, now):
                return
            self._apply(conn, row)

    def _gap_passed(self, next_id, now):
        first_missing = self.seen + 1
        if self._gap is None or self._gap[0] != first_missing:
            self._gap = (first_missing, now)
        if now - self._gap[1] < GAP_GRACE_SECONDS:
            return False
        self._holes.append([first_missing, next_id - 1, now + HOLE_TTL_SECONDS])
        self._gap = None
        return True

    def _fill_hole(self, command_id):
        for hole in self._holes:
            if hole[0] <= command_id <= hole[1]:
                self._holes.remove(hole)
                if hole[0] < command_id:
                    self._holes.append([hole[0], command_id - 1, hole[2]])
                if command_id < hole[1]:
                    self._holes.append([command_id + 1, hole[1], hole[2]])
                return

    def _apply(self, conn, row):
        """The cursor moves past ``row``; a restart may be held or stop this process."""
        if row.node_id and row.node_id != self.node_id:
            self._advance(conn, row.id)
            return
        if row.kind == RESTART:
            if self._held is not None:
                # One restart covers both: it waits for the nodes ahead to pass the newer one
                held = self._held
                self._held = _Held(max(held.id, row.id), max(held.created_at, row.created_at))
                self._advance(conn, row.id)
                return
            self._restart(conn, row)
            return
        handler = self.handlers.get(row.kind)
        if handler is None:
            logger.warning(f"Cluster command {row.id}: unknown kind {row.kind!r}, skipped")
        else:
            try:
                payload = json.loads(row.payload) if row.payload else None
                with self.app.app_context():
                    try:
                        handler(payload)
                    finally:
                        from models import db
                        db.session.remove()
            except Exception as e:
                # Never replayed: one failure must not hold every later command back
                logger.error(f"Cluster command {row.id} ({row.kind}) failed on node "
                             f"{self.node_id}: {type(e).__name__}: {e}")
        self._advance(conn, row.id)

    def _advance(self, conn, command_id):
        self.seen = max(self.seen, command_id)
        self._mark_seen(conn, command_id)

    def _mark_seen(self, conn, command_id):
        """Conditional UPDATE: the node's cursor only moves forward."""
        if self.record:
            conn.execute(_ADVANCE_SQL, {'id': command_id, 'n': self.node_id})

    def _cluster_clock(self, conn, local_instant):
        from services.scheduler_leader import to_cluster_clock
        return to_cluster_clock(local_instant, self.clock(), conn)

    def _claim(self, conn, command_id):
        """True when this process takes the node's restart ``command_id`` (or the node has no row)."""
        if conn.execute(_CLAIM_SQL, {'id': command_id, 'n': self.node_id}).rowcount:
            return True
        return conn.execute(_ROW_SQL, {'n': self.node_id}).first() is None

    def _restart(self, conn, row):
        """Sets _stop when this process leaves; while it waits for its turn, ``row`` is held
        (restart_seen, not command_seen, records the claim) and later reloads go on."""
        if not self.record or row.created_at <= self.started_at:
            # Started after the command (or the scheduler process): nothing to restart here
            self._held = None
            self._advance(conn, row.id)
            return
        nodes = conn.execute(_NODES_SQL).fetchall()
        from services.scheduler_leader import cluster_utc_now
        pending = pending_predecessors(self.node_id, nodes, row.created_at,
                                       cluster_utc_now(conn), self.stale_seconds)
        now = time.monotonic()
        if self._restart_wait is None or self._restart_wait[0] != row.id:
            self._restart_wait = (row.id, now, len(pending))
        _, since, ahead = self._restart_wait
        if pending and now - since < self.guard * ahead:
            self._held = _Held(row.id, row.created_at)
            self._advance(conn, row.id)
            return
        self._restart_wait = None
        self._held = None
        if pending:
            logger.warning(f"Rolling restart: {', '.join(pending)} not back after "
                           f"{self.guard * ahead:.0f}s, node {self.node_id} restarts anyway")
        # Claimed before acting: a sibling process of this node that lost the claim leaves it alone
        previous = conn.execute(_CLAIMED_SQL, {'n': self.node_id}).scalar()
        claimed = self._claim(conn, row.id)
        self._advance(conn, row.id)
        if not claimed:
            return
        self.restarting = True
        logger.warning(f"Rolling restart: node {self.node_id} restarts (command {row.id})")
        self._stop.set()  # this process is leaving: nothing after the restart is applied here
        try:
            self.restart_action()
        except Exception as e:
            # Still on the old process: the claim is given back and the restart retried next pass
            logger.error(f"Rolling restart of node {self.node_id} failed, retried on the next pass: "
                         f"{type(e).__name__}: {e}")
            conn.execute(_RELEASE_SQL, {'prev': previous, 'id': row.id, 'n': self.node_id})
            self.restarting = False
            self._held = _Held(row.id, row.created_at)
            if not self._stopping:
                self._stop.clear()


_applier = None


def start_applier(app, record=True, master_pid=None):
    """HA only: this process's applier; None (no thread, no query) outside HA."""
    global _applier
    from utils.ha import ha_enabled
    if not ha_enabled():
        return None
    if _applier is not None and _applier._thread is not None and _applier._thread.is_alive():
        return _applier
    from config.settings import Config
    _applier = CommandApplier(app, Config.NODE_ID, record=record,
                              restart_action=lambda: restart_this_node(master_pid)).start()
    logger.info(f"Cluster command applier started on node {Config.NODE_ID} (pid {os.getpid()})")
    return _applier
