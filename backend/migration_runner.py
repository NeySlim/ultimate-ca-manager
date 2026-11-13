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
records (``migrations/_from_2_254.PIVOT_NAMES``). Any other database is refused
before anything is written, with what to do.

Migrations
----------
Numbered from 300. Every migration is multi-backend:

  * Set ``pg_compatible = True`` at module scope.
  * Expose ``upgrade(arg)`` that accepts EITHER ``sqlite3.Connection``
    (SQLite path) OR a SQLAlchemy connection (PostgreSQL path).
  * Use ``isinstance(arg, sqlite3.Connection)`` to dispatch.

Files and packages whose name starts with ``_`` are not migrations.

Public API
----------
- `run_all_migrations(dry_run=False, verbose=False)`
- `mark_all_applied()`  -> call after create_all() on fresh installs
- `show_status()`       -> CLI helper
"""
import os
import sys
import sqlite3
import importlib.util
from pathlib import Path

from sqlalchemy import create_engine, text, inspect

from utils.db_url import is_postgres_url, postgres_connect_args, sqlalchemy_url


def say(*args, **kwargs):
    """say() that reaches the journal now, not when the process ends.

    The progress line is written without a newline (``  -> name...`` then
    ``OK``), so an unflushed stream leaves journald holding a partial line:
    the upgrade ran, and its report only appeared at the next shutdown.
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


def pivot_refusal(state, applied):
    """None when this database may be migrated, else the message that refuses it."""
    from migrations._from_2_254 import PIVOT_NAMES
    if state == "fresh" or UPGRADE_MIGRATION in applied:
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

    Call this after `db.create_all()` on a fresh install so that future
    migrations (added later) are the only ones that run.
    """
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True,
                           connect_args=postgres_connect_args(db_url))
    try:
        _ensure_tracking_table(engine, is_pg)
        _mark_applied(engine, _list_migration_names(), is_pg)
    finally:
        engine.dispose()


def run_all_migrations(dry_run: bool = False, verbose: bool = False) -> bool:
    """Apply pending migrations to the configured database.

    Returns True on success, False on failure. A no-op (FRESH state)
    counts as success — caller is responsible for create_all() and
    mark_all_applied().
    """
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    backend = "PostgreSQL" if is_pg else "SQLite"

    try:
        engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True,
                           connect_args=postgres_connect_args(db_url))
    except Exception as exc:
        say(f"✗ Could not connect to database ({backend}): {exc}")
        return False

    try:
        state, applied = _get_state(engine)

        if state == "fresh":
            say(
                f"✓ Fresh {backend} database: schema will be built by "
                f"SQLAlchemy create_all()"
            )
            return True

        # Checked before any write, the creation of `_migrations` included
        refusal = pivot_refusal(state, applied)
        if refusal:
            say(f"✗ {refusal}")
            return False

        all_names = _list_migration_names()
        pending = [n for n in all_names if n not in applied]
        replay = UPGRADE_MIGRATION in applied and not dry_run and _serial_steps_pending(engine)
        # Pass the SQLite path derived from db_url so DATABASE_URL stays the
        # single source of truth (avoids DATABASE_URL/DATABASE_PATH mismatch).
        sqlite_path = db_url.replace("sqlite:///", "", 1) if db_url.startswith("sqlite:///") else None

        if not pending and not replay:
            say(f"✓ {backend} database up to date (no pending migrations)")
            return True

        if pending:
            say(f"Found {len(pending)} pending migration(s) for {backend}:")
            done = (_run_pending_pg(engine, pending, dry_run) if is_pg
                    else _run_pending_sqlite(pending, dry_run, db_path=sqlite_path))
            if not done:
                return False
        return _replay_serial_steps(engine, is_pg, sqlite_path) if replay else True
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# Serial steps: run again at each start while they leave the unique index pending
# ---------------------------------------------------------------------------

SERIAL_STEPS = ("142_serial_per_ca_and_proxy_links", "144_canonical_certificate_serials")


def _serial_steps_pending(engine) -> bool:
    from utils.serial_duplicates import PENDING_KEY
    if "system_config" not in inspect(engine).get_table_names():
        return False
    with engine.connect() as conn:
        return conn.execute(text("SELECT 1 FROM system_config WHERE key = :k"),
                            {"k": PENDING_KEY}).first() is not None


def _replay_serial_steps(engine, is_pg: bool, sqlite_path) -> bool:
    """Steps 142 and 144 alone, idempotent; the 300 row and its date stay as they are."""
    from migrations._from_2_254 import step
    say("  → serial_unique_index_pending is set: upgrade steps 142 and 144 run again...", end=" ")
    try:
        if is_pg:
            with engine.begin() as conn:
                for name in SERIAL_STEPS:
                    step(name).upgrade(conn)
        else:
            conn = sqlite3.connect(sqlite_path or os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db"))
            try:
                for name in SERIAL_STEPS:
                    step(name).upgrade(conn)
            finally:
                conn.close()
    except Exception as exc:  # noqa: BLE001
        say(f"✗ {exc}")
        return False
    say("✓")
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
    say(f"  → {name}...", end=" ", flush=True)
    if dry_run:
        say("(dry run)")
        return True
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
            say("SKIP (no upgrade)")
            return False
        conn.execute("INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        say("✓")
        return True
    except Exception as e:  # noqa: BLE001
        # A failed migration is never recorded: its steps are idempotent, the next start runs it again
        conn.rollback()
        say(f"✗ {e}")
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


# Migrations at this index or above MUST declare pg_compatible=True (every 3.0 migration).
PG_COMPATIBLE_REQUIRED_FROM = 20


def _run_pending_pg(engine, pending, dry_run) -> bool:
    """Run pending migrations against PostgreSQL.

    A migration runs only if it declares `pg_compatible = True` and exposes
    `upgrade(conn)`. Migrations numbered < 020 that don't declare
    pg_compatible are silently marked applied (they are SQLite-only by
    design). Migrations numbered >= 020 that don't declare pg_compatible
    are a HARD ERROR — silent-skip was the root cause of issue #115.
    """
    for name in pending:
        path = MIGRATIONS_DIR / f"{name}.py"
        say(f"  → {name}...", end=" ", flush=True)
        if dry_run:
            say("(dry run)")
            continue
        try:
            mod = _load_module(path)
            is_pg_compatible = getattr(mod, "pg_compatible", False)
            idx = _migration_index(name)

            if not is_pg_compatible and idx >= PG_COMPATIBLE_REQUIRED_FROM:
                # Hard fail — refuse to silently skip a "new-era" migration.
                say("✗")
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
                    say("✓")
                else:
                    say("(SQLite-only, skipped)")
                conn.execute(
                    text(
                        f"INSERT INTO _migrations (name, applied_at) VALUES (:n, {_PG_NOW_UTC}) "
                        "ON CONFLICT (name) DO NOTHING"
                    ),
                    {"n": name},
                )
        except Exception as e:  # noqa: BLE001
            say(f"✗ {e}")
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
        engine = create_engine(sqlalchemy_url(db_url), hide_parameters=True,
                           connect_args=postgres_connect_args(db_url))
    except Exception as e:
        say(f"✗ Cannot connect: {e}")
        return
    try:
        state, applied = _get_state(engine)
        say(f"State:   {state}")
        refusal = pivot_refusal(state, applied)
        if refusal:
            say(f"Refused: {refusal}")
        all_names = _list_migration_names()
        pending = [n for n in all_names if n not in applied]
        say(f"Applied: {len(applied)}")
        say(f"Pending: {len(pending)}")
        for n in sorted(applied):
            say(f"  ✓ {n}")
        for n in pending:
            say(f"  ○ {n}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="UCM Database Migration Runner")
    parser.add_argument(
        "command",
        choices=["run", "status", "dry-run", "mark-applied"],
        nargs="?",
        default="status",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    if args.command == "status":
        show_status()
    elif args.command == "dry-run":
        run_all_migrations(dry_run=True, verbose=args.verbose)
    elif args.command == "run":
        sys.exit(0 if run_all_migrations(verbose=args.verbose) else 1)
    elif args.command == "mark-applied":
        mark_all_applied()
        say("✓ All current migrations marked as applied")
