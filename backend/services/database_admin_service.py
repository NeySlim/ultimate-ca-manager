"""
Database Admin Service
Manages database backend status, testing, switching, and data migration
between SQLite and PostgreSQL.
"""

import os
import re
import json
import shutil
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from config.settings import Config, DATA_DIR, is_docker
from models import db

logger = logging.getLogger(__name__)

UCM_ENV_PATH = Path("/etc/ucm/ucm.env")
BACKUP_DIR = DATA_DIR / "backups" / "db_migration"


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """Return current backend status: type, version, size, table count, health."""
    db_uri = Config.SQLALCHEMY_DATABASE_URI
    backend = "postgresql" if db_uri.startswith("postgresql") else "sqlite"

    info = {
        "backend": backend,
        "uri_redacted": _redact_uri(db_uri),
        "is_docker": is_docker(),
        "table_count": 0,
        "size_bytes": 0,
        "size_human": "0 B",
        "version": None,
        "healthy": False,
        "error": None,
    }

    try:
        engine = db.engine
        with engine.connect() as conn:
            insp = inspect(engine)
            info["table_count"] = len(insp.get_table_names())

            if backend == "sqlite":
                db_path = db_uri.replace("sqlite:///", "")
                if os.path.exists(db_path):
                    info["size_bytes"] = os.path.getsize(db_path)
                row = conn.execute(text("SELECT sqlite_version()")).fetchone()
                info["version"] = f"SQLite {row[0]}" if row else "SQLite"
            else:
                row = conn.execute(text("SELECT version()")).fetchone()
                info["version"] = row[0].split(",")[0] if row else "PostgreSQL"
                row = conn.execute(text(
                    "SELECT pg_database_size(current_database())"
                )).fetchone()
                info["size_bytes"] = int(row[0]) if row else 0

            info["size_human"] = _human_size(info["size_bytes"])
            info["healthy"] = True
    except Exception as e:
        logger.error(f"get_status failed: {e}")
        info["error"] = str(e)

    return info


# ---------------------------------------------------------------------------
# Test connection
# ---------------------------------------------------------------------------

MIN_POSTGRES_MAJOR = 13


def test_connection(database_url: str) -> Tuple[bool, str]:
    """Validate a DATABASE_URL by opening a connection and running SELECT 1.
    For PostgreSQL, also checks server version >= MIN_POSTGRES_MAJOR.
    """
    if not database_url or not isinstance(database_url, str):
        return False, "DATABASE_URL is required"

    parsed = urlparse(database_url)
    if parsed.scheme not in ("postgresql", "postgresql+psycopg2", "sqlite"):
        return False, f"Unsupported scheme: {parsed.scheme}"

    try:
        engine = create_engine(
            database_url,
            connect_args={"connect_timeout": 5} if parsed.scheme.startswith("postgresql") else {},
            pool_pre_ping=True,
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if parsed.scheme.startswith("postgresql"):
                row = conn.execute(text("SHOW server_version_num")).fetchone()
                if row:
                    try:
                        ver_num = int(row[0])  # e.g. 130012 = 13.12, 160003 = 16.3
                        major = ver_num // 10000
                        if major < MIN_POSTGRES_MAJOR:
                            engine.dispose()
                            return False, (
                                f"PostgreSQL {major} is not supported. "
                                f"UCM requires PostgreSQL {MIN_POSTGRES_MAJOR} or newer."
                            )
                    except (ValueError, TypeError):
                        pass  # don't fail on parse errors, just skip the check
        engine.dispose()
        return True, "Connection successful"
    except SQLAlchemyError as e:
        return False, f"Connection failed: {_short_err(str(e))}"
    except Exception as e:
        return False, f"Connection failed: {_short_err(str(e))}"


# ---------------------------------------------------------------------------
# Persist DATABASE_URL to /etc/ucm/ucm.env
# ---------------------------------------------------------------------------

def persist_database_url(database_url: Optional[str]) -> Tuple[bool, str]:
    """
    Write DATABASE_URL to /etc/ucm/ucm.env (set/update/remove).
    Pass None or empty string to remove (= use SQLite default).
    Refuses in Docker (caller must check first).
    """
    if is_docker():
        return False, "Cannot modify ucm.env in Docker. Set DATABASE_URL env var instead."

    try:
        UCM_ENV_PATH.parent.mkdir(parents=True, exist_ok=True)
        existing = UCM_ENV_PATH.read_text() if UCM_ENV_PATH.exists() else ""

        lines = [ln for ln in existing.splitlines() if not ln.startswith("DATABASE_URL=") and not ln.startswith("#DATABASE_URL=")]

        if database_url:
            lines.append(f"DATABASE_URL={database_url}")

        new_content = "\n".join(lines).rstrip() + "\n"
        UCM_ENV_PATH.write_text(new_content)
        os.chmod(UCM_ENV_PATH, 0o640)
        return True, "DATABASE_URL persisted"
    except PermissionError as e:
        return False, f"Permission denied writing {UCM_ENV_PATH}: {e}"
    except Exception as e:
        logger.error(f"persist_database_url failed: {e}")
        return False, f"Failed to persist DATABASE_URL: {e}"


# ---------------------------------------------------------------------------
# Data migration (dump/load)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _redact_uri(uri: str) -> str:
    """Hide password in DB URI for display."""
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", uri)


def _short_err(msg: str, limit: int = 200) -> str:
    msg = msg.replace("\n", " ").strip()
    return msg[:limit] + "..." if len(msg) > limit else msg


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _backup_current_db() -> Optional[Path]:
    """Backup current DB before migration. Returns backup path or None."""
    import subprocess
    import os
    from urllib.parse import urlparse
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    db_uri = Config.SQLALCHEMY_DATABASE_URI

    if db_uri.startswith("sqlite:///"):
        src = Path(db_uri.replace("sqlite:///", ""))
        if not src.exists():
            return None
        dst = BACKUP_DIR / f"ucm-sqlite-{timestamp}.db"
        shutil.copy2(src, dst)
        return dst
    else:
        # PostgreSQL: use pg_dump
        try:
            parsed = urlparse(db_uri)
            db_config = {
                'host': parsed.hostname or 'localhost',
                'port': str(parsed.port or 5432),
                'user': parsed.username or '',
                'password': parsed.password or '',
                'dbname': parsed.path[1:] if parsed.path else parsed.netloc.split('/')[-1]
            }
            
            output = BACKUP_DIR / f"ucm-pg-{timestamp}.dump"
            
            cmd = [
                'pg_dump',
                '-h', db_config['host'],
                '-p', db_config['port'],
                '-U', db_config['user'],
                '-d', db_config['dbname'],
                '-F', 'c',  # custom format (compressed)
                '-f', str(output),
                '--no-password'
            ]
            
            env = os.environ.copy()
            env['PGPASSWORD'] = db_config['password']
            
            result = subprocess.run(
                cmd,
                env=env,
                capture_output=True,
                timeout=300,
                check=False
            )
            
            if result.returncode != 0:
                logger.error(f"pg_dump failed: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                return None
            
            logger.info(f"PostgreSQL backup created: {output}")
            return output
            
        except FileNotFoundError:
            logger.error("pg_dump not found. Install postgresql-client.")
            return None
        except Exception as e:
            logger.error(f"PostgreSQL backup failed: {e}")
            return None


def _reset_pg_sequences(engine):
    """Reset PG sequences after data load so new inserts don't collide."""
    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT table_name, column_name "
            "FROM information_schema.columns "
            "WHERE column_default LIKE 'nextval%' AND table_schema = 'public'"
        )).fetchall()
        for table_name, column_name in rows:
            try:
                seq_row = conn.execute(text(
                    "SELECT pg_get_serial_sequence(:t, :c)"
                ), {"t": table_name, "c": column_name}).fetchone()
                if not seq_row or not seq_row[0]:
                    continue  # column has nextval() default but no resolvable seq
                seq_name = seq_row[0]
                conn.execute(text(
                    f"SELECT setval('{seq_name}', "
                    f"COALESCE((SELECT MAX(\"{column_name}\") FROM \"{table_name}\"), 1))"
                ))
            except Exception as e:
                logger.warning(f"Failed to reset sequence for {table_name}.{column_name}: {e}")


def _normalize_row(
    row: dict,
    source_is_pg: bool,
    target_is_pg: bool,
    target_json_cols: Optional[set] = None,
    target_bool_cols: Optional[set] = None,
) -> dict:
    """Normalize values for cross-backend insert.

    - PG → SQLite: dict/list become JSON strings; memoryview → bytes; booleans
      become int (SQLite has no real bool type but accepts ints fine).
    - SQLite → PG: when the target column is JSON/JSONB, JSON-string values
      are parsed back to dict/list so psycopg2's JSON adapter serializes
      them correctly (otherwise PG rejects "raw text into json column").
      When the target column is BOOLEAN, integer 0/1 (or strings "0"/"1"/
      "true"/"false") are coerced to real bool — SQLite stores booleans as
      INTEGER and psycopg2 refuses to insert int into BOOLEAN.
    """
    target_json_cols = target_json_cols or set()
    target_bool_cols = target_bool_cols or set()
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, memoryview):
            out[k] = bytes(v)
        elif isinstance(v, (dict, list)) and not target_is_pg:
            out[k] = json.dumps(v)
        elif (
            target_is_pg
            and not source_is_pg
            and k in target_bool_cols
            and not isinstance(v, bool)
        ):
            # SQLite stored bools as INTEGER (0/1). Coerce to real bool.
            if isinstance(v, (int, float)):
                out[k] = bool(v)
            elif isinstance(v, str):
                s = v.strip().lower()
                if s in ("1", "true", "t", "yes", "y"):
                    out[k] = True
                elif s in ("0", "false", "f", "no", "n", ""):
                    out[k] = False
                else:
                    out[k] = v
            else:
                out[k] = v
        elif target_is_pg and k in target_json_cols:
            # PG json/jsonb columns: always send as JSON-encoded text.
            # - dict/list (SQLAlchemy auto-deserialized SQLite JSON) → encode
            #   so psycopg2 doesn't send a Python list as PostgreSQL ARRAY.
            # - str: keep as-is if already valid JSON, otherwise wrap.
            # PG parses the text into json/jsonb on INSERT.
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v)
            elif isinstance(v, str):
                if v == "":
                    out[k] = None
                else:
                    out[k] = v  # assume already JSON text
            else:
                out[k] = json.dumps(v)
        else:
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Helpers — model registration, FK control, JSON detection, topo sort
# ---------------------------------------------------------------------------

def _force_register_all_models() -> None:
    """Import every model module so db.metadata.create_all sees all tables.

    Some modules are registered lazily (only when their feature runs) which
    means create_all on a fresh target would silently miss their tables.
    """
    try:
        # Core model packages — importing the package triggers SQLAlchemy
        # registration via class definitions.
        import models  # noqa: F401
        from models import (  # noqa: F401
            acme_models, api_key, auth_certificate, certificate_template,
            crl, discovered_certificate, email_notification, group, hsm,
            msca, ocsp, policy, rbac, ssh, sso, truststore, webauthn,
        )
    except Exception as e:
        logger.warning(f"Some core models failed to import: {e}")

    # Service-owned tables (lazy-registered)
    for mod in (
        "services.webhook_service",
        "services.notification_service",
    ):
        try:
            __import__(mod)
        except Exception as e:
            logger.debug(f"Optional model module {mod} not loaded: {e}")


def _detect_json_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for columns whose SQL type is JSON/JSONB."""
    out = {}
    for t in table_names:
        json_cols = set()
        try:
            for col in insp.get_columns(t):
                type_str = str(col.get("type", "")).upper()
                if "JSON" in type_str:  # matches JSON and JSONB
                    json_cols.add(col["name"])
        except Exception:
            continue
        if json_cols:
            out[t] = json_cols
    return out


def _detect_boolean_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for columns whose SQL type is BOOLEAN.

    Needed when migrating SQLite → PostgreSQL: SQLite stores booleans as
    INTEGER (0/1), but psycopg2 refuses to insert int into a real BOOLEAN
    column. We detect them up-front and coerce in _normalize_row.
    """
    out = {}
    for t in table_names:
        bool_cols = set()
        try:
            for col in insp.get_columns(t):
                type_str = str(col.get("type", "")).upper()
                # Match BOOLEAN, BOOL — but NOT TINYINT/SMALLINT (they are
                # integers in SQLite even when SQLAlchemy maps to Boolean).
                if type_str in ("BOOLEAN", "BOOL"):
                    bool_cols.add(col["name"])
        except Exception:
            continue
        if bool_cols:
            out[t] = bool_cols
    return out


def _try_disable_fks(conn, target_is_pg: bool) -> bool:
    """Disable FK checks for bulk load. Returns True if successful.

    On PostgreSQL `SET session_replication_role` requires SUPERUSER. When the
    DBA followed best practice and gave UCM a non-superuser role, the call
    fails — we catch it and rely on the topological insert order instead.
    """
    try:
        if target_is_pg:
            conn.execute(text("SET session_replication_role = 'replica'"))
        else:
            conn.execute(text("PRAGMA foreign_keys = OFF"))
        return True
    except Exception as e:
        logger.warning(
            f"Could not disable FK checks ({_short_err(str(e))}); "
            "falling back to topological insert order."
        )
        return False


def _try_reenable_fks(conn, target_is_pg: bool, was_disabled: bool) -> None:
    if not was_disabled:
        return
    try:
        if target_is_pg:
            conn.execute(text("SET session_replication_role = 'origin'"))
        else:
            conn.execute(text("PRAGMA foreign_keys = ON"))
    except Exception as e:
        logger.warning(f"Could not re-enable FK checks: {_short_err(str(e))}")


def _topo_sort_tables(insp) -> list:
    """Return table names in FK-dependency order (parents first).

    Falls back to alphabetical on any error so a sort failure doesn't
    abort the whole migration.
    """
    try:
        all_tables = insp.get_table_names()
        deps = {t: set() for t in all_tables}
        for t in all_tables:
            for fk in insp.get_foreign_keys(t):
                ref = fk.get("referred_table")
                if ref and ref in deps and ref != t:
                    deps[t].add(ref)

        ordered = []
        remaining = dict(deps)
        while remaining:
            ready = sorted(t for t, d in remaining.items() if not d)
            if not ready:
                # Cycle detected — append the rest in alpha order
                ordered.extend(sorted(remaining.keys()))
                break
            for t in ready:
                ordered.append(t)
                remaining.pop(t)
            for t in remaining:
                remaining[t] -= set(ready)
        return ordered
    except Exception as e:
        logger.warning(f"Topo sort failed ({e}); using alphabetical order.")
        return sorted(insp.get_table_names())
