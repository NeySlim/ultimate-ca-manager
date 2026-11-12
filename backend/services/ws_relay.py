"""WebSocket events relayed between processes and nodes without Redis.

No browser is connected to the scheduler process. Without a message queue it appends each
event to websocket_relay from one writer thread, in emission order, and every web worker
emits to its own clients the rows newer than its cursor. In HA the web workers publish too:
each emits to its own clients at once and skips its own rows when it reads them back.
On PostgreSQL a NOTIFY wakes the readers; the table stays the source. With a message queue
none of this runs.
"""
import json
import logging
import secrets
import threading
import time
from collections import deque
from datetime import timedelta
from itertools import islice

from sqlalchemy import DateTime, bindparam, text
from sqlalchemy.exc import DBAPIError

from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)

# One primary-key range read per worker every 2 s, empty at rest: the cluster applier's cadence
TICK_SECONDS = 2.0
# A worker that was away for longer starts at the newest row: older ones are of no use
RETENTION = timedelta(minutes=10)
PURGE_EVERY_SECONDS = 60.0
# Events kept in memory while the database is unreachable; the oldest go first
QUEUE_MAX = 1000
BATCH = 200
# A missing id below a newer one is another emitter still committing: wait this long
GAP_GRACE_SECONDS = 4.0
# An id passed over that commits later is still delivered within this window
HOLE_TTL_SECONDS = 120.0
MAX_HOLES = 32
# Payload key naming the publishing process; removed before a browser sees the event
ORIGIN_KEY = '_origin'
# NOTIFY only wakes the readers up: one lost is caught up on the next tick. Its payload is
# the schema, so installations sharing a database do not wake each other
CHANNEL = 'ucm_ws_relay'
_NOTIFY_SQL = text(f"SELECT pg_notify('{CHANNEL}', current_schema())")
STOP_SLICE_SECONDS = 0.5

# Typed binds: a raw datetime goes through the deprecated sqlite3 adapter
_INSERT_SQL = text("INSERT INTO websocket_relay (created_at, room, payload) VALUES (:t, :r, :p)"
                   ).bindparams(bindparam('t', type_=DateTime()))
_PURGE_SQL = text("DELETE FROM websocket_relay WHERE created_at < :t"
                  ).bindparams(bindparam('t', type_=DateTime()))
_LAST_SQL = text("SELECT COALESCE(MAX(id), 0) FROM websocket_relay")
_SQLITE_SEQ_SQL = text("SELECT seq FROM sqlite_sequence WHERE name = 'websocket_relay'")
_PG_SEQ_NAME_SQL = text("SELECT pg_get_serial_sequence('websocket_relay', 'id')")


def _newest_id(conn):
    """Highest id ever issued: the sequence, which a purge that emptied the table leaves ahead of MAX(id)."""
    newest = conn.execute(_LAST_SQL).scalar() or 0
    if conn.dialect.name == 'sqlite':
        issued = conn.execute(_SQLITE_SEQ_SQL).scalar()
    elif conn.dialect.name == 'postgresql':
        name = conn.execute(_PG_SEQ_NAME_SQL).scalar()
        issued = None
        try:
            # A role without SELECT on the sequence falls back to MAX(id); the savepoint keeps the transaction usable
            with conn.begin_nested():
                issued = conn.execute(text(f"SELECT CASE WHEN is_called THEN last_value ELSE 0 END FROM {name}")
                                      ).scalar() if name else None
        except DBAPIError:
            issued = None
    else:
        issued = None
    return max(newest, issued or 0)


class RelayPublisher:
    """Emitting side: publish() only queues, one thread writes the rows in order and purges."""

    def __init__(self, engine, *, clock=utc_now, monotonic=time.monotonic,
                 retry_seconds=TICK_SECONDS, purge_every=PURGE_EVERY_SECONDS,
                 retention=RETENTION, queue_max=QUEUE_MAX, batch=BATCH, origin=None):
        self.engine = engine
        self.origin = origin  # set on a process that also reads the relay
        self.clock = clock
        self._monotonic = monotonic
        self.retry_seconds = retry_seconds
        self.purge_every = purge_every
        self.retention = retention
        self.queue_max = queue_max
        self.batch = batch
        self._queue = deque()  # (seq, room, payload json, created_at)
        self._seq = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._failing = False
        self._dropped = 0
        self._next_purge = 0.0
        self._last_written = None  # created_at of the newest row this publisher wrote

    def publish(self, room, payload):
        """Queue one event for every web worker; never waits on the database, never raises."""
        if self.origin is not None:
            payload = dict(payload, **{ORIGIN_KEY: self.origin})
        try:
            item_payload = json.dumps(payload, allow_nan=False)
        except (TypeError, ValueError) as e:
            logger.warning(f"WebSocket event for {room} not relayed: {e}")
            return
        with self._lock:
            self._seq += 1
            if len(self._queue) >= self.queue_max:
                self._queue.popleft()
                self._dropped += 1
            self._queue.append((self._seq, room, item_payload, self.clock()))
            if self._thread is None and not self._stop.is_set():
                self._thread = threading.Thread(target=self._loop, daemon=True,
                                                name='WebSocketRelayWriter')
                self._thread.start()
        self._wake.set()

    def stop(self, timeout=5.0):
        """Write what is queued (best effort within ``timeout``), then stop the thread."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)

    def _loop(self):
        while True:
            self._wake.wait(self._wait_seconds())
            self._wake.clear()
            self.run_once()
            if self._stop.is_set():
                return

    def _wait_seconds(self):
        """Retry while failing, wake to purge while its own rows remain, else sleep until an event."""
        if self._failing:
            return self.retry_seconds
        if self._last_written is not None:
            return self.purge_every
        return None

    def run_once(self):
        try:
            self._write_queued()
            self._purge_if_due()
        except Exception as e:
            if not self._failing:
                logger.error(f"WebSocket events not relayed to the web workers, retried: "
                             f"{type(e).__name__}: {e}")
            self._failing = True
            return
        if self._failing or self._dropped:
            logger.warning(f"WebSocket relay back; {self._dropped} event(s) dropped meanwhile")
        self._failing = False
        self._dropped = 0

    def _write_queued(self):
        while True:
            with self._lock:
                batch = list(islice(self._queue, self.batch))
            if not batch:
                return
            # One transaction per batch: its ids follow the queue order
            with self.engine.begin() as conn:
                conn.execute(_INSERT_SQL, [{'t': t, 'r': room, 'p': payload}
                                           for _, room, payload, t in batch])
                if conn.dialect.name == 'postgresql':
                    conn.execute(_NOTIFY_SQL)  # sent at commit, with the rows
            with self._lock:
                while self._queue and self._queue[0][0] <= batch[-1][0]:
                    self._queue.popleft()
            self._last_written = batch[-1][3]

    def _purge_if_due(self):
        if self._last_written is None or self._monotonic() < self._next_purge:
            return
        cutoff = self.clock() - self.retention
        with self.engine.begin() as conn:
            removed = conn.execute(_PURGE_SQL, {'t': cutoff}).rowcount
        self._next_purge = self._monotonic() + self.purge_every
        if removed:
            logger.debug(f"Purged {removed} relayed WebSocket event(s)")
        if self._last_written < cutoff:
            self._last_written = None  # nothing of ours is left: sleep until the next event


class RelayReader:
    """Worker side: emits each row newer than its cursor once, in id order, from its own thread."""

    def __init__(self, engine, deliver, *, tick=TICK_SECONDS, monotonic=time.monotonic,
                 gap_grace=None, batch=BATCH, skip_origin=None, wakeup=None):
        self.engine = engine
        self.deliver = deliver
        # This process's own rows: its clients got them when they were emitted
        self.skip_origin = skip_origin
        self.wakeup = wakeup  # PgWakeup, or None: the tick alone
        self.tick = tick
        self._monotonic = monotonic
        self.gap_grace = GAP_GRACE_SECONDS if gap_grace is None else gap_grace
        self.batch = batch
        self.seen = None  # last id delivered; None until the first read
        self._holes = []  # [lo, hi, monotonic deadline]: ids passed over that may still commit
        self._gap = None  # (first missing id, monotonic time it was noticed)
        self._error_logged = False
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._loop, daemon=True, name='WebSocketRelayReader')
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout)
        if self.wakeup is not None and (self._thread is None or not self._thread.is_alive()):
            self.wakeup.close()

    def _loop(self):
        try:
            while not self._stop.is_set():
                self.run_once()
                if self.wakeup is not None:
                    self.wakeup.wait(self.tick, self._stop)
                else:
                    self._stop.wait(self.tick)
        finally:
            # A thread that outlived stop()'s join (a slow connect) still releases its LISTEN
            if self.wakeup is not None:
                self.wakeup.close()

    def run_once(self):
        """Deliver what is new; a database error is logged once and retried on the next tick."""
        try:
            with self.engine.connect() as conn:
                if self.seen is None:
                    # Starts at the newest id issued: what was emitted before this worker is not replayed
                    self.seen = _newest_id(conn)
                    rows = []
                else:
                    rows = self._read(conn)
        except Exception as e:
            if not self._error_logged:
                logger.error(f"WebSocket relay not read: {type(e).__name__}: {e}")
                self._error_logged = True
            return
        self._error_logged = False
        self._take(rows)

    def _read(self, conn):
        now = self._monotonic()
        self._holes = [h for h in self._holes if h[2] > now][-MAX_HOLES:]
        where, params = ['id > :seen'], {'seen': self.seen, 'n': self.batch}
        for i, (lo, hi, _) in enumerate(self._holes):
            where.append(f'id BETWEEN :lo{i} AND :hi{i}')
            params[f'lo{i}'], params[f'hi{i}'] = lo, hi
        return conn.execute(text(
            "SELECT id, room, payload FROM websocket_relay "
            f"WHERE {' OR '.join(where)} ORDER BY id LIMIT :n"), params).fetchall()

    def _take(self, rows):
        now = self._monotonic()
        for row in rows:
            if row.id <= self.seen:
                self._fill_hole(row.id)
            elif row.id > self.seen + 1 and not self._gap_passed(row.id, now):
                return  # later rows wait too: one emitter's order is kept
            else:
                self.seen = row.id
            # The cursor moved first: a row is delivered at most once by this worker
            self._deliver(row)

    def _gap_passed(self, next_id, now):
        first_missing = self.seen + 1
        if self._gap is None or self._gap[0] != first_missing:
            self._gap = (first_missing, now)
        if now - self._gap[1] < self.gap_grace:
            return False
        self._holes.append([first_missing, next_id - 1, now + HOLE_TTL_SECONDS])
        self._gap = None
        return True

    def _fill_hole(self, row_id):
        for hole in self._holes:
            if hole[0] <= row_id <= hole[1]:
                self._holes.remove(hole)
                if hole[0] < row_id:
                    self._holes.append([hole[0], row_id - 1, hole[2]])
                if row_id < hole[1]:
                    self._holes.append([row_id + 1, hole[1], hole[2]])
                return

    def _deliver(self, row):
        try:
            payload = json.loads(row.payload)
            if not isinstance(payload, dict) or not isinstance(row.room, str):
                raise ValueError('not an event')
            origin = payload.pop(ORIGIN_KEY, None)
            if self.skip_origin is not None and origin == self.skip_origin:
                return
            self.deliver(row.room, payload)
        except Exception as e:
            logger.warning(f"Relayed WebSocket event {row.id} not emitted: {type(e).__name__}: {e}")


class PgWakeup:
    """LISTEN on a connection of its own, outside the pool, reopened when it drops."""

    def __init__(self, url):
        from services.scheduler_leader import _dedicated_engine
        self.engine = _dedicated_engine(url)
        self._raw = None
        self.backend_pid = None
        self.schema = None
        self._error_logged = False
        self._loss_logged = False

    def _listen(self):
        raw = self.engine.raw_connection()
        try:
            conn = raw.driver_connection
            conn.autocommit = True
            conn.execute(f"LISTEN {CHANNEL}")
            self.schema = conn.execute("SELECT current_schema()").fetchone()[0]
            self.backend_pid = conn.info.backend_pid
        except BaseException:
            raw.close()
            raise
        self._raw = raw

    def wait(self, timeout, stop):
        """Return on a notification, after ``timeout`` or at once after a reconnection."""
        if self._raw is None:
            try:
                self._listen()
            except Exception as e:
                if not self._error_logged:
                    logger.warning(f"WebSocket relay: no LISTEN connection, reading every "
                                   f"{timeout:g} s: {type(e).__name__}")
                    self._error_logged = True
                stop.wait(timeout)
                return
            self._error_logged = False
            return  # notifications sent while it was down are lost: read now
        deadline = time.monotonic() + timeout
        try:
            # In slices: a stop is noticed within one, not after a whole tick
            while not stop.is_set() and (left := deadline - time.monotonic()) > 0:
                for notify in self._raw.driver_connection.notifies(timeout=min(left, STOP_SLICE_SECONDS)):
                    if notify.payload == self.schema:
                        self._loss_logged = False
                        return
        except Exception as e:
            # A connection dropped right after each LISTEN reconnects twice a second, logged once
            if not self._loss_logged:
                logger.warning(f"WebSocket relay: LISTEN connection lost, reopened: {type(e).__name__}")
                self._loss_logged = True
            self.close()
            stop.wait(min(timeout, STOP_SLICE_SECONDS))
            return
        self._loss_logged = False

    def close(self):
        raw, self._raw = self._raw, None
        self.backend_pid = None
        if raw is not None:
            try:
                raw.close()
            except Exception:  # noqa: BLE001  # already broken: nothing left to release
                pass


def _engine(app):
    from models import db
    with app.app_context():
        return db.engine


def _emit_local(room, payload):
    from websocket.events import socketio
    socketio.emit('event', payload, to=room)


_publisher = None
_reader = None


def start_publisher(app, *, emit_here=False):
    """Its events go through the table, unless a message queue carries them.

    ``emit_here``: a web worker, whose clients get its events at once and not from the table.
    """
    global _publisher
    from websocket import events
    if events.message_queue_in_use():
        return None
    if _publisher is None:
        origin = secrets.token_hex(8) if emit_here else None
        _publisher = RelayPublisher(_engine(app), origin=origin)
        events.relay_through(_publisher, emit_here=emit_here)
    return _publisher


def stop_publisher(timeout=5.0):
    """Never raises; the process emits directly again afterwards."""
    global _publisher
    publisher, _publisher = _publisher, None
    if publisher is None:
        return
    from websocket import events
    events.relay_through(None)
    try:
        publisher.stop(timeout)
    except Exception as e:
        logger.error(f"WebSocket relay writer not stopped cleanly: {type(e).__name__}")


def start_reader(app):
    """Web worker: emits the relayed events to its clients, unless a message queue does.

    In HA it also publishes its own events, for the other workers and nodes.
    """
    global _reader
    from utils.ha import ha_enabled
    from websocket import events
    if events.message_queue_in_use():
        return None
    if _reader is None:
        engine = _engine(app)
        skip_origin = start_publisher(app, emit_here=True).origin if ha_enabled() else None
        wakeup = PgWakeup(engine.url) if engine.dialect.name == 'postgresql' else None
        _reader = RelayReader(engine, _emit_local, skip_origin=skip_origin, wakeup=wakeup).start()
    return _reader


def stop_reader():
    global _reader
    reader, _reader = _reader, None
    if reader is not None:
        reader.stop()
    stop_publisher()
