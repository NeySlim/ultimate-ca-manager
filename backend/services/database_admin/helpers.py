"""
Database Admin — shared helpers and constants.
Used by status.py, persistence.py, and migration.py.
"""

import os
import re
import json
import shutil
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy import text

from config.settings import Config, DATA_DIR

logger = logging.getLogger(__name__)

UCM_ENV_PATH = Path("/etc/ucm/ucm.env")
BACKUP_DIR = DATA_DIR / "backups" / "db_migration"


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
