"""
Regression test for #103 / #104: PostgreSQL migration runner.

Bug: ``_run_pending_pg`` previously passed an SQLAlchemy ``Engine`` to
migration modules' ``upgrade()`` callable. Migration modules expect a
``Connection``, so any pg-compatible migration crashed on first run.
Fix: open a single transactional ``Connection`` via ``engine.begin()`` and
hand THAT to ``mod.upgrade(conn)``. SQLite path was unaffected.

This test guards against re-introduction of the regression by:
  1. Asserting the source of `_run_pending_pg` calls `engine.begin()` and
     passes the resulting `conn` to `mod.upgrade()` (static guard, runs in
     the SQLite CI job too — fast, no Postgres needed).
  2. When `UCM_TEST_POSTGRES_URL` is set (PG CI job only), running an actual
     migration against a real PostgreSQL instance and asserting it applied.

Marked with `pytest.mark.postgres` so the PG-only end-to-end check is
skipped in plain SQLite runs.
"""
from __future__ import annotations

import inspect
import os
import textwrap

import pytest


# ---------------------------------------------------------------------------
# Static guard — runs in every CI job (no PG needed)
# ---------------------------------------------------------------------------

def test_run_pending_pg_uses_connection_not_engine():
    """`_run_pending_pg` must hand a Connection (via engine.begin()) to upgrade(),
    NOT the engine itself. This is the exact regression of #103/#104."""
    import migration_runner

    src = inspect.getsource(migration_runner._run_pending_pg)

    # Must open a transactional connection.
    assert "engine.begin()" in src, (
        "_run_pending_pg must use `with engine.begin() as conn:` — "
        "regression of #103/#104 (engine vs. connection)."
    )

    # Must pass the conn (not engine) to mod.upgrade.
    # We allow either `mod.upgrade(conn)` or any call that names the conn.
    assert "mod.upgrade(conn)" in src, (
        "_run_pending_pg must call `mod.upgrade(conn)`, not `mod.upgrade(engine)`. "
        "Migration modules expect a Connection."
    )
    assert "mod.upgrade(engine)" not in src, (
        "Found `mod.upgrade(engine)` in _run_pending_pg — this is the #103 bug."
    )


# ---------------------------------------------------------------------------
# Static guard — every pg_compatible migration must NOT open a nested tx
# (regression #111: `_upgrade_pg(engine)` did `with engine.begin() as conn`
# but the runner now passes a Connection, raising "transaction already begun"
# and breaking every PG upgrade to v2.149).
# ---------------------------------------------------------------------------

def test_pg_migrations_do_not_open_nested_transactions():
    """All pg_compatible migrations must use the Connection passed by the
    runner directly. They MUST NOT call ``engine.begin()`` / ``conn.begin()``
    because the runner already opens the transaction.
    """
    import ast
    import pathlib

    migrations_dir = pathlib.Path(__file__).resolve().parent.parent / "migrations"
    offenders = []
    for path in sorted(migrations_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        src = path.read_text()
        if "pg_compatible = True" not in src:
            continue
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "begin" and isinstance(node.func.value, ast.Name):
                    if node.func.value.id in ("engine", "conn"):
                        offenders.append(f"{path.name}:{node.lineno}")

    assert not offenders, (
        "Migration(s) call `.begin()` on the runner-supplied Connection. "
        "The runner already opens `with engine.begin() as conn:` and passes "
        "the Connection to upgrade(); calling .begin() again raises "
        '"transaction already begun" and breaks PG upgrades (issue #111). '
        f"Offenders: {offenders}"
    )


# ---------------------------------------------------------------------------
# Static guard — every migration numbered >= 020 MUST declare pg_compatible.
# Issue #115: migrations 031-034 shipped without `pg_compatible = True` and
# were silently marked applied on PostgreSQL without executing, leaving the
# schema out of sync with the models.
# ---------------------------------------------------------------------------

def test_modern_migrations_declare_pg_compatible():
    """Every migration file numbered >= 020 must declare `pg_compatible = True`.

    Migrations 000-019 are SQLite-only by design (predate PG support) and are
    silently skipped on PostgreSQL. From 020 onward, every migration MUST be
    multi-backend or it will silently no-op on PG and corrupt the schema.
    """
    import pathlib
    import re

    migrations_dir = pathlib.Path(__file__).resolve().parent.parent / "migrations"
    offenders = []
    for path in sorted(migrations_dir.glob("*.py")):
        if path.name.startswith("__"):
            continue
        # Extract leading numeric index
        m = re.match(r"^(\d+)_", path.name)
        if not m:
            continue
        idx = int(m.group(1))
        if idx < 20:
            continue
        src = path.read_text()
        if "pg_compatible = True" not in src and "pg_compatible=True" not in src:
            offenders.append(path.name)

    assert not offenders, (
        "Migration(s) numbered >= 020 must declare `pg_compatible = True` "
        "(silent-skip on PG corrupts the schema — issue #115). "
        f"Offenders: {offenders}"
    )


def test_runner_rejects_modern_migration_without_pg_compatible():
    """The runner must raise (return False) when a migration numbered >= 020
    lacks `pg_compatible = True`, instead of silently marking it applied.
    """
    import migration_runner

    src = inspect.getsource(migration_runner._run_pending_pg)
    # Must reference the threshold and refuse to continue.
    assert "PG_COMPATIBLE_REQUIRED_FROM" in src, (
        "Runner must check PG_COMPATIBLE_REQUIRED_FROM threshold; "
        "silent-skip caused issue #115."
    )
    assert "return False" in src, (
        "Runner must return False (hard fail) on missing pg_compatible "
        "for modern migrations, not silently skip."
    )


# ---------------------------------------------------------------------------
# End-to-end — PG CI job only
# ---------------------------------------------------------------------------

PG_URL = os.environ.get("UCM_TEST_POSTGRES_URL")


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason="UCM_TEST_POSTGRES_URL not set; skipping PG e2e migration test")
def test_pg_migration_runs_against_real_postgres(tmp_path, monkeypatch):
    """End-to-end: write a fake pg_compatible migration on disk, run it
    against a real Postgres, assert it actually applied (created a table)."""
    from sqlalchemy import create_engine, text

    import migration_runner

    # Isolate the migrations directory to a tempdir so we don't run all the
    # real migrations against the CI database.
    migrations_dir = tmp_path / "migrations"
    migrations_dir.mkdir()

    # Bootstrap _migrations table (normally done by migration_runner itself).
    engine = create_engine(PG_URL)
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS _migrations ("
                "name TEXT PRIMARY KEY, applied_at TIMESTAMP DEFAULT NOW())"
            )
        )
        # Clean slate for our fake migration.
        conn.execute(text("DROP TABLE IF EXISTS regression_103_marker"))
        conn.execute(text("DELETE FROM _migrations WHERE name = '999_regression_103'"))

    # Write a fake pg-compatible migration that takes a Connection (not Engine).
    fake = migrations_dir / "999_regression_103.py"
    fake.write_text(textwrap.dedent("""
        pg_compatible = True

        def upgrade(conn):
            # If conn is an Engine, this call shape will raise.
            # If conn is a Connection (the fix), this works.
            from sqlalchemy import text
            conn.execute(text("CREATE TABLE regression_103_marker (id INT PRIMARY KEY)"))
    """).lstrip())

    # Point the runner at our temp migrations dir.
    monkeypatch.setattr(migration_runner, "MIGRATIONS_DIR", migrations_dir)

    ok = migration_runner._run_pending_pg(engine, ["999_regression_103"], dry_run=False)
    assert ok, "_run_pending_pg returned False — migration did not apply"

    with engine.begin() as conn:
        marker = conn.execute(
            text("SELECT to_regclass('public.regression_103_marker')")
        ).scalar()
        assert marker is not None, (
            "regression_103_marker table was not created — _run_pending_pg "
            "did not actually execute the migration."
        )
        applied = conn.execute(
            text("SELECT COUNT(*) FROM _migrations WHERE name = '999_regression_103'")
        ).scalar()
        assert applied == 1, "migration not recorded in _migrations table"

    # Cleanup
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS regression_103_marker"))
        conn.execute(text("DELETE FROM _migrations WHERE name = '999_regression_103'"))
