#!/usr/bin/env python3
"""
UCM Database Bootstrap & Migration Runner
==========================================

Backend-agnostic. Supports SQLite and PostgreSQL.

Bootstrap states
----------------
- FRESH:      No business tables (``users``, ``certificate_authorities``) and no
              migration recorded.
              -> Schema is built by SQLAlchemy `db.create_all()`.
              -> Every current migration is then marked as applied.
- TRACKED:    `_migrations` table exists.
              -> Pending migrations are applied, once the pivot check passes.
- LEGACY:     Business tables exist but no `_migrations`: refused.

Pivot (3.0)
-----------
3.0 starts from UCM 2.254. A database that is not fresh starts only when its
registry holds ``300_upgrade_from_2_254`` (a 3.0 database) or every name 2.254
records (``migrations/_from_2_254.PIVOT_NAMES``), and no name that neither 2.254
nor this release knows. Any other database is refused before anything is written,
with what to do.

Migrations
----------
Numbered from 300. Every migration is multi-backend:

  * Set ``pg_compatible = True`` at module scope.
  * Expose ``upgrade(arg)`` that accepts EITHER ``sqlite3.Connection``
    (SQLite path) OR a SQLAlchemy connection (PostgreSQL path).
  * Use ``isinstance(arg, sqlite3.Connection)`` to dispatch.

Files and packages whose name starts with ``_`` are not migrations.

A migration only adds to what the release before it reads or writes (CONTRIBUTING.md,
"Migrations and rolling updates"). One that removes or narrows sets ``requires_full_stop = "<why>"``
(``migration_marks``): in HA the runner refuses to apply it while another node beats fresh on
another version, and a rolling update refuses the release before installing anything.

Public API
----------
- `run_all_migrations(dry_run=False, verbose=False)`
- `build_fresh_schema(create_all)` -> fresh installs: registry, then tables
- `mark_all_applied()`
- `show_status()`       -> CLI helper
"""
import os
import sys
import sqlite3
import time
import importlib.util
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, event, text, inspect

from migration_marks import full_stop_reason
from utils.db_url import is_postgres_url, postgres_connect_args, postgres_engine_options, sqlalchemy_url


def say(*args, **kwargs):
    """say() that reaches the journal now, not when the process ends.

    An unflushed stream leaves journald holding the lines of a long upgrade
    until the process ends: the upgrade ran, its report came at shutdown.
    """
    kwargs.setdefault('flush', True)
    print(*args, **kwargs)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


# ---------------------------------------------------------------------------
# Connection helpers
# ---------------------------------------------------------------------------

def _get_db_url() -> str:
    """Resolve the active database URL (env-driven)."""
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        return db_url
    db_path = os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db")
    return f"sqlite:///{db_path}"


def _is_postgres(db_url: str) -> bool:
    return is_postgres_url(db_url)


# Server side, per session: a dead peer is dropped within about a minute, and a statement whose
# client is gone (a killed start) stops within 10 s with its locks, not at its own end
_SESSION_KEEPALIVES = ("SELECT set_config('tcp_keepalives_idle', '30', false), "
                       "set_config('tcp_keepalives_interval', '10', false), "
                       "set_config('tcp_keepalives_count', '3', false)")
_SESSION_CLIENT_CHECK = "SELECT set_config('client_connection_check_interval', '10s', false)"


def _session_limits(dbapi_connection, _record):
    for statement in (_SESSION_KEEPALIVES, _SESSION_CLIENT_CHECK):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute(statement)
            dbapi_connection.commit()
        except Exception:  # noqa: BLE001 - PostgreSQL before 14, or a platform without the check
            dbapi_connection.rollback()
        finally:
            cursor.close()


def _engine(db_url):
    """The runner's engine: on PostgreSQL the application pool's options and the limits above."""
    engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True, **postgres_engine_options(db_url))
    if is_postgres_url(db_url):
        event.listen(engine, "connect", _session_limits)
    return engine


def _list_migration_names() -> list[str]:
    if not MIGRATIONS_DIR.exists():
        return []
    return [
        f.stem for f in sorted(MIGRATIONS_DIR.glob("*.py"))
        if not f.name.startswith("_") and not f.is_dir()
    ]


# ---------------------------------------------------------------------------
# State detection
# ---------------------------------------------------------------------------

def _get_state(engine):
    """Return (state, applied_set).

    state in {'fresh', 'legacy', 'tracked'}.
    """
    insp = inspect(engine)
    try:
        tables = set(insp.get_table_names())
    except Exception:
        # Database doesn't exist yet (SQLite file not created)
        return ("fresh", set())

    has_meta = "_migrations" in tables
    has_data = "users" in tables or "certificate_authorities" in tables

    if has_meta:
        with engine.connect() as conn:
            rows = conn.execute(text("SELECT name FROM _migrations")).fetchall()
        if rows or has_data:
            return ("tracked", {r[0] for r in rows})
    if has_data:
        return ("legacy", set())
    return ("fresh", set())


# ---------------------------------------------------------------------------
# Pivot: 3.0 upgrades a database last started by 2.254, nothing older
# ---------------------------------------------------------------------------

UPGRADE_MIGRATION = "300_upgrade_from_2_254"
PIVOT_VERSION = "2.254"


def unknown_migrations(applied):
    """Registry names neither 2.254 (2.254.N adds none) nor this release knows: a later release
    or a hand edit wrote them."""
    from migrations._from_2_254 import PIVOT_NAMES, RECORDED_BEFORE_2_52
    return sorted(set(applied) - PIVOT_NAMES - RECORDED_BEFORE_2_52 - set(_list_migration_names()))


def pivot_refusal(state, applied):
    """None when this database may be migrated, else the message that refuses it."""
    from migrations._from_2_254 import PIVOT_NAMES
    if state == "fresh":
        return None
    unknown = unknown_migrations(applied)
    if unknown:
        return (f"This database names {len(unknown)} migration(s) this release does not know, first "
                f"{', '.join(unknown[:3])}: a later release started it, or its registry was edited. "
                f"Start it with the release that recorded them. Nothing was changed.")
    if UPGRADE_MIGRATION in applied:
        return None
    missing = sorted(PIVOT_NAMES - set(applied))
    if not missing:
        return None
    what = ("it has no migration registry" if state == "legacy"
            else f"{len(missing)} migration(s) of {PIVOT_VERSION} are missing from its registry, "
                 f"first {', '.join(missing[:3])}")
    return (f"This database was last started by a release older than {PIVOT_VERSION} ({what}). "
            f"Install {PIVOT_VERSION}, start it once, then upgrade. Nothing was changed: "
            f"{PIVOT_VERSION} still starts on this database.")


# The Docker image moves to a new major only when the operator names it: pulling `latest` is not
# consent. UCM_DOCKER=1 is set by the Dockerfile alone (Kubernetes included); a package installed
# in a container has /.dockerenv but not this variable, and installing a package is consent.
MAJOR = "3"
ACCEPT_MAJOR_VARIABLE = "UCM_ACCEPT_MAJOR_UPGRADE"
MAJOR_UPGRADE_REFUSAL = (
    f"This database was last started by UCM {PIVOT_VERSION} and this image is UCM {MAJOR}: starting it "
    f"would upgrade the database to the new major version, which {PIVOT_VERSION} cannot start "
    f"afterwards. Nothing was changed.\n"
    f"To upgrade: back up the data volume (and the PostgreSQL database if you use one), then set "
    f"{ACCEPT_MAJOR_VARIABLE}={MAJOR} and start again. See UPGRADE.md, Upgrading to v3.0.\n"
    f"To stay on 2.x: pin the image tag '2' (or an exact version, 2.254.N) instead of 'latest'.")


def major_upgrade_refusal(state, applied, engine):
    """In the image, a database the pivot accepts and 300 has not upgraded (2.254 started it last)
    waits for UCM_ACCEPT_MAJOR_UPGRADE to be exactly the major of this release. The marker of an
    upgrade already begun (SQLite) is that consent: it was given for this database, which 2.254
    must not start again."""
    if os.environ.get("UCM_DOCKER") != "1" or state == "fresh" or UPGRADE_MIGRATION in applied:
        return None
    if os.environ.get(ACCEPT_MAJOR_VARIABLE) == MAJOR:
        return None
    from pre_upgrade_copy import MARKER_TABLE
    if MARKER_TABLE in inspect(engine).get_table_names():
        return None
    return MAJOR_UPGRADE_REFUSAL


# ---------------------------------------------------------------------------
# Full stop: a marked migration waits until no node of another version beats
# ---------------------------------------------------------------------------

def _instant(value):
    from datetime import datetime
    return datetime.fromisoformat(value) if isinstance(value, str) else value


FULL_STOP_POLL_SECONDS = 5
FULL_STOP_LOG_SECONDS = 15
# Past the stale window: the last beat of a killed node has aged out by then
FULL_STOP_MARGIN_SECONDS = 15


def _stale_seconds():
    from services.scheduler_leader import STALE_PASSES
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    return STALE_PASSES * WAKE_INTERVAL_SECONDS


def _full_stop_hold(engine, pending):
    """({marked migration: reason}, ["node (version)"...]): HA, the marked migrations among
    *pending*, and the other nodes beating fresh on another version that hold them."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        return {}, []
    marked = {n: r for n in pending if (r := full_stop_reason(MIGRATIONS_DIR / f"{n}.py"))}
    if not marked or "cluster_nodes" not in inspect(engine).get_table_names():
        return marked, []
    from config.settings import Config
    from services.scheduler_leader import cluster_utc_now
    from services.updates import versions_match
    own, stale = Config.APP_VERSION, _stale_seconds()
    with engine.connect() as conn:
        now = cluster_utc_now(conn)
        rows = conn.execute(text("SELECT node_id, version, heartbeat_at, pid FROM cluster_nodes")).fetchall()
    # This node's own row still holds the version it ran before this start; pid NULL: stopped cleanly
    others = sorted(f"{node} ({version or 'unknown version'})" for node, version, beat, pid in rows
                    if node != Config.NODE_ID and beat is not None and pid is not None
                    and (now - _instant(beat)).total_seconds() <= stale
                    and not (versions_match(version, own) or versions_match(own, version)))
    return marked, others


def full_stop_refusal(engine, pending):
    """None, or why this node may not apply *pending* now: HA, a pending migration marked
    requires_full_stop, and another node with a fresh heartbeat on another version."""
    from config.settings import Config
    marked, others = _full_stop_hold(engine, pending)
    if not others:
        return None
    first = sorted(marked)[0]
    more = f" (and {len(marked) - 1} more)" if len(marked) > 1 else ""
    return (f"Migration {first}{more} requires every node stopped: {marked[first]}. "
            f"Still running with a fresh heartbeat: {', '.join(others)}. Stop every node, then "
            f"start them on {Config.APP_VERSION}; a node stopped cleanly counts as gone at once, "
            f"one that was killed {_stale_seconds()}s after its last heartbeat. Nothing was changed.")


def _full_stop_holders_now():
    """The nodes holding a pending marked migration now, on a connection closed on return;
    [] when anything else is in the way (run_all_migrations then says what)."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        return []
    db_url = _get_db_url()
    try:
        engine = _engine(db_url)
    except Exception:
        return []
    try:
        state, applied = _get_state(engine)
        if state != "tracked" or pivot_refusal(state, applied):
            return []
        return _full_stop_hold(engine, [n for n in _list_migration_names() if n not in applied])[1]
    except Exception:
        return []
    finally:
        engine.dispose()


def wait_for_full_stop(clock=None, sleep=None):
    """Before the startup lock: while other nodes hold a pending marked migration, wait at most
    the stale window plus a margin (a killed node ages out), logging them every 15s, holding no
    connection between polls. Returns the nodes still holding it, [] to go on."""
    import time
    clock, sleep = clock or time.monotonic, sleep or time.sleep
    start = clock()
    deadline, next_log = start + _stale_seconds() + FULL_STOP_MARGIN_SECONDS, start
    while True:
        holders = _full_stop_holders_now()
        now = clock()
        if not holders or now >= deadline:
            return holders
        if now >= next_log:
            say(f"Waiting for {', '.join(holders)} to stop before a migration that requires every "
                f"node stopped: at most {deadline - now:.0f}s more")
            next_log = now + FULL_STOP_LOG_SECONDS
        sleep(min(FULL_STOP_POLL_SECONDS, deadline - now))


def run_at_startup(lock, clock=None, sleep=None) -> bool:
    """create_app: the full-stop wait outside the startup lock, then the migrations under it."""
    wait_for_full_stop(clock=clock, sleep=sleep)
    with lock(_get_db_url()):
        return run_all_migrations(dry_run=False, verbose=False)


def mark_node_stopped(node_id=None) -> None:
    """HA, gunicorn master on exit, once its workers and scheduler process are gone: the node's
    row keeps its last heartbeat with pid NULL, which _full_stop_hold reads as stopped."""
    from utils.ha import ha_enabled
    if not ha_enabled():
        return
    from config.settings import Config
    db_url = _get_db_url()
    try:
        engine = _engine(db_url)
        try:
            with engine.begin() as conn:
                conn.execute(text("UPDATE cluster_nodes SET pid = NULL WHERE node_id = :n"),
                             {"n": node_id or Config.NODE_ID})
        finally:
            engine.dispose()
    except Exception as exc:
        say(f"Node not marked stopped in cluster_nodes ({type(exc).__name__}): a node that "
            f"starts a full-stop migration waits up to {_stale_seconds()}s for this one")


# ---------------------------------------------------------------------------
# Tracking table management
# ---------------------------------------------------------------------------

_DDL_PG = """
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')
)
"""

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


# `_migrations.applied_at` is naive UTC on both backends, so a copy between them keeps its meaning.
_PG_NOW_UTC = "(CURRENT_TIMESTAMP AT TIME ZONE 'UTC')"


def _ensure_tracking_table(engine, is_pg: bool):
    with engine.begin() as conn:
        conn.execute(text(_DDL_PG if is_pg else _DDL_SQLITE))


def _mark_applied(engine, names, is_pg: bool):
    if not names:
        return
    sql = (
        f"INSERT INTO _migrations (name, applied_at) VALUES (:n, {_PG_NOW_UTC}) ON CONFLICT (name) DO NOTHING"
        if is_pg
        else "INSERT OR IGNORE INTO _migrations (name) VALUES (:n)"
    )
    with engine.begin() as conn:
        for n in names:
            conn.execute(text(sql), {"n": n})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def mark_all_applied():
    """Mark every current migration file as applied without running them.

    A fresh install calls it through build_fresh_schema, before create_all, so that
    future migrations (added later) are the only ones that run.
    """
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    engine = _engine(db_url)
    try:
        record_fresh_registry(engine, is_pg)
    finally:
        engine.dispose()


def record_fresh_registry(engine, is_pg: bool):
    """The registry of a fresh 3.0 database on *engine*: every current migration, applied."""
    _ensure_tracking_table(engine, is_pg)
    _mark_applied(engine, _list_migration_names(), is_pg)


def build_fresh_schema(create_all):
    """A fresh install records its registry first, then builds its tables: a start cut short in
    between finds a 3.0 database whose tables create_all completes, never one older than 2.254."""
    mark_all_applied()
    create_all()


def _server_encoding(engine) -> str:
    """server_encoding read on a bare driver connection: SQLAlchemy's first connect reads the
    server version with a text pattern, which a SQL_ASCII database answers in bytes (TypeError)."""
    cargs, cparams = engine.dialect.create_connect_args(engine.url)
    # An unreachable server is given up in 10 s, as elsewhere, unless the URL sets its own
    cparams.setdefault("connect_timeout", 10)
    conn = engine.dialect.dbapi.connect(*cargs, **cparams)
    try:
        with conn.cursor() as cursor:
            cursor.execute("SHOW server_encoding")
            value = cursor.fetchone()[0]
    finally:
        conn.close()
    return value.decode("ascii", "replace") if isinstance(value, bytes) else str(value)


def encoding_refusal(engine):
    """None on SQLite or a UTF8 PostgreSQL database, else the message that refuses it."""
    if engine.dialect.name != "postgresql":
        return None
    encoding = _server_encoding(engine)
    if encoding.upper() in ("UTF8", "UTF-8"):
        return None
    return (f"This PostgreSQL database uses the encoding {encoding}; UCM needs UTF8. Create a "
            f"database with ENCODING 'UTF8' (docs/ADMIN_GUIDE.md, PostgreSQL Backend) and point "
            f"DATABASE_URL at it. Nothing was changed.")


def startup_encoding_refusal():
    """encoding_refusal of the configured database, before any SQLAlchemy connection; None
    when the server cannot be asked (the steps after it fail on that as they would)."""
    db_url = _get_db_url()
    if not _is_postgres(db_url):
        return None
    try:
        engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True,
                               connect_args=postgres_connect_args(db_url))
    except Exception:  # noqa: BLE001
        return None
    try:
        return encoding_refusal(engine)
    except Exception:  # noqa: BLE001
        return None
    finally:
        engine.dispose()


def _pending(applied):
    return [n for n in _list_migration_names() if n not in applied]


def pending_migrations(engine) -> list[str]:
    """What this release applies at its next start to the database of *engine*: none for a
    fresh one (built whole) or one it refuses."""
    state, applied = _get_state(engine)
    if state == "fresh" or pivot_refusal(state, applied):
        return []
    return _pending(applied)
def start_schema(engine, metadata, create_all) -> bool:
    """The schema step of a start, after the migrations: a database without its core tables is
    built fresh (True); any other is a 3.0 one, where create_all and the index pass add only
    what a cut fresh install left out."""
    from sqlalchemy import inspect as _inspect
    tables = set(_inspect(engine).get_table_names())
    fresh = not {'users', 'certificate_authorities'} <= tables
    if fresh:
        build_fresh_schema(create_all)
    else:
        create_all()
    create_missing_indexes(engine, metadata)
    return fresh


def create_missing_indexes(engine, metadata):
    """create_all skips a table that exists, with its indexes: one a cut start left out (SQLite
    commits each statement) is created here. Any 3.0 database already holds the model's indexes."""
    from sqlalchemy import inspect as _inspect
    from utils.serial_duplicates import INDEX as serial_index
    insp = _inspect(engine)
    tables = set(insp.get_table_names())
    # Two certificates of one CA under one serial: the unique index waits for step 144
    waiting = {serial_index} if _serial_steps_pending(engine) else set()
    for table in metadata.sorted_tables:
        if table.name not in tables:
            continue
        present = {i['name'] for i in insp.get_indexes(table.name)}
        for index in table.indexes:
            if index.name not in present and index.name not in waiting:
                say(f"✓ Creating index {index.name} missing from {table.name}")
                index.create(engine)


def run_all_migrations(dry_run: bool = False, verbose: bool = False) -> bool:
    """Apply pending migrations to the configured database.

    Returns True on success, False on failure. A no-op (FRESH state)
    counts as success — caller is responsible for build_fresh_schema().
    """
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    backend = "PostgreSQL" if is_pg else "SQLite"

    try:
        engine = _engine(db_url)
    except Exception as exc:
        say(f"✗ Could not connect to database ({backend}): {exc}")
        return False

    try:
        # Before the first SQLAlchemy connection, which fails on it without naming it
        refusal = encoding_refusal(engine)
        if refusal:
            say(f"✗ {refusal}")
            return False
        state, applied = _get_state(engine)

        if state == "fresh":
            say(
                f"✓ Fresh {backend} database: schema will be built by "
                f"SQLAlchemy create_all()"
            )
            return True

        # Checked before any write, the creation of `_migrations` included; an older database
        # keeps its own refusal first
        refusal = pivot_refusal(state, applied) or major_upgrade_refusal(state, applied, engine)
        if refusal:
            say(f"✗ {refusal}")
            return False

        pending = _pending(applied)
        try:
            refusal = full_stop_refusal(engine, pending)
        except ValueError as exc:
            refusal = str(exc)
        if refusal:
            say(f"✗ {refusal}")
            return False
        serial_replay = UPGRADE_MIGRATION in applied and _serial_steps_pending(engine)
        # Pass the SQLite path derived from db_url so DATABASE_URL stays the
        # single source of truth (avoids DATABASE_URL/DATABASE_PATH mismatch).
        sqlite_path = db_url.replace("sqlite:///", "", 1) if db_url.startswith("sqlite:///") else None

        if not pending and not serial_replay:
            say(f"✓ {backend} database up to date (no pending migrations)")
            return True

        if pending:
            say(f"Found {len(pending)} pending migration(s) for {backend}:")
            if UPGRADE_MIGRATION in pending:
                refusal = upgrade_refusal(engine)
                if refusal:
                    say(f"✗ {refusal}")
                    return False
                if not _copy_before_upgrade(is_pg, sqlite_path, dry_run):
                    return False
            done = (_run_pending_pg(engine, pending, dry_run) if is_pg
                    else _run_pending_sqlite(pending, dry_run, db_path=sqlite_path))
            if not done:
                return False
        if serial_replay and dry_run:
            say(f"  → {SERIAL_REPLAY_NOTE} (dry run)")
            return True
        return _replay_serial_steps(engine, is_pg, sqlite_path) if serial_replay else True
    finally:
        engine.dispose()


def upgrade_refusal(engine):
    """What migration 300 refuses in the 2.254 data, read before the copy and its marker are
    written, so a refused database is left exactly as 2.254 left it."""
    check = getattr(_load_module(MIGRATIONS_DIR / f"{UPGRADE_MIGRATION}.py"), "refusal", None)
    if check is None:
        return None
    with engine.connect() as conn:
        return check(conn)


def _sqlite_file(sqlite_path):
    return sqlite_path or os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db")


def _copy_before_upgrade(is_pg: bool, sqlite_path, dry_run: bool) -> bool:
    """SQLite: migration 300 starts once a verified copy exists and the marker is set, or the
    marker shows an earlier start began it (pre_upgrade_copy.prepare)."""
    import pre_upgrade_copy
    if is_pg:
        say(f"  ! {pre_upgrade_copy.PG_NOTE}")
        return True
    if dry_run:
        say(f"  → {pre_upgrade_copy.plan(_sqlite_file(sqlite_path))} (dry run)")
        return True
    try:
        say(f"  {pre_upgrade_copy.prepare(_sqlite_file(sqlite_path))}")
    except pre_upgrade_copy.CopyFailed as exc:
        say(f"  ✗ {exc}")
        return False
    return True


# ---------------------------------------------------------------------------
# Serial steps: run again at each start while they leave the unique index pending
# ---------------------------------------------------------------------------

# Step 144 alone: it converts, creates the index and resets the key in one commit, so a
# replay cut short keeps the key that triggers the next one (142 commits its deletion apart)
SERIAL_STEP = "144_canonical_certificate_serials"
SERIAL_REPLAY_NOTE = "serial_unique_index_pending is set: upgrade step 144 runs again at each start until it clears"


def _serial_steps_pending(engine) -> bool:
    from utils.serial_duplicates import PENDING_KEY
    if "system_config" not in inspect(engine).get_table_names():
        return False
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1 FROM system_config WHERE key = :k"),
                            {"k": PENDING_KEY}).first() is not None


def _replay_serial_steps(engine, is_pg: bool, sqlite_path) -> bool:
    """Step 144 alone, idempotent; the 300 row and its date stay as they are."""
    from migrations._from_2_254 import step
    say(f"  → serial_unique_index_pending is set: upgrade step {SERIAL_STEP} runs again: started")
    started = time.monotonic()
    try:
        if is_pg:
            with engine.begin() as conn:
                step(SERIAL_STEP).upgrade(conn)
        else:
            conn = sqlite3.connect(sqlite_path or os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db"))
            try:
                step(SERIAL_STEP).upgrade(conn)
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        say(f"  ✗ {SERIAL_STEP}: failed after {time.monotonic() - started:.1f} s: {exc}")
        return False
    say(f"  ✓ {SERIAL_STEP}: done in {time.monotonic() - started:.1f} s")
    return True


# ---------------------------------------------------------------------------
# SQLite execution path
# ---------------------------------------------------------------------------

def _run_pending_sqlite(pending, dry_run, db_path: str = None) -> bool:
    if not db_path:
        db_path = os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db")
    if not os.path.exists(db_path):
        say(f"✗ SQLite file not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_DDL_SQLITE)
        conn.commit()
        for name in pending:
            path = MIGRATIONS_DIR / f"{name}.py"
            if not _run_one_sqlite(conn, path, db_path, dry_run):
                say("✗ Migration failed, stopping")
                return False
        say("✓ All migrations applied")
        return True
    finally:
        conn.close()


def _load_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_one_sqlite(conn, path: Path, db_path: str, dry_run: bool) -> bool:
    name = path.stem
    if dry_run:
        say(f"  → {name}: (dry run)")
        return True
    say(f"  → {name}: started")
    started = time.monotonic()
    try:
        mod = _load_module(path)
        if hasattr(mod, "upgrade"):
            import inspect as _ins
            sig = _ins.signature(mod.upgrade)
            n = len(sig.parameters)
            if n == 0:
                mod.upgrade()
            elif n == 1:
                # All current migrations accept a sqlite3.Connection (or a
                # SQLAlchemy Engine on the PG path). Always pass the connection
                # — never inspect the parameter name; that heuristic silently
                # passed the db_path string when a migration called its
                # parameter anything other than "conn", which broke 020.
                mod.upgrade(conn)
            else:
                mod.upgrade(conn)
        else:
            say(f"  ✗ {name}: no upgrade(), skipped")
            return False
        if name == UPGRADE_MIGRATION:
            import pre_upgrade_copy
            pre_upgrade_copy.clear_started(conn)
        conn.execute("INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        say(f"  ✓ {name}: done in {time.monotonic() - started:.1f} s")
        return True
    except Exception as e:  # noqa: BLE001
        # A failed migration is never recorded: its steps are idempotent, the next start runs it again
        conn.rollback()
        say(f"  ✗ {name}: failed after {time.monotonic() - started:.1f} s: {e}")
        return False


# ---------------------------------------------------------------------------
# PostgreSQL execution path
# ---------------------------------------------------------------------------

def _migration_index(name: str) -> int:
    """Extract leading numeric index from a migration filename stem.

    Returns -1 if no leading digits — such files are treated as legacy
    (never enforced).
    """
    digits = []
    for ch in name:
        if ch.isdigit():
            digits.append(ch)
        else:
            break
    return int("".join(digits)) if digits else -1


# Migrations at this index or above MUST declare pg_compatible=True: every 3.0 migration (300+).
PG_COMPATIBLE_REQUIRED_FROM = 20


def _run_pending_pg(engine, pending, dry_run) -> bool:
    """Run pending migrations against PostgreSQL, each in one transaction with its registry row.

    Every 3.0 migration declares `pg_compatible = True`; one that does not is a hard error
    (silent-skip was the root cause of issue #115).
    """
    for name in pending:
        path = MIGRATIONS_DIR / f"{name}.py"
        if dry_run:
            say(f"  → {name}: (dry run)")
            continue
        say(f"  → {name}: started")
        started = time.monotonic()
        try:
            mod = _load_module(path)
            is_pg_compatible = getattr(mod, "pg_compatible", False)
            idx = _migration_index(name)

            if not is_pg_compatible and idx >= PG_COMPATIBLE_REQUIRED_FROM:
                # Hard fail — refuse to silently skip a "new-era" migration.
                say(f"  ✗ {name}: refused")
                say(
                    f"    Migration {name} is numbered >= {PG_COMPATIBLE_REQUIRED_FROM:03d} "
                    f"but does not declare `pg_compatible = True`. "
                    f"Silent-skip would corrupt the PostgreSQL schema (issue #115). "
                    f"Refusing to continue."
                )
                return False

            with engine.begin() as conn:
                if is_pg_compatible and hasattr(mod, "upgrade"):
                    mod.upgrade(conn)
                else:
                    say(f"    {name}: SQLite-only, skipped")
                conn.execute(
                    text(
                        f"INSERT INTO _migrations (name, applied_at) VALUES (:n, {_PG_NOW_UTC}) "
                        "ON CONFLICT (name) DO NOTHING"
                    ),
                    {"n": name},
                )
            # After the commit: on PostgreSQL the step and its registry row land together
            say(f"  ✓ {name}: done in {time.monotonic() - started:.1f} s")
        except Exception as e:  # noqa: BLE001
            say(f"  ✗ {name}: failed after {time.monotonic() - started:.1f} s: {e}")
            return False
    say("✓ All migrations applied")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def show_status():
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    say("=== Migration Status ===")
    say(f"Backend: {'PostgreSQL' if is_pg else 'SQLite'}")
    say(f"URL:     {db_url.split('@')[-1] if '@' in db_url else db_url}")
    try:
        engine = _engine(db_url)
    except Exception as e:
        say(f"✗ Cannot connect: {e}")
        return
    try:
        refusal = encoding_refusal(engine)
        if refusal:
            say(f"Refused: {refusal}")
            return
        state, applied = _get_state(engine)
        say(f"State:   {state}")
        refusal = pivot_refusal(state, applied)
        if refusal:
            say(f"Refused: {refusal}")
        all_names = _list_migration_names()
        pending = [n for n in all_names if n not in applied]
        if not refusal:
            try:
                held = full_stop_refusal(engine, pending)
            except ValueError as exc:
                held = str(exc)
            if held:
                say(f"Refused: {held}")
        say(f"Applied: {len(applied)}")
        say(f"Pending: {len(pending)}")
        for n in sorted(applied):
            say(f"  ✓ {n}")
        for n in pending:
            say(f"  ○ {n}")
        if not refusal and UPGRADE_MIGRATION in pending:
            import pre_upgrade_copy
            sqlite_path = db_url.replace("sqlite:///", "", 1) if db_url.startswith("sqlite:///") else None
            say(f"Copy:    {pre_upgrade_copy.PG_NOTE if is_pg else pre_upgrade_copy.plan(_sqlite_file(sqlite_path))}")
        if not refusal and UPGRADE_MIGRATION in applied and _serial_steps_pending(engine):
            say(f"Replay:  {SERIAL_REPLAY_NOTE}")
    finally:
        engine.dispose()


# Exit codes of `check`; any other code (a crash) means the answer is unknown. REFUSED is a
# database older than 2.254, UNKNOWN one whose registry names migrations this release lacks,
# MAJOR_UPGRADE (with --major-upgrade only, the image's entrypoint) major_upgrade_refusal.
CHECK_STARTABLE, CHECK_FRESH, CHECK_REFUSED, CHECK_UNREADABLE, CHECK_UNKNOWN = 0, 3, 4, 5, 6
CHECK_MAJOR_UPGRADE = 7


def _journal_holds_data(path: str) -> bool:
    """A non-empty -wal or -journal: SQLite would replay it into the read (a hot journal is
    rolled back before any read), which a read-only open of the file cannot do unwritten."""
    return any(os.path.isfile(path + suffix) and os.path.getsize(path + suffix) > 0
               for suffix in ("-wal", "-journal"))


@contextmanager
def _probe_engine(db_url: str):
    """An engine on *db_url* that writes nothing there. A SQLite file whose journal is absent
    or empty is opened in place with immutable=1 (no lock, no -wal or -shm created, as a WAL
    database opened otherwise would); one whose journal holds data is read from a private
    copy, with that journal."""
    if db_url.startswith("sqlite:///"):
        path = db_url[len("sqlite:///"):]
        if not _journal_holds_data(path):
            import sqlite3
            from urllib.parse import quote
            # The URI goes to sqlite3 as written: a URL parser would decode it again (#, ?, %)
            uri = f"file:{quote(os.path.abspath(path))}?immutable=1"
            engine = create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True))
            try:
                yield engine
            finally:
                engine.dispose()
            return
        import shutil
        import tempfile
        with tempfile.TemporaryDirectory(prefix="ucm-check-") as tmp:
            copy = os.path.join(tmp, "probe.db")
            shutil.copyfile(path, copy)
            for suffix in ("-wal", "-journal"):
                if os.path.isfile(path + suffix):
                    shutil.copyfile(path + suffix, copy + suffix)
            engine = create_engine(f"sqlite:///{copy}")
            try:
                yield engine
            finally:
                engine.dispose()
        return
    args = dict(postgres_connect_args(db_url))
    if _is_postgres(db_url) and "connect_timeout" not in db_url:
        args["connect_timeout"] = 10
    engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True, connect_args=args)
    try:
        yield engine
    finally:
        engine.dispose()


def check_database(major_upgrade: bool = False) -> int:
    """For the package scripts and the image: whether this release starts on the configured database.

    Prints the backend first ("sqlite <path>", "postgresql", or "other" for any other URL),
    then the reason of a refusal or of an unreadable database, and returns one of the
    CHECK_* codes: a missing or empty SQLite file is fresh, a registry naming unknown
    migrations is UNKNOWN even when 2.254 migrations are missing too. *major_upgrade* (the
    image) also answers MAJOR_UPGRADE for a database major_upgrade_refusal refuses.
    """
    db_url = _get_db_url()
    sqlite_path = db_url[len("sqlite:///"):] if db_url.startswith("sqlite:///") else None
    say(f"sqlite {sqlite_path}" if sqlite_path else
        "postgresql" if _is_postgres(db_url) else "other")
    if sqlite_path is not None and not os.path.lexists(sqlite_path):
        return CHECK_FRESH
    try:
        with _probe_engine(db_url) as engine:
            refusal = encoding_refusal(engine)
            if refusal:
                say(f"unreadable: {refusal}")
                return CHECK_UNREADABLE
            # _get_state takes a table listing that fails for an empty file: read it here first
            with engine.connect() as conn:
                if sqlite_path is not None:
                    conn.execute(text("SELECT name FROM sqlite_master LIMIT 1")).fetchall()
            state, applied = _get_state(engine)
            refusal = pivot_refusal(state, applied)
            major = (major_upgrade_refusal(state, applied, engine)
                     if major_upgrade and not refusal else None)
    except Exception as exc:  # noqa: BLE001
        cause = getattr(exc, "orig", None) or exc
        # Never the URL: only the driver's first line, which names no password
        say(f"unreadable: {type(cause).__name__}: {str(cause).splitlines()[0] if str(cause) else ''}")
        return CHECK_UNREADABLE
    if refusal:
        say(refusal)
        return CHECK_UNKNOWN if unknown_migrations(applied) else CHECK_REFUSED
    refusal = major
    if refusal:
        say(refusal)
        return CHECK_MAJOR_UPGRADE
    return CHECK_FRESH if state == "fresh" else CHECK_STARTABLE


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="UCM Database Migration Runner")
    parser.add_argument(
        "command",
        choices=["run", "status", "dry-run", "mark-applied", "check"],
        nargs="?",
        default="status",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--major-upgrade", action="store_true",
                        help="check: also refuse an unaccepted upgrade from 2.254 (image only)")
    args = parser.parse_args()

    if args.command == "status":
        show_status()
    elif args.command == "check":
        sys.exit(check_database(major_upgrade=args.major_upgrade))
    elif args.command == "dry-run":
        run_all_migrations(dry_run=True, verbose=args.verbose)
    elif args.command == "run":
        sys.exit(0 if run_all_migrations(verbose=args.verbose) else 1)
    elif args.command == "mark-applied":
        mark_all_applied()
        say("✓ All current migrations marked as applied")
