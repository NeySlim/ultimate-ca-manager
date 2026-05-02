"""
Database Admin — data migration and auth bootstrap functions.
"""

import logging
from typing import Tuple

from sqlalchemy import create_engine, inspect, text

from .helpers import (
    _backup_current_db,
    _detect_boolean_columns,
    _detect_json_columns,
    _force_register_all_models,
    _normalize_row,
    _reset_pg_sequences,
    _short_err,
    _topo_sort_tables,
    _try_disable_fks,
    _try_reenable_fks,
)
from .status import test_connection

logger = logging.getLogger(__name__)

# Tables that must be present on a target backend even when an admin switches
# WITHOUT migrating data, so we don't lock everyone out of the new empty DB.
# Order matters: parents before children to satisfy FKs without disabling them.
BOOTSTRAP_AUTH_TABLES = (
    "users",
    "groups",
    "group_members",
    "pro_custom_roles",
    "pro_role_permissions",
    "pro_sso_providers",
    "pro_sso_sessions",
    "webauthn_credentials",
    "webauthn_challenges",
    "api_keys",
    # Keep system_config so SSO/SMTP/HSM toggles survive the switch
    "system_config",
)


def bootstrap_auth_to_target(target_url: str) -> Tuple[bool, str, dict]:
    """
    Copy auth/RBAC/SSO/MFA tables from the current DB to a fresh target so
    admins, custom roles and SSO config survive a `switch_backend` call.

    Used when the user switches backends WITHOUT a full data migration.
    Without this, the new DB has no users → nobody can log in → lockout.

    Safe to call against an empty target. If the target already has any users,
    bootstrap is skipped (we assume the operator manages that DB themselves).
    """
    # Force-load every model module so db.metadata.create_all() sees them.
    # Some modules (webhooks, …) are only imported when their feature runs.
    _force_register_all_models()

    stats = {"tables_bootstrapped": 0, "rows_copied": 0, "skipped": []}
    try:
        from models import db as _db
        source_engine = _db.engine
        target_engine = create_engine(target_url, pool_pre_ping=True)

        # Build schema on target via SQLAlchemy metadata (safe to call repeatedly)
        _db.metadata.create_all(target_engine)

        target_is_pg = target_url.startswith("postgresql")
        source_is_pg = str(source_engine.url).startswith("postgresql")

        target_insp = inspect(target_engine)
        target_tables = set(target_insp.get_table_names())
        target_cols_by_table = {
            t: {c["name"] for c in target_insp.get_columns(t)} for t in target_tables
        }
        target_json_cols = _detect_json_columns(target_insp, target_tables)
        target_bool_cols = _detect_boolean_columns(target_insp, target_tables)

        # Refuse to bootstrap if target already has users (already provisioned)
        if "users" in target_tables:
            with target_engine.connect() as probe:
                row = probe.execute(text('SELECT COUNT(*) FROM users')).fetchone()
                if row and row[0] and row[0] > 0:
                    target_engine.dispose()
                    return True, "Target already has users; bootstrap skipped.", stats

        with source_engine.connect() as src:
            for table_name in BOOTSTRAP_AUTH_TABLES:
                if table_name not in target_tables:
                    stats["skipped"].append(f"{table_name} (missing on target)")
                    continue
                try:
                    target_cols = target_cols_by_table[table_name]
                    rows = list(src.execute(text(f'SELECT * FROM "{table_name}"')).mappings())
                    if not rows:
                        stats["tables_bootstrapped"] += 1
                        continue
                    src_cols = list(rows[0].keys())
                    cols = [c for c in src_cols if c in target_cols]
                    if not cols:
                        stats["skipped"].append(f"{table_name} (no overlapping columns)")
                        continue
                    placeholders = ", ".join(f":{c}" for c in cols)
                    col_list = ", ".join(f'"{c}"' for c in cols)
                    insert_sql = text(
                        f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
                    )
                    json_cols_here = target_json_cols.get(table_name, set())
                    bool_cols_here = target_bool_cols.get(table_name, set())
                    # Per-table transaction: a single bad row on PG poisons the
                    # whole tx (InFailedSqlTransaction), so isolate each table.
                    with target_engine.begin() as dst:
                        _try_disable_fks(dst, target_is_pg)
                        for row in rows:
                            d = _normalize_row(
                                dict(row),
                                source_is_pg,
                                target_is_pg,
                                json_cols_here,
                                bool_cols_here,
                            )
                            d = {c: d.get(c) for c in cols}
                            dst.execute(insert_sql, d)
                    stats["tables_bootstrapped"] += 1
                    stats["rows_copied"] += len(rows)
                except Exception as e:
                    err = f"{table_name}: {_short_err(str(e))}"
                    logger.error(f"Bootstrap error on table {err}")
                    stats["skipped"].append(err)

        if target_is_pg:
            _reset_pg_sequences(target_engine)

        target_engine.dispose()

        # If users table failed, lockout is guaranteed — surface as failure.
        if stats["rows_copied"] == 0 or any(
            s.startswith("users:") or s.startswith("users ") for s in stats["skipped"]
        ):
            return (
                False,
                "Bootstrap failed for users table — switch aborted to prevent lockout",
                stats,
            )

        return True, "Auth tables bootstrapped to target", stats

    except Exception as e:
        logger.exception("bootstrap_auth_to_target failed")
        return False, f"Bootstrap failed: {_short_err(str(e))}", stats


def migrate_data(target_url: str) -> Tuple[bool, str, dict]:
    """
    Migrate all data from current backend → target_url.
    Steps:
      1. Validate target connection
      2. Backup current DB (file copy for SQLite, pg_dump for PG)
      3. Dump all rows from current DB
      4. Create schema on target via SQLAlchemy create_all
      5. Load rows into target
      6. Reset PG sequences if target is PG
      7. Return success — caller persists URL + restarts
    On failure: target is left in whatever state it reached. Caller should NOT
    persist the URL. Source DB is untouched.
    """
    # Force-load every model module so db.metadata.create_all() sees them.
    _force_register_all_models()

    stats = {
        "tables_migrated": 0,
        "rows_migrated": 0,
        "backup_path": None,
        "errors": [],
        "dropped_columns": {},
    }

    ok, msg = test_connection(target_url)
    if not ok:
        return False, f"Target unreachable: {msg}", stats

    # Refuse if target already contains UCM data (avoid silent data clobbering / partial states)
    # NOTE: this check is fail-closed. If we cannot inspect the target, we
    # refuse to migrate rather than risk overwriting an existing database.
    try:
        probe_engine = create_engine(target_url, pool_pre_ping=True)
        probe_insp = inspect(probe_engine)
        existing_tables = [
            t for t in probe_insp.get_table_names()
            if not t.startswith("_") and t != "alembic_version"
        ]
        non_empty = []
        if existing_tables:
            with probe_engine.connect() as probe:
                # Check a few canonical tables — if any has rows, we refuse
                for tname in ("users", "cas", "certificates"):
                    if tname in existing_tables:
                        try:
                            row = probe.execute(text(f'SELECT COUNT(*) FROM "{tname}"')).fetchone()
                            if row and row[0] and row[0] > 0:
                                non_empty.append(f"{tname}={row[0]}")
                        except Exception as inner:
                            # Fail-closed: treat unreadable canonical tables as
                            # potentially populated to avoid silent overwrite.
                            logger.warning(
                                f"Could not verify emptiness of '{tname}' on target ({inner}); "
                                "treating as non-empty for safety."
                            )
                            non_empty.append(f"{tname}=?")
        probe_engine.dispose()
        if non_empty:
            target_is_pg = target_url.startswith("postgresql")
            cleanup_hint = (
                'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
                if target_is_pg else 'rm <target>.db'
            )
            return False, (
                f"Target database is not empty ({', '.join(non_empty)}). "
                f"Refusing to overwrite. To reset the target, run: {cleanup_hint}"
            ), stats
    except Exception as e:
        # Inspector itself failed — fail-closed.
        return False, (
            f"Could not inspect target database to verify it is empty ({e}). "
            "Refusing to migrate. Verify connectivity and permissions."
        ), stats

    # 1. Backup source
    try:
        backup_path = _backup_current_db()
        stats["backup_path"] = str(backup_path) if backup_path else None
    except Exception as e:
        return False, f"Backup failed: {e}", stats

    # 2. Migrate
    try:
        from models import db as _db
        source_engine = _db.engine
        target_engine = create_engine(target_url, pool_pre_ping=True)

        # Build schema on target via SQLAlchemy metadata (covers all models
        # registered above by _force_register_all_models)
        _db.metadata.create_all(target_engine)

        # Create _migrations table on target (not part of SQLAlchemy metadata).
        # Use a backend-appropriate auto-increment primary key — plain
        # "INTEGER PRIMARY KEY" auto-increments on SQLite but NOT on
        # PostgreSQL, where it would force callers to supply an id.
        target_is_pg = target_url.startswith("postgresql")
        source_is_pg = str(source_engine.url).startswith("postgresql")
        if target_is_pg:
            migrations_ddl = """
                CREATE TABLE IF NOT EXISTS _migrations (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
        else:
            migrations_ddl = """
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
        with target_engine.begin() as dst:
            dst.execute(text(migrations_ddl))

        # Copy each table
        # Pre-fetch inspectors before opening transactions (SQLite locking)
        src_insp = inspect(source_engine)
        target_insp = inspect(target_engine)
        target_tables = set(target_insp.get_table_names())
        target_cols_by_table = {
            t: {c["name"] for c in target_insp.get_columns(t)} for t in target_tables
        }
        target_json_cols = _detect_json_columns(target_insp, target_tables)
        target_bool_cols = _detect_boolean_columns(target_insp, target_tables)
        src_table_names = _topo_sort_tables(src_insp)

        with source_engine.connect() as src, target_engine.begin() as dst:
            # Disable FK checks during bulk load to avoid ordering issues.
            # Falls back gracefully if the PG user is not a superuser
            # (session_replication_role is superuser-only) — in that case we
            # rely on the topological order computed above.
            fk_disabled = _try_disable_fks(dst, target_is_pg)

            for table_name in src_table_names:
                if table_name.startswith("_") and table_name != "_migrations":
                    continue  # skip internal tables but keep _migrations
                if table_name not in target_tables:
                    logger.warning(f"Skipping table {table_name}: not in target schema")
                    continue
                try:
                    target_cols = target_cols_by_table[table_name]
                    rows = list(src.execute(text(f'SELECT * FROM "{table_name}"')).mappings())
                    if not rows:
                        stats["tables_migrated"] += 1
                        continue
                    src_cols = list(rows[0].keys())
                    cols = [c for c in src_cols if c in target_cols]
                    dropped = [c for c in src_cols if c not in target_cols]
                    if dropped:
                        logger.warning(f"{table_name}: dropping columns absent in target: {dropped}")
                        stats["dropped_columns"][table_name] = dropped
                    if not cols:
                        logger.warning(f"{table_name}: no overlapping columns, skipping")
                        continue
                    placeholders = ", ".join(f":{c}" for c in cols)
                    col_list = ", ".join(f'"{c}"' for c in cols)
                    insert_sql = text(
                        f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
                    )
                    json_cols_here = target_json_cols.get(table_name, set())
                    bool_cols_here = target_bool_cols.get(table_name, set())
                    for row in rows:
                        d = _normalize_row(
                            dict(row),
                            source_is_pg,
                            target_is_pg,
                            json_cols_here,
                            bool_cols_here,
                        )
                        d = {c: d.get(c) for c in cols}
                        dst.execute(insert_sql, d)
                    stats["tables_migrated"] += 1
                    stats["rows_migrated"] += len(rows)
                except Exception as e:
                    err = f"{table_name}: {_short_err(str(e))}"
                    logger.error(f"Migration error on table {err}")
                    stats["errors"].append(err)
                    raise

            _try_reenable_fks(dst, target_is_pg, fk_disabled)

        # Reset PG sequences if target is PG
        if target_url.startswith("postgresql"):
            _reset_pg_sequences(target_engine)

        target_engine.dispose()
        return True, "Data migrated successfully", stats

    except Exception as e:
        logger.exception("Data migration failed")
        target_is_pg = target_url.startswith("postgresql")
        cleanup_hint = (
            'Reset the target before retrying: DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
            if target_is_pg else
            'Reset the target before retrying: delete the target SQLite file.'
        )
        return False, (
            f"Migration failed: {_short_err(str(e))}. "
            f"Target may be in a partial state. {cleanup_hint} "
            f"Source database is untouched (backup at {stats.get('backup_path')})."
        ), stats
