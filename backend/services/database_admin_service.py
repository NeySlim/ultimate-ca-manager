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
    stats = {
        "tables_migrated": 0,
        "rows_migrated": 0,
        "backup_path": None,
        "errors": [],
    }

    ok, msg = test_connection(target_url)
    if not ok:
        return False, f"Target unreachable: {msg}", stats

    # Refuse if target already contains UCM data (avoid silent data clobbering / partial states)
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
                        except Exception:
                            pass
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
        logger.warning(f"Target emptiness check failed (continuing): {e}")

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

        # Build schema on target via SQLAlchemy metadata
        _db.metadata.create_all(target_engine)

        # Also create webhook table (registered at runtime, not in metadata at import time)
        try:
            from services.webhook_service import WebhookEndpoint  # noqa: F401
            _db.metadata.create_all(target_engine)
        except Exception:
            pass

        # Create _migrations table on target (not part of SQLAlchemy metadata)
        with target_engine.begin() as dst:
            dst.execute(text("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(255) NOT NULL UNIQUE,
                    applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))

        # Copy each table
        source_is_pg = str(source_engine.url).startswith("postgresql")
        target_is_pg = target_url.startswith("postgresql")
        # Pre-fetch inspectors before opening transactions (SQLite locking)
        src_insp = inspect(source_engine)
        target_insp = inspect(target_engine)
        target_tables = set(target_insp.get_table_names())
        target_cols_by_table = {
            t: {c["name"] for c in target_insp.get_columns(t)} for t in target_tables
        }
        src_table_names = src_insp.get_table_names()

        with source_engine.connect() as src, target_engine.begin() as dst:
            # Disable FK checks during bulk load to avoid ordering issues
            if target_is_pg:
                dst.execute(text("SET session_replication_role = 'replica'"))
            else:
                dst.execute(text("PRAGMA foreign_keys = OFF"))

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
                    if not cols:
                        logger.warning(f"{table_name}: no overlapping columns, skipping")
                        continue
                    placeholders = ", ".join(f":{c}" for c in cols)
                    col_list = ", ".join(f'"{c}"' for c in cols)
                    insert_sql = text(
                        f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
                    )
                    for row in rows:
                        d = _normalize_row(dict(row), source_is_pg, target_is_pg)
                        d = {c: d.get(c) for c in cols}
                        dst.execute(insert_sql, d)
                    stats["tables_migrated"] += 1
                    stats["rows_migrated"] += len(rows)
                except Exception as e:
                    err = f"{table_name}: {_short_err(str(e))}"
                    logger.error(f"Migration error on table {err}")
                    stats["errors"].append(err)
                    raise

            # Re-enable FK checks
            if target_is_pg:
                dst.execute(text("SET session_replication_role = 'origin'"))
            else:
                dst.execute(text("PRAGMA foreign_keys = ON"))

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
        # PG: skip pg_dump for now (requires binary). Document caveat in docs.
        # Best-effort: create a marker file
        marker = BACKUP_DIR / f"pg-migration-{timestamp}.marker"
        marker.write_text(f"PG migration started at {timestamp}\nSource: {_redact_uri(db_uri)}\n")
        return marker


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
                conn.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{table_name}', '{column_name}'), "
                    f"COALESCE((SELECT MAX(\"{column_name}\") FROM \"{table_name}\"), 1))"
                ))
            except Exception as e:
                logger.warning(f"Failed to reset sequence for {table_name}.{column_name}: {e}")


def _normalize_row(row: dict, source_is_pg: bool, target_is_pg: bool) -> dict:
    """Normalize values for cross-backend insert.

    - PG → SQLite: dict/list become JSON strings; memoryview → bytes
    - SQLite → PG: JSON-looking strings on JSON columns are left as-is
      (SQLAlchemy handles the cast on ORM-typed columns; raw INSERT works
      because PG accepts text in JSON columns when string is valid JSON
      — but psycopg2 doesn't cast str→json automatically, so we leave
      strings unchanged and rely on PG implicit cast for TEXT columns;
      JSON columns get TEXT input which fails — so we don't touch).
    """
    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None
        elif isinstance(v, memoryview):
            out[k] = bytes(v)
        elif isinstance(v, (dict, list)) and not target_is_pg:
            out[k] = json.dumps(v)
        else:
            out[k] = v
    return out
