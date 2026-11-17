"""HA cluster maintenance: while a restore (or an administrator) holds it, no node writes.

One row in ``cluster_maintenance``. Every process's command applier reads it on each tick,
and the request gate when its last reading is older than OBSERVE_TTL_SECONDS. A process
that has seen it refuses writes (503 with Retry-After), leaves /health/ready and then
acknowledges it in ``cluster_nodes``. The lease bounds it when its holder dies. Outside HA
the same view is fed by the local write gate of a restore job (observe_local), and nothing else.
"""
import contextvars
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

from sqlalchemy import event, text

logger = logging.getLogger(__name__)

REASON_RESTORE = 'restore'
REASON_MANUAL = 'manual'
PHASE_DRAINING = 'draining'      # waiting for every node's acknowledgement
PHASE_RESTORING = 'restoring'    # the restore transaction runs
PHASE_COMMITTED = 'committed'    # committed: sessions and the rolling restart still to do
PHASE_RESTARTING = 'restarting'  # a process started after restored_at serves again
PHASE_MANUAL = 'manual'
# The restore has not committed: a lease that ends lifts it, a node that starts waits
UNCOMMITTED = frozenset({PHASE_DRAINING, PHASE_RESTORING})
RENEWED = (PHASE_DRAINING, PHASE_RESTORING, PHASE_COMMITTED)

ROW_ID = 1
LEASE_SECONDS = 300
RENEW_SECONDS = 30
ACK_TIMEOUT_SECONDS = 30
ACK_POLL_SECONDS = 0.5
RESTART_LEASE_SECONDS = 1800
OBSERVE_TTL_SECONDS = 6
RETRY_AFTER_SECONDS = 30
STARTUP_POLL_SECONDS = 2
MANUAL_DEFAULT_MINUTES = 60
MANUAL_MAX_MINUTES = 1440

EXTENSION = 'ucm_cluster_maintenance'
MESSAGE = ("This UCM cluster is in maintenance ({what}): writes are refused until it ends. "
           "Retry later.")

_ROW_SQL = text("SELECT token, reason, phase, started_at, expires_at, restored_at, node_id, actor "
                "FROM cluster_maintenance WHERE id = :id")
_NODES_SQL = text("SELECT node_id, started_at, heartbeat_at, maintenance_ack, "
                  "maintenance_ack_scheduler FROM cluster_nodes ORDER BY node_id")
_ACK_SQL = {
    'web': text("UPDATE cluster_nodes SET maintenance_ack = :t WHERE node_id = :n"),
    'scheduler': text("UPDATE cluster_nodes SET maintenance_ack_scheduler = :t WHERE node_id = :n"),
}

# The request or thread that holds the maintenance writes; nobody else in its process does
_exempt = contextvars.ContextVar('ucm_maintenance_exempt', default=False)
_held = contextvars.ContextVar('ucm_maintenance_hold', default=None)


class MaintenanceActive(Exception):
    """A write this process refuses while the cluster is in maintenance (answered 503)."""


class MaintenanceRefused(Exception):
    """The maintenance could not be set or kept; nothing was restored (answered 409)."""
    code = 'maintenance_refused'


class MaintenanceBusy(MaintenanceRefused):
    code = 'maintenance_in_progress'


class NodesNotAcknowledged(MaintenanceRefused):
    code = 'maintenance_not_acknowledged'

    def __init__(self, missing):
        self.missing = missing
        names = ', '.join(f"{node} ({', '.join(parts)})" for node, parts in missing.items())
        super().__init__(f"Cluster maintenance not acknowledged within {ACK_TIMEOUT_SECONDS}s by "
                         f"node(s) {names}: nothing was restored and the maintenance is lifted. "
                         "A node that is gone counts until its heartbeat is stale (3 minutes).")


class MaintenanceLost(MaintenanceRefused):
    code = 'maintenance_lost'


# -- what this process has seen ----------------------------------------------

class View:
    """One application's last reading of the row, judged on this host's monotonic clock."""

    def __init__(self):
        self.row = None
        self.deadline = 0.0
        self.observed = None
        self.process_started = None  # on the cluster clock
        self._logged = None

    def set(self, row, now):
        self.observed = time.monotonic()
        if row is not None:
            self.deadline = self.observed + (row['expires_at'] - now).total_seconds()
        self.row = row
        state = (row['token'], row['phase']) if row is not None and self.active() else None
        if state != self._logged:
            self._logged = state
            if state is None:
                logger.info("Cluster maintenance over for this process: writes accepted")
            else:
                logger.warning(f"Cluster maintenance ({row['reason']}, {row['phase']}, set by node "
                               f"{row['node_id']}): this process refuses writes")

    def active(self) -> bool:
        row = self.row
        if row is None:
            return False
        if time.monotonic() >= self.deadline and row['phase'] != PHASE_COMMITTED:
            return False  # a committed restore holds until a node completes it (tend)
        if row['phase'] == PHASE_RESTARTING and row['restored_at'] is not None \
                and self.process_started is not None and self.process_started > row['restored_at']:
            return False  # this process loaded the restored state
        return True

    def public(self):
        row = self.row
        if row is None or not self.active():
            return None
        return {'reason': row['reason'], 'phase': row['phase'], 'node_id': row['node_id'],
                'started_at': _iso(row['started_at']), 'expires_at': _iso(row['expires_at']),
                'restored_at': _iso(row['restored_at'])}


def _iso(value):
    from utils.datetime_utils import utc_isoformat
    return utc_isoformat(value) if value is not None else None


def view_of(app):
    view = app.extensions.get(EXTENSION)
    if view is None:
        view = app.extensions.setdefault(EXTENSION, View())
    return view


def read_row(executor):
    row = executor.execute(_ROW_SQL, {'id': ROW_ID}).first()
    return None if row is None else dict(row._mapping)


def observe(app, executor):
    """Read the row into ``app``'s view; returns the row."""
    from services.scheduler_leader import cluster_utc_now
    view = view_of(app)
    if view.process_started is None:
        from services.cluster_commands import PROCESS_STARTED
        from services.scheduler_leader import to_cluster_clock
        from utils.datetime_utils import utc_now
        view.process_started = to_cluster_clock(PROCESS_STARTED, utc_now(), executor)
    row = read_row(executor)
    view.set(row, cluster_utc_now(executor))
    return row


def _app():
    from flask import current_app, has_app_context
    return current_app._get_current_object() if has_app_context() else None


LOCAL_REASON = 'local_restore'


def observe_local(app):
    """Single node: the write gate a restore job holds, read from its local state file
    (cheap: one stat, one read when it changed). The view refuses writes while it is up."""
    from services.jobs import restore as restore_job
    from utils.datetime_utils import utc_now
    view = view_of(app)
    reader = getattr(view, 'local_reader', None)
    if reader is None:
        reader = view.local_reader = restore_job.StateReader()
    state = reader.read()
    row = None
    if state is not None:
        now = utc_now()
        row = {'token': state.get('job_id'), 'reason': LOCAL_REASON, 'phase': PHASE_RESTORING,
               'started_at': _from_epoch(state.get('started_at')) or now, 'expires_at': now + timedelta(
                   seconds=max(0.0, state['expires'] - time.time())),
               'restored_at': None, 'node_id': None, 'actor': state.get('actor')}
        view.set(row, now)
    elif view.row is not None:
        view.set(None, None)
    return view


def _from_epoch(seconds):
    """A naive UTC datetime, like utc_now(), from a time.time() value; None if unreadable."""
    from datetime import datetime, timezone
    if not isinstance(seconds, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(seconds, timezone.utc).replace(tzinfo=None)
    except (OverflowError, OSError, ValueError):
        return None


def current(refresh=True):
    """This application's view: HA, read again when older than OBSERVE_TTL_SECONDS; a single
    node, the local restore gate read on every refresh."""
    from utils.ha import ha_enabled
    app = _app()
    if app is None:
        return None
    if not ha_enabled():
        if refresh:
            try:
                observe_local(app)
            except Exception as e:
                logger.error(f"Restore write gate not readable: {type(e).__name__}: {e}")
        return view_of(app)
    view = view_of(app)
    if refresh and (view.observed is None or time.monotonic() - view.observed > OBSERVE_TTL_SECONDS):
        from models import db
        try:
            observe(app, db.session)
        except Exception as e:
            db.session.rollback()
            logger.error(f"Cluster maintenance not readable: {type(e).__name__}: {e}")
    return view


def active_here(refresh=True) -> bool:
    """This process is in maintenance (whoever asks): /health/ready answers 503."""
    view = current(refresh)
    return bool(view and view.active())


def blocks_writes(app=None) -> bool:
    """A write from here would be refused; never queries (called from engine events)."""
    if _exempt.get():
        return False
    app = app or _app()
    view = app.extensions.get(EXTENSION) if app is not None else None
    return bool(view and view.active())


@contextmanager
def exempt():
    """Writes of the maintenance itself, the heartbeat and the holder's own request."""
    token = _exempt.set(True)
    try:
        yield
    finally:
        _exempt.reset(token)


# -- refusing writes ---------------------------------------------------------

_WRITE = re.compile(r'\s*(INSERT|UPDATE|DELETE|MERGE|TRUNCATE|CREATE|ALTER|DROP|COPY)\b', re.I)
_CTE_WRITE = re.compile(r'\b(INSERT|UPDATE|DELETE|MERGE)\b', re.I)
_WROTE = 'ucm_maintenance_wrote'


def is_write(statement) -> bool:
    if _WRITE.match(statement):
        return True
    return statement.lstrip()[:4].upper() == 'WITH' and bool(_CTE_WRITE.search(statement))


def install_engine_guard(app, engine):
    """No write statement, and no commit of a transaction that wrote, once ``app`` is in maintenance.

    The commit check also stops a request that wrote before the maintenance was seen.
    """
    guarded = app.extensions.setdefault(EXTENSION + '_engines', set())
    if id(engine) in guarded:
        return
    guarded.add(id(engine))
    view = view_of(app)

    def blocked():
        return view.active() and not _exempt.get()

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        if not is_write(statement):
            return
        if blocked():
            raise MaintenanceActive(_message(view))
        conn.info[_WROTE] = True

    def on_commit(conn):
        if conn.info.pop(_WROTE, False) and blocked():
            raise MaintenanceActive(_message(view))

    def on_rollback(conn):
        # An invalidated connection's info is cleared when its record reconnects; reading it
        # here would raise and turn every rollback after a disconnect into an error
        if not conn.invalidated:
            conn.info.pop(_WROTE, None)

    def on_checkin(dbapi_connection, record):
        record.info.pop(_WROTE, None)

    event.listen(engine, 'before_cursor_execute', before_cursor_execute)
    event.listen(engine, 'commit', on_commit)
    event.listen(engine, 'rollback', on_rollback)
    event.listen(engine, 'checkin', on_checkin)


LOCAL_MESSAGE = ("This UCM instance is restoring a backup: writes are refused until the restore "
                 "ends. Retry later.")


def _what(view):
    row = view.row or {}
    return 'a backup restore' if row.get('reason') in (REASON_RESTORE, LOCAL_REASON) \
        else 'set by an administrator'


def _message(view):
    if (view.row or {}).get('reason') == LOCAL_REASON:
        return LOCAL_MESSAGE
    return MESSAGE.format(what=_what(view))


SAFE_METHODS = frozenset({'GET', 'HEAD', 'OPTIONS'})
# Enrollment and signing protocols, whatever the method (SCEP enrolls over GET too)
REFUSED_BLUEPRINTS = frozenset({'acme', 'acme_proxy', 'est', 'scep_protocol', 'xcep_protocol',
                                'wstep_protocol', 'tsa'})
# An OCSP request is a query, whatever the method
READ_BLUEPRINTS = frozenset({'ocsp'})
OPEN_BLUEPRINTS = frozenset({'health'})
CONTROL_ENDPOINTS = frozenset({'system_v2.maintenance_status', 'system_v2.maintenance_begin',
                               'system_v2.maintenance_lift'})
# Routes that start a background job: authenticated first, then refused by start_job itself,
# so GET and POST answer the same 503
JOB_START_ENDPOINTS = frozenset({'audit_v2.verify_integrity', 'system_v2.create_backup',
                                 'settings_v2.create_backup', 'system_v2.restore_backup',
                                 'settings_v2.restore_backup'})
# The cancellation of the restore that holds the maintenance: a flag on its own job row.
# Through a restore's maintenance only; holds() decides which job it may write.
JOB_CONTROL_ENDPOINTS = frozenset({'system_v2.cancel_job'})


def holds(job, view=None) -> bool:
    """``job`` (a job row) is the restore that holds the maintenance this process sees: the one
    job whose cancellation writes through it. A manual maintenance is held by no job."""
    view = view or current(refresh=False)
    row = (view.row or {}) if view is not None and view.active() else {}
    if job is None or job.get('kind') != 'restore' or job.get('state') not in ('pending', 'running'):
        return False
    if row.get('reason') == LOCAL_REASON:
        return row.get('token') == job.get('id')
    if row.get('reason') == REASON_RESTORE:
        return job.get('node_id') in (None, row.get('node_id'))
    return False


def refusal(view=None, message=None):
    from flask import jsonify
    from utils.response import PROBLEM_CONTENT_TYPE, build_problem
    view = view or current(refresh=False)
    local = view is not None and (view.row or {}).get('reason') == LOCAL_REASON
    body = build_problem(message or (_message(view) if view else MESSAGE.format(
        what='set by an administrator')), 503,
        title='Restore in progress' if local else 'Cluster maintenance')
    body['code'] = 'maintenance'
    body['maintenance'] = view.public() if view else None
    response = jsonify(body)
    response.mimetype = PROBLEM_CONTENT_TYPE
    response.status_code = 503
    response.headers['Retry-After'] = str(RETRY_AFTER_SECONDS)
    return response


def gate():
    """before_request: what a node in maintenance still serves (health, reads, OCSP, CRL, AIA)."""
    from flask import request
    from utils.public_endpoints import PROBE_PATHS
    if request.path in PROBE_PATHS:
        return None  # served in maintenance; readiness reads the row itself, liveness never
    view = current(refresh=True)
    if view is None or not view.active():
        return None
    if (request.blueprint in OPEN_BLUEPRINTS or request.endpoint in CONTROL_ENDPOINTS
            or request.endpoint in JOB_START_ENDPOINTS):
        return None
    if request.endpoint in JOB_CONTROL_ENDPOINTS and (view.row or {}).get('reason') in (
            REASON_RESTORE, LOCAL_REASON):
        return None  # the route writes only for the restore that holds it (holds())
    if request.blueprint in REFUSED_BLUEPRINTS:
        return refusal(view)
    if request.method in SAFE_METHODS or request.blueprint in READ_BLUEPRINTS:
        return None
    return refusal(view)


def init_app(app):
    """Gate, write guard and 503 answer; outside HA only a local restore job raises it."""
    from models import db
    view_of(app)
    app.before_request(gate)
    app.register_error_handler(MaintenanceActive, lambda e: refusal())
    with app.app_context():
        install_engine_guard(app, db.engine)


def wait_while_restoring(url, poll=None):
    """HA start: an uncommitted restore holds the cluster, so this node neither migrates nor
    writes before it ends (commit, failure or lease)."""
    from sqlalchemy import inspect
    from services.scheduler_leader import _dedicated_engine, cluster_utc_now
    poll = STARTUP_POLL_SECONDS if poll is None else poll
    engine = _dedicated_engine(url)
    said = None
    try:
        while True:
            try:
                with engine.connect() as conn:
                    if 'cluster_maintenance' not in inspect(conn).get_table_names():
                        return
                    row, now = read_row(conn), cluster_utc_now(conn)
            except Exception as e:
                logger.warning(f"Cluster maintenance not read at start: {type(e).__name__}")
                return
            if row is None or row['phase'] not in UNCOMMITTED or row['expires_at'] <= now:
                if said:
                    logger.warning("Cluster maintenance: the restore is over, this node starts")
                return
            if said != row['token']:
                said = row['token']
                logger.warning(f"Cluster maintenance: a restore runs on node {row['node_id']}, "
                               "this node waits for it before starting")
            time.sleep(poll)
    finally:
        engine.dispose()


# -- holding it --------------------------------------------------------------

def _stale_seconds():
    from services.scheduler_leader import STALE_PASSES
    from services.scheduler_service import get_scheduler
    return STALE_PASSES * get_scheduler().wake_interval


def node_states(executor, token=None, stale_seconds=None):
    """Every registered node: fresh or not, and whether each process acknowledged ``token``."""
    from services.scheduler_leader import cluster_utc_now
    stale_seconds = _stale_seconds() if stale_seconds is None else stale_seconds
    now = cluster_utc_now(executor)
    nodes = []
    for row in executor.execute(_NODES_SQL).fetchall():
        nodes.append({
            'node_id': row.node_id,
            'fresh': (now - row.heartbeat_at).total_seconds() <= stale_seconds,
            'started_at': row.started_at,
            'web': token is not None and row.maintenance_ack == token,
            'scheduler': token is not None and row.maintenance_ack_scheduler == token,
        })
    return nodes


class Hold:
    """This node's hold on the maintenance: begin(), wait_for_acks(), then close()."""

    def __init__(self, app, token, reason, renew):
        self.app = app
        self.token = token
        self.reason = reason
        self.finished = False
        self._stop = threading.Event()
        self._renewer = None
        if renew:
            self._renewer = threading.Thread(target=self._renew_loop, daemon=True,
                                             name='ClusterMaintenanceLease')

    @classmethod
    def begin(cls, reason, actor, *, phase, lease_seconds):
        from config.settings import Config
        from models import ClusterMaintenance, db
        from services.scheduler_leader import cluster_utc_now
        from sqlalchemy.exc import IntegrityError
        app = _app()
        token = str(uuid.uuid4())
        with exempt():
            try:
                now = cluster_utc_now()
                existing = read_row(db.session)
                if existing is not None:
                    if existing['expires_at'] > now or existing['phase'] == PHASE_COMMITTED:
                        raise MaintenanceBusy(
                            f"A cluster maintenance ({existing['reason']}, {existing['phase']}) set by "
                            f"node {existing['node_id']} is in progress")
                    db.session.execute(text("DELETE FROM cluster_maintenance WHERE id = :id "
                                            "AND token = :t"), {'id': ROW_ID, 't': existing['token']})
                db.session.add(ClusterMaintenance(
                    id=ROW_ID, token=token, reason=reason, phase=phase, started_at=now,
                    expires_at=now + timedelta(seconds=lease_seconds), node_id=Config.NODE_ID,
                    actor=actor))
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                raise MaintenanceBusy("Another node set a cluster maintenance at the same time") from None
            except Exception:
                db.session.rollback()
                raise
            observe(app, db.session)
        logger.warning(f"Cluster maintenance set ({reason}) by {actor or 'system'} on node "
                       f"{Config.NODE_ID}")
        hold = cls(app, token, reason, renew=reason == REASON_RESTORE)
        if hold._renewer is not None:
            hold._renewer.start()
        return hold

    def unacknowledged(self):
        from models import db
        with exempt():
            try:
                nodes = node_states(db.session, self.token)
            finally:
                db.session.rollback()
        return {n['node_id']: [part for part in ('web', 'scheduler') if not n[part]]
                for n in nodes if n['fresh'] and not (n['web'] and n['scheduler'])}

    def wait_for_acks(self):
        """Returns once every fresh node's processes refuse writes; NodesNotAcknowledged otherwise."""
        deadline = time.monotonic() + ACK_TIMEOUT_SECONDS
        while True:
            missing = self.unacknowledged()
            if not missing:
                return
            if time.monotonic() >= deadline:
                raise NodesNotAcknowledged(missing)
            time.sleep(ACK_POLL_SECONDS)

    def _update(self, sql, **params):
        from models import db
        with exempt():
            try:
                done = db.session.execute(text(sql), {'id': ROW_ID, 't': self.token, **params}).rowcount
                db.session.commit()
            except Exception:
                db.session.rollback()
                raise
        return done

    def start_restore(self):
        if self._update("UPDATE cluster_maintenance SET phase = :p WHERE id = :id AND token = :t "
                        "AND phase = :was", p=PHASE_RESTORING, was=PHASE_DRAINING) != 1:
            raise MaintenanceLost("The cluster maintenance was lifted before the restore started: "
                                  "nothing was restored")

    def _renew_loop(self):
        from models import db
        from services.scheduler_leader import cluster_utc_now
        while not self._stop.wait(RENEW_SECONDS):
            # On a connection of its own: the restore's session turns commits into flushes
            with self.app.app_context(), exempt():
                try:
                    with db.engine.begin() as conn:
                        conn.execute(text(
                            "UPDATE cluster_maintenance SET expires_at = :e WHERE id = :id "
                            f"AND token = :t AND phase IN ({', '.join(repr(p) for p in RENEWED)})"),
                            {'id': ROW_ID, 't': self.token,
                             'e': cluster_utc_now(conn) + timedelta(seconds=LEASE_SECONDS)})
                except Exception as e:
                    logger.error(f"Cluster maintenance lease not renewed: {type(e).__name__}: {e}")

    def before_commit(self, session):
        """In the restore transaction: still ours and in its lease, or the restore rolls back."""
        from services.scheduler_leader import cluster_utc_now
        now = cluster_utc_now(session)
        done = session.execute(text(
            "UPDATE cluster_maintenance SET phase = :p, expires_at = :e WHERE id = :id AND token = :t "
            "AND phase = :was AND expires_at > :now"),
            {'p': PHASE_COMMITTED, 'was': PHASE_RESTORING, 'id': ROW_ID, 't': self.token, 'now': now,
             'e': now + timedelta(seconds=LEASE_SECONDS)}).rowcount
        if done != 1:
            raise MaintenanceLost("The cluster maintenance ended or was lifted during the restore: "
                                  "it was rolled back, nothing was restored")

    def finish(self):
        """The rolling restart, in the transaction that opens the cluster to restarted nodes."""
        from models import db
        from services import cluster_commands
        from services.scheduler_leader import cluster_utc_now
        with exempt():
            try:
                now = cluster_utc_now()
                cluster_commands.emit(cluster_commands.RESTART)
                done = db.session.execute(text(
                    "UPDATE cluster_maintenance SET phase = :p, restored_at = :now, expires_at = :e "
                    "WHERE id = :id AND token = :t AND phase = :was"),
                    {'p': PHASE_RESTARTING, 'was': PHASE_COMMITTED, 'id': ROW_ID, 't': self.token,
                     'now': now, 'e': now + timedelta(seconds=RESTART_LEASE_SECONDS)}).rowcount
                if done != 1:
                    db.session.rollback()
                    return False, ("The cluster maintenance was lifted meanwhile: restart every node "
                                   "yourself")
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Restore: rolling restart not requested: {type(e).__name__}: {e}")
                return False, "The rolling restart could not be requested"
            self.finished = True
            observe(self.app, db.session)
        return True, cluster_commands.ROLLING_RESTART_MESSAGE

    def lift_unchanged(self):
        """The archive carried no data: lifted with no restart, as a single node asks none."""
        if self._update("DELETE FROM cluster_maintenance WHERE id = :id AND token = :t"):
            logger.warning("Cluster maintenance lifted: the archive restored nothing")
        self.finished = True
        from models import db
        observe(self.app, db.session)

    def close(self):
        """Not finished: lifted when nothing was committed, else left to any node to complete now."""
        self._stop.set()
        if self._renewer is not None and self._renewer.is_alive():
            self._renewer.join(10)
        if self.finished or self.reason != REASON_RESTORE:
            return
        from models import db
        from services.scheduler_leader import cluster_utc_now
        with exempt():
            try:
                row = read_row(db.session)
                if row is not None and row['token'] == self.token:
                    if row['phase'] == PHASE_COMMITTED:
                        db.session.execute(text("UPDATE cluster_maintenance SET expires_at = :now "
                                                "WHERE id = :id AND token = :t"),
                                           {'id': ROW_ID, 't': self.token, 'now': cluster_utc_now()})
                    else:
                        db.session.execute(text("DELETE FROM cluster_maintenance WHERE id = :id "
                                                "AND token = :t"), {'id': ROW_ID, 't': self.token})
                        logger.warning("Cluster maintenance lifted: the restore did not commit")
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                logger.error(f"Cluster maintenance not lifted after the restore, its lease ends it: "
                             f"{type(e).__name__}: {e}")
            try:
                observe(self.app, db.session)
            except Exception:
                db.session.rollback()


@contextmanager
def restore_window(actor, preflight=None):
    """HA: the restore runs inside this; None outside HA, where nothing changes.
    `preflight` runs first: what it refuses (a wrong password) never reaches the cluster."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        yield None
        return
    if preflight is not None:
        preflight()
    exempt_token = _exempt.set(True)
    try:
        hold = Hold.begin(REASON_RESTORE, actor, phase=PHASE_DRAINING, lease_seconds=LEASE_SECONDS)
        held_token = _held.set(hold)
        try:
            hold.wait_for_acks()
            hold.start_restore()
            yield hold
        finally:
            _held.reset(held_token)
            hold.close()
    finally:
        _exempt.reset(exempt_token)


def before_restore_commit(session):
    """Called by the restore's single transaction just before it commits."""
    hold = _held.get()
    if hold is not None:
        hold.before_commit(session)


# -- lease ends and lifts, by any node's web worker ----------------------------

def tend(stale_seconds=None):
    """In an app context: a lease that ended lifts the maintenance (a committed restore is
    completed first); a rolling restart that every fresh node has passed lifts it too."""
    from models import db
    from services.scheduler_leader import cluster_utc_now
    with exempt():
        try:
            row = read_row(db.session)
            if row is None:
                return
            now = cluster_utc_now()
            if row['expires_at'] <= now:
                if row['phase'] == PHASE_COMMITTED:
                    complete_committed(row, now)
                    return
                if _delete(row['token'], "AND expires_at <= :now", now=now):
                    logger.warning(f"Cluster maintenance ({row['reason']}, {row['phase']}) lifted: "
                                   f"its lease ended (set by node {row['node_id']})")
            elif row['phase'] == PHASE_RESTARTING and _every_node_restarted(
                    db.session, row['restored_at'], stale_seconds):
                if _delete(row['token'], "AND phase = :p", p=PHASE_RESTARTING):
                    logger.warning("Cluster maintenance lifted: every node restarted on the restored state")
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise


def _delete(token, condition, **params):
    from models import db
    return db.session.execute(text(f"DELETE FROM cluster_maintenance WHERE id = :id AND token = :t "
                                   f"{condition}"), {'id': ROW_ID, 't': token, **params}).rowcount


def _every_node_restarted(executor, restored_at, stale_seconds):
    nodes = [n for n in node_states(executor, stale_seconds=stale_seconds) if n['fresh']]
    return all(n['started_at'] > restored_at for n in nodes)


def complete_committed(row, now):
    """A committed restore whose holder stopped: its sessions are revoked and the rolling
    restart is asked here, as the holder would have done (one node wins the UPDATE)."""
    from models import db
    from services import cluster_commands
    from services.backup.restore.invalidate import (
        _advance_session_epoch, _revoke_database_sessions, _revoke_flask_sessions)
    done = db.session.execute(text(
        "UPDATE cluster_maintenance SET phase = :p, restored_at = :now, expires_at = :e "
        "WHERE id = :id AND token = :t AND phase = :was AND expires_at <= :now"),
        {'p': PHASE_RESTARTING, 'was': PHASE_COMMITTED, 'id': ROW_ID, 't': row['token'], 'now': now,
         'e': now + timedelta(seconds=RESTART_LEASE_SECONDS)}).rowcount
    if done != 1:
        db.session.rollback()
        return False
    # Only the node that won the UPDATE revokes: the epoch commits with the phase and
    # the restart, so a loser never refuses the sessions opened since
    cluster_commands.emit(cluster_commands.RESTART)
    # A restore job that already passed its sessions step advanced the epoch: not twice
    from services.jobs.restore import claim_sessions
    if claim_sessions(db.session) == 'done':
        db.session.commit()
        logger.warning(f"Cluster maintenance: the restore committed by node {row['node_id']} had "
                       "revoked its sessions; rolling restart requested here")
        return True
    _advance_session_epoch()
    try:
        _revoke_database_sessions()
        _revoke_flask_sessions()
    except Exception as e:
        # Committed above and never retried: the epoch already refuses what these rows list
        db.session.rollback()
        logger.error(f"Cluster maintenance: session rows left after the completed restore ({e}); "
                     "the session epoch refuses them")
    logger.warning(f"Cluster maintenance: the restore committed by node {row['node_id']} was "
                   "completed here (sessions revoked, rolling restart requested)")
    return True


# -- by hand ------------------------------------------------------------------

def begin_manual(actor, minutes):
    """Set (or extend) the manual maintenance; returns the node states once acknowledged."""
    from models import db
    from services.scheduler_leader import cluster_utc_now
    with exempt():
        row = read_row(db.session)
        if row is not None and row['reason'] == REASON_MANUAL and row['expires_at'] > cluster_utc_now():
            db.session.execute(text("UPDATE cluster_maintenance SET expires_at = :e WHERE id = :id "
                                    "AND token = :t"),
                               {'id': ROW_ID, 't': row['token'],
                                'e': cluster_utc_now() + timedelta(minutes=minutes)})
            db.session.commit()
            hold, created = Hold(_app(), row['token'], REASON_MANUAL, renew=False), False
        else:
            hold = Hold.begin(REASON_MANUAL, actor, phase=PHASE_MANUAL, lease_seconds=minutes * 60)
            created = True
        try:
            hold.wait_for_acks()
        except NodesNotAcknowledged:
            if created:  # an extension keeps the maintenance already acknowledged
                _delete(hold.token, '')
                db.session.commit()
                observe(_app(), db.session)
            raise
        observe(_app(), db.session)
    return hold.token


def lift(actor):
    """Lift whatever maintenance holds, from any node; a committed restore is completed first.
    Returns the lifted row, or None."""
    from models import db
    from services.scheduler_leader import cluster_utc_now
    with exempt():
        try:
            row = read_row(db.session)
            if row is None:
                return None
            if row['phase'] == PHASE_COMMITTED:
                db.session.execute(text("UPDATE cluster_maintenance SET expires_at = :now WHERE id = :id "
                                        "AND token = :t"),
                                   {'id': ROW_ID, 't': row['token'], 'now': cluster_utc_now()})
                db.session.commit()
                complete_committed(row, cluster_utc_now())
            _delete(row['token'], '')
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        observe(_app(), db.session)
    logger.warning(f"Cluster maintenance ({row['reason']}, {row['phase']}) lifted by {actor}")
    return row


def status():
    """The row and every node's acknowledgement of it, for the status route."""
    from models import db
    row = read_row(db.session)
    nodes = node_states(db.session, row['token'] if row else None)
    db.session.rollback()
    view = current(refresh=True)
    return {
        'maintenance': None if row is None else {
            'reason': row['reason'], 'phase': row['phase'], 'node_id': row['node_id'],
            'actor': row['actor'], 'started_at': _iso(row['started_at']),
            'expires_at': _iso(row['expires_at']), 'restored_at': _iso(row['restored_at'])},
        'this_node_refuses_writes': bool(view and view.active()),
        'nodes': [{'node_id': n['node_id'], 'fresh': n['fresh'],
                   'acknowledged': n['web'] and n['scheduler'],
                   'started_at': _iso(n['started_at'])} for n in nodes],
    }
