#!/usr/bin/env python3
"""
UCM Database Bootstrap & Migration Runner
==========================================

Backend-agnostic. Supports SQLite and PostgreSQL.

Bootstrap states
----------------
- FRESH:      No `_migrations` table, no business tables.
              -> Schema is built by SQLAlchemy `db.create_all()`.
              -> All current migrations are then marked as applied
                 so future migrations from this point work normally.
- TRACKED:    `_migrations` table exists.
              -> Pending migrations are applied.
- LEGACY:     Business tables exist (e.g. `users`) but no `_migrations`.
              -> Tracking table is created and pending migrations applied
                 (typical of pre-2.x SQLite installs).

Backend behavior
----------------
- SQLite legacy install -> runs SQLite-only migrations as before.
- PostgreSQL install    -> always treated as FRESH (we never had a PG
                           install before, so legacy SQLite migrations
                           are not relevant). After create_all() the
                           caller invokes `mark_all_applied()`.

Future migrations
-----------------
Starting with migration 020 (v2.128), every new migration MUST be
multi-backend:

  * Set ``pg_compatible = True`` at module scope.
  * Expose ``upgrade(arg)`` that accepts EITHER ``sqlite3.Connection``
    (SQLite path) OR ``sqlalchemy.Engine`` (PostgreSQL path).
  * Use ``isinstance(arg, sqlite3.Connection)`` to dispatch.

Migrations 000-019 are SQLite-only by design (they predate native PG
support) and are silently skipped on PostgreSQL.

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
    return db_url.startswith(("postgresql://", "postgres://"))


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
        return ("tracked", {r[0] for r in rows})
    if has_data:
        return ("legacy", set())
    return ("fresh", set())


# ---------------------------------------------------------------------------
# Tracking table management
# ---------------------------------------------------------------------------

_DDL_PG = """
CREATE TABLE IF NOT EXISTS _migrations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS _migrations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_tracking_table(engine, is_pg: bool):
    with engine.begin() as conn:
        conn.execute(text(_DDL_PG if is_pg else _DDL_SQLITE))


def _mark_applied(engine, names, is_pg: bool):
    if not names:
        return
    sql = (
        "INSERT INTO _migrations (name) VALUES (:n) ON CONFLICT (name) DO NOTHING"
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
    engine = create_engine(db_url)
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
        engine = create_engine(db_url)
    except Exception as exc:
        print(f"✗ Could not connect to database ({backend}): {exc}")
        return False

    try:
        state, applied = _get_state(engine)

        if state == "fresh":
            print(
                f"✓ Fresh {backend} database — schema will be built by "
                f"SQLAlchemy create_all() (skipping legacy SQL migrations)"
            )
            return True

        if state == "legacy":
            _ensure_tracking_table(engine, is_pg)

        all_names = _list_migration_names()
        pending = [n for n in all_names if n not in applied]

        if not pending:
            print(f"✓ {backend} database up to date (no pending migrations)")
            return True

        print(f"Found {len(pending)} pending migration(s) for {backend}:")
        if is_pg:
            return _run_pending_pg(engine, pending, dry_run)
        return _run_pending_sqlite(pending, dry_run)
    finally:
        engine.dispose()


# ---------------------------------------------------------------------------
# SQLite execution path (legacy migrations 000-019 are SQLite-only)
# ---------------------------------------------------------------------------

def _run_pending_sqlite(pending, dry_run) -> bool:
    db_path = os.environ.get("DATABASE_PATH", "/opt/ucm/data/ucm.db")
    if not os.path.exists(db_path):
        print(f"✗ SQLite file not found: {db_path}")
        return False
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_DDL_SQLITE)
        conn.commit()
        for name in pending:
            path = MIGRATIONS_DIR / f"{name}.py"
            if not _run_one_sqlite(conn, path, db_path, dry_run):
                print("✗ Migration failed — stopping")
                return False
        print("✓ All migrations applied")
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
    print(f"  → {name}...", end=" ", flush=True)
    if dry_run:
        print("(dry run)")
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
                pname = list(sig.parameters)[0].lower()
                mod.upgrade(conn) if "conn" in pname else mod.upgrade(db_path)
            else:
                mod.upgrade(conn)
        elif hasattr(mod, "MIGRATION_SQL"):
            conn.executescript(mod.MIGRATION_SQL)
        else:
            print("SKIP (no upgrade)")
            return False
        conn.execute("INSERT INTO _migrations (name) VALUES (?)", (name,))
        conn.commit()
        print("✓")
        return True
    except sqlite3.IntegrityError:
        conn.rollback()
        print("(already applied)")
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        msg = str(e).lower()
        if "already exists" in msg or "duplicate" in msg:
            conn.execute(
                "INSERT OR IGNORE INTO _migrations (name) VALUES (?)", (name,)
            )
            conn.commit()
            print("✓ (table existed)")
            return True
        print(f"✗ {e}")
        return False


# ---------------------------------------------------------------------------
# PostgreSQL execution path
# ---------------------------------------------------------------------------

def _run_pending_pg(engine, pending, dry_run) -> bool:
    """Run pending migrations against PostgreSQL.

    A migration runs only if it declares `pg_compatible = True` and exposes
    `upgrade(engine)`. Anything else is silently marked applied (legacy
    SQLite migrations don't apply to PG installs that started fresh).
    """
    for name in pending:
        path = MIGRATIONS_DIR / f"{name}.py"
        print(f"  → {name}...", end=" ", flush=True)
        if dry_run:
            print("(dry run)")
            continue
        try:
            mod = _load_module(path)
            if getattr(mod, "pg_compatible", False) and hasattr(mod, "upgrade"):
                mod.upgrade(engine)
                print("✓")
            else:
                print("(SQLite-only — skipped)")
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "INSERT INTO _migrations (name) VALUES (:n) "
                        "ON CONFLICT (name) DO NOTHING"
                    ),
                    {"n": name},
                )
        except Exception as e:  # noqa: BLE001
            print(f"✗ {e}")
            return False
    print("✓ All migrations applied")
    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def show_status():
    db_url = _get_db_url()
    is_pg = _is_postgres(db_url)
    print("=== Migration Status ===")
    print(f"Backend: {'PostgreSQL' if is_pg else 'SQLite'}")
    print(f"URL:     {db_url.split('@')[-1] if '@' in db_url else db_url}")
    try:
        engine = create_engine(db_url)
    except Exception as e:
        print(f"✗ Cannot connect: {e}")
        return
    try:
        state, applied = _get_state(engine)
        print(f"State:   {state}")
        all_names = _list_migration_names()
        pending = [n for n in all_names if n not in applied]
        print(f"Applied: {len(applied)}")
        print(f"Pending: {len(pending)}")
        for n in sorted(applied):
            print(f"  ✓ {n}")
        for n in pending:
            print(f"  ○ {n}")
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
        print("✓ All current migrations marked as applied")
