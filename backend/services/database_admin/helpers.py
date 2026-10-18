"""
Database Admin — shared helpers and constants.
Used by status.py, persistence.py, and migration.py.

"""

import os
import re
import json
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from sqlalchemy import (
    column as sa_column,
    func,
    select,
    table as sa_table,
    text,
)
from sqlalchemy.engine import make_url

import fips_mode
from config.settings import Config, DATA_DIR

logger = logging.getLogger(__name__)

UCM_ENV_PATH = Path("/etc/ucm/ucm.env")
BACKUP_DIR = DATA_DIR / "backups" / "db_migration"

# Pre-migration snapshots are never pruned by user-facing backup retention;
# without a cap they accumulate unbounded. Keep the N most recent
# (override with UCM_DB_MIGRATION_KEEP).
try:
    DB_MIGRATION_KEEP = max(1, int(os.environ.get("UCM_DB_MIGRATION_KEEP", "5")))
except ValueError:
    DB_MIGRATION_KEEP = 5

# Shared empty set for the row-normalisation hot path: avoids allocating a new
# set per row when a table has no JSON/BOOLEAN columns.
_EMPTY_COLS = frozenset()

# DB URI credentials. Greedy match to the LAST '@' in the authority so an
# un-encoded '@' inside a password cannot leave a fragment behind. The user
# part may be empty (postgresql://:secret@host/db is a valid URI).
_URI_CRED_RE = re.compile(r"://([^:/?#@]*):[^/?#\s]*@")

# libpq also accepts the password as a query parameter, spelled password,
# passwd, pwd or sslpassword (the client key's passphrase), which the
# authority pattern above does not cover.
_URI_QUERY_PASSWORD_RE = re.compile(
    r"(?i)([A-Za-z0-9_]*(?:password|passwd|pwd))=[^&\s]*"
)

# setval()'s regclass argument as a constant. The cast is spelled out rather
# than imported from sqlalchemy.dialects.postgresql so this module stays
# backend-neutral at import time (loads on every startup, including SQLite).
_SEQ_REGCLASS_ARG = text("CAST(:seq AS regclass)")

# Serial columns + owning sequence in one round trip. Sequence name resolved
# server-side; table/schema quoted by quote_ident() so no metadata is
# concatenated into SQL on the Python side. pg_get_serial_sequence() lower-cases
# its first argument (SQL identifier rules) but treats the column name literally.
_PG_SERIAL_COLUMNS_SQL = text(
    "SELECT table_schema, table_name, column_name, "
    "       pg_get_serial_sequence("
    "           quote_ident(CAST(table_schema AS text)) || '.' || "
    "           quote_ident(CAST(table_name AS text)), "
    "           CAST(column_name AS text)"
    "       ) AS sequence_name "
    "FROM information_schema.columns "
    "WHERE table_schema = 'public' AND column_default LIKE 'nextval%'"
)


def _restrict(path: Path) -> None:
    """Best-effort owner-only permissions on a raw DB copy."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _reserve(path: Path) -> None:
    """Claim a snapshot filename, or raise because someone else has it.

    Two migrations starting in the same second used to compute the same
    timestamped name, and the second one would write over the first one's
    rollback artefact. The name now carries a UUID, and it is still created
    with ``O_EXCL`` rather than merely assumed free: exclusive creation is
    what makes the claim, a unique-looking name is only what makes the claim
    succeed.
    """
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)


def _discard(path: Path) -> None:
    """Remove a failed/partial backup artefact.

    A truncated dump that looks like a valid restore point is worse than no
    dump at all, and it still counts against the retention cap.
    """
    try:
        path.unlink()
    except OSError:
        pass


def _set_env_or_remove(env: dict, key: str, value) -> None:
    """Set an environment variable when *value* is non-empty; otherwise remove it."""
    if isinstance(value, (tuple, list)):
        value = value[-1] if value else None

    if value is not None and str(value) != "":
        env[key] = str(value)
    else:
        env.pop(key, None)


def _prune_db_migration_snapshots(keep: int = DB_MIGRATION_KEEP) -> int:
    """Keep only the ``keep`` most recent pre-migration snapshots. Returns count removed."""
    keep = max(1, keep)  # a keep<=0 caller must never wipe every safety copy
    try:
        snaps = sorted(
            (
                p
                for p in BACKUP_DIR.glob("ucm-*")
                if p.suffix in (".db", ".dump") and p.is_file()
            ),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return 0

    removed = 0
    for path in snaps[keep:]:
        try:
            path.unlink()
            removed += 1
        except OSError:
            continue

    if removed:
        logger.info(
            "Pruned %d old pre-migration DB snapshot(s), kept %d",
            removed,
            keep,
        )
    return removed


def _redact_uri(uri: str) -> str:
    """Hide the password in a DB URI (or in any text that embeds one)."""
    if not uri:
        return uri
    redacted = _URI_CRED_RE.sub(r"://\1:***@", uri)
    return _URI_QUERY_PASSWORD_RE.sub(r"\1=***", redacted)


# An absolute filesystem path of at least two segments. Driver and OS errors
# quote the file they failed on, which is how "/opt/ucm/data/backups/..." and
# "/etc/ucm/ucm.env" end up in an API response and in an audit entry that is
# forwarded to syslog. A single slash ("and/or", "read/write") is left alone.
_ABSOLUTE_PATH_RE = re.compile(r"(?:/[\w.+@-]+){2,}/?")


def _scrub_paths(msg: str) -> str:
    """Reduce absolute paths to their last component.

    The operator needs to know *which file*, not where this installation
    keeps it: the directory layout is the instance's business, and these
    messages travel to callers and to the audit log.
    """
    return _ABSOLUTE_PATH_RE.sub(
        lambda m: m.group(0).rstrip('/').rsplit('/', 1)[-1] or '/', msg)


def _short_err(msg: str, limit: int = 200) -> str:
    """Collapse an error to one short line, without the password or the layout.

    These strings are surfaced to API callers, and driver/engine errors happily
    echo the connection URI they failed on and the file they could not open.
    Redaction runs before truncation so a password cannot survive as a partial
    fragment.
    """
    msg = _scrub_paths(_redact_uri(msg.replace("\n", " ").strip()))
    return msg[:limit] + "..." if len(msg) > limit else msg


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _live_database_url():
    """The URL the application's engine is connected to.

    ``make_url`` is still used for the fallback because it percent-decodes
    credentials, which ``urlparse`` does not: ``p%40ss`` would otherwise
    reach ``pg_dump`` verbatim and fail authentication.
    """
    from models import db as _db

    return _db.engine.url


def _live_sqlite_connection():
    """The sqlite3 connection the application is actually using, if any.

    The snapshot has to be of the database the migration will copy, and that
    is the one the engine is connected to — not whatever the module-level
    configuration says, which a differently-configured application object (or
    a test suite) makes a different database entirely. It is also the only
    way to snapshot a database that has no file at all.
    """
    from models import db as _db

    raw = _db.engine.raw_connection()
    return raw, (getattr(raw, 'driver_connection', None)
                 or getattr(raw, 'connection', None) or raw)


# How long the snapshot waits for the application to finish a write before
# giving up. A migration is a deliberate operation, so waiting a little is
# right; waiting forever, which is what a backup from the application's own
# connection does when that connection is mid-write, is not.
_SQLITE_SNAPSHOT_TIMEOUT = 30.0


def _snapshot_sqlite(src: Optional[Path], dst: Path) -> str:
    """Copy the live SQLite database consistently, or raise.

    sqlite3's online backup API takes a proper read lock, so the copy is a
    transactionally consistent image rather than a set of pages read while
    the application was writing between them. It runs from a second
    connection to the same file: from the application's own connection it
    cannot fail — it *blocks*, forever, whenever that connection is in the
    middle of a write — and a worker stuck there would hold the migration
    lock with it. A database with no file (``:memory:``) has no second
    connection to open, so there the live one is the only choice.

    There is deliberately no fall back to ``shutil.copy2``. This artefact is
    not only the rollback point: on SQLite it is also what the copy reads
    from, so a raw copy of a database being written to would seed the target
    with torn pages, and ``quick_check`` — which validates b-tree structure,
    not rows — would call it sound.

    The import is local by design: a PostgreSQL deployment never reaches this
    branch and must not need ``sqlite3`` merely to import this module.
    """
    import sqlite3

    if src is not None:
        source = sqlite3.connect(str(src), timeout=_SQLITE_SNAPSHOT_TIMEOUT)
        method = 'online backup of the database file'
        close_source = source.close
    else:
        raw, source = _live_sqlite_connection()
        method = 'online backup from the live connection'
        close_source = raw.close

    try:
        target = sqlite3.connect(str(dst))
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        close_source()

    return method


def _backup_current_db(reasons: Optional[list] = None,
                       details: Optional[dict] = None) -> Optional[Path]:
    """Backup current DB before migration. Returns backup path or None.

    ``reasons`` collects one short sentence per failure. Returning None used
    to be the whole story, which left the caller telling an operator that the
    snapshot "could not be taken" while the actual cause — a pg_dump older
    than the server it is dumping, a full disk, a missing binary — sat in a
    log line they had no reason to look for.
    """
    def refuse(message: str) -> None:
        if reasons is not None:
            reasons.append(message)

    def record(**values) -> None:
        if details is not None:
            details.update(values)

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # Raw DB copies hold password hashes and config — owner-only access.
    try:
        os.chmod(BACKUP_DIR, 0o700)
    except OSError:
        pass

    # Sortable for a human reading the directory, unique for two migrations
    # starting within the same second.
    stamp = (
        f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        f"-{uuid.uuid4().hex}"
    )

    # The URL of the database the application is connected to, not the one
    # the module-level configuration names: an application object configured
    # differently — a test suite, a second instance in the same process —
    # would otherwise have a snapshot taken of a database it never reads.
    try:
        url = _live_database_url()
    except Exception as e:
        logger.error("Unusable database URI: %s", _short_err(str(e)))
        refuse(f"the database in use could not be identified ({_short_err(str(e))})")
        return None

    # get_backend_name() strips the driver suffix, so sqlite+pysqlite:// and
    # postgresql+psycopg2:// are classified correctly (unlike startswith()).
    backend = url.get_backend_name()

    if backend == "sqlite":
        # A database with no file of its own is still snapshotted: the online
        # backup runs from the live connection, which is where the data is.
        src = None
        if url.database and url.database != ":memory:":
            src = Path(url.database)
            if not src.exists():
                logger.error("SQLite database file does not exist: %s", src)
                refuse("the SQLite database file named by the configuration "
                       "does not exist")
                return None

        dst = BACKUP_DIR / f"ucm-sqlite-{stamp}.db"
        try:
            # Outside the try below: a name already claimed by another
            # migration must not be discarded as if it were ours.
            _reserve(dst)
        except OSError as e:
            logger.error("Could not claim a snapshot name: %s", _short_err(str(e)))
            refuse(f"the snapshot file could not be created ({_short_err(str(e))})")
            return None

        try:
            record(method=_snapshot_sqlite(src, dst))
            _restrict(dst)
        except OSError as e:
            _discard(dst)
            logger.error("SQLite backup failed: %s", _short_err(str(e)))
            refuse(f"the SQLite online backup failed ({_short_err(str(e))})")
            return None
        except Exception as e:
            _discard(dst)
            logger.error(
                "Unexpected SQLite backup failure: %s",
                _short_err(str(e)),
            )
            refuse(f"the SQLite online backup failed ({_short_err(str(e))})")
            return None

        logger.info("SQLite backup created: %s", dst)
        _prune_db_migration_snapshots()
        return dst

    if backend != "postgresql":
        logger.error("No backup strategy for database backend '%s'", backend)
        refuse(f"there is no snapshot strategy for the '{backend}' backend")
        return None

    output = BACKUP_DIR / f"ucm-pg-{stamp}.dump"

    # Connection details in libpq env vars, not argv: prevents argument injection
    # from values starting with '-'. Empty values are removed (not blanked) so
    # stale PGUSER/PGPASSWORD from the service env cannot silently take effect.
    env = os.environ.copy()

    # Do not default an omitted host to localhost. Leaving PGHOST absent lets
    # libpq use its normal platform default, including Unix sockets.
    for key, value in (
        ("PGHOST", url.host),
        ("PGPORT", url.port),
        ("PGUSER", url.username),
        ("PGDATABASE", url.database),
        ("PGPASSWORD", url.password),
    ):
        _set_env_or_remove(env, key, value)

    # Preserve common libpq options encoded in the SQLAlchemy URI query string.
    libpq_query_options = {
        "sslmode": "PGSSLMODE",
        "sslrootcert": "PGSSLROOTCERT",
        "sslcert": "PGSSLCERT",
        "sslkey": "PGSSLKEY",
        "sslcrl": "PGSSLCRL",
        "sslpassword": "PGSSLPASSWORD",
        "connect_timeout": "PGCONNECT_TIMEOUT",
        "application_name": "PGAPPNAME",
        "options": "PGOPTIONS",
        "target_session_attrs": "PGTARGETSESSIONATTRS",
        "gssencmode": "PGGSSENCMODE",
        "krbsrvname": "PGKRBSRVNAME",
        "service": "PGSERVICE",
    }

    # As in libpq, the URL wins; otherwise the service's own setting, which the
    # live connection uses too, is kept. PGSERVICE is not: its file would
    # override the host and database taken from the URL above.
    for query_key, env_key in libpq_query_options.items():
        if url.query.get(query_key):
            env[env_key] = str(url.query[query_key])
        elif env_key == "PGSERVICE":
            env.pop(env_key, None)
    if fips_mode.requested():
        env['PGGSSENCMODE'] = 'disable'  # GSSAPI encryption runs outside the FIPS module

    cmd = [
        "pg_dump",
        "-F", "c",  # custom format (compressed)
        "-f",
        str(output),
        "--no-password",
    ]

    try:
        _reserve(output)
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            timeout=300,
            check=False,
        )
    except FileExistsError:
        logger.error("A snapshot already claims %s", output.name)
        refuse("the snapshot file could not be created: the name is taken")
        return None
    except FileNotFoundError:
        logger.error("pg_dump not found. Install postgresql-client.")
        _discard(output)
        refuse("pg_dump was not found; install the PostgreSQL client tools")
        return None
    except subprocess.TimeoutExpired:
        logger.error("pg_dump timed out after 300s")
        _discard(output)
        refuse("pg_dump did not finish within 300 seconds")
        return None
    except Exception as e:
        logger.error("PostgreSQL backup failed: %s", _short_err(str(e)))
        _discard(output)
        refuse(f"pg_dump could not be run ({_short_err(str(e))})")
        return None

    if result.returncode != 0:
        stderr = (
            result.stderr.decode(errors="replace")
            if result.stderr
            else "Unknown error"
        )
        logger.error("pg_dump failed: %s", _short_err(stderr))
        _discard(output)
        refuse(f"pg_dump failed: {_short_err(stderr)}")
        return None

    _restrict(output)
    record(method='pg_dump, custom format')
    logger.info("PostgreSQL backup created: %s", output)
    _prune_db_migration_snapshots()
    return output


def _pg_setval_stmt(schema_name: str, table_name: str, column_name: str):
    """Build a safe setval() statement for one serial column.

    Identifiers go to SQLAlchemy as identifiers (not string interpolation), so
    the compiler handles dialect quoting and paramstyle escaping. The table is
    schema-qualified to prevent search_path redirection of MAX().

    For empty tables, ``is_called=False`` makes nextval() return 1 instead of
    incorrectly returning 2.
    """
    col = sa_column(column_name)
    tbl = sa_table(table_name, col, schema=schema_name)

    max_value = select(func.max(col)).select_from(tbl).scalar_subquery()
    sequence_value = func.coalesce(max_value, 1)
    has_existing_rows = max_value.is_not(None)

    # setval()'s regclass arg arrives as a bound parameter (data, not SQL).
    # The explicit CAST keeps it safe for drivers that send str as a typed
    # text parameter. This is a constant fragment — nothing is interpolated.
    return select(
        func.setval(
            _SEQ_REGCLASS_ARG,
            sequence_value,
            has_existing_rows,
        )
    )


def _reset_pg_sequences(engine) -> None:
    """Reset PG sequences after data load so new inserts don't collide.

    SECURITY: no metadata is concatenated into SQL — see
    ``_PG_SERIAL_COLUMNS_SQL`` (server-side quote_ident) and
    ``_pg_setval_stmt`` (compiler-rendered identifiers + bound sequence name).

    No ``^[A-Za-z_]\\w*$`` allowlist: legal PG identifiers need not match it,
    and pg_get_serial_sequence() returns already-quoted names (e.g.
    ``public."My Table_id_seq"``) that fail the regex and would be corrupted
    by splitting on '.', leaving sequences unreset → duplicate-key errors.

    Each reset runs in its own SAVEPOINT: a single failed PG statement aborts
    the whole transaction, so without isolation one failure cascades to all.
    """
    with engine.begin() as conn:
        rows = conn.execute(_PG_SERIAL_COLUMNS_SQL).fetchall()

        for schema_name, table_name, column_name, sequence_name in rows:
            if not sequence_name:
                continue  # nextval() default but no sequence owned by the column

            try:
                with conn.begin_nested():
                    conn.execute(
                        _pg_setval_stmt(schema_name, table_name, column_name),
                        {"seq": sequence_name},
                    )
            except Exception as e:
                logger.warning(
                    "Failed to reset sequence for %s.%s: %s",
                    table_name,
                    column_name,
                    _short_err(str(e)),
                )


def _is_json_text(value: str) -> bool:
    """True if *value* is already a JSON document/scalar."""
    try:
        json.loads(value)
    except (TypeError, ValueError):
        return False
    return True


def _normalize_row(
    row: dict,
    source_is_pg: bool,
    target_is_pg: bool,
    target_json_cols: Optional[set] = None,
    target_bool_cols: Optional[set] = None,
) -> dict:
    """Normalize values for cross-backend insert.

    - PG → SQLite: dict/list → JSON strings; memoryview → bytes; bools → int.
    - SQLite → PG: JSON/JSONB columns get parsed values (not raw text, which PG
      rejects). BOOLEAN columns get real bools (SQLite stores 0/1 ints, and
      psycopg2 refuses int into BOOLEAN).
    """
    json_cols = target_json_cols or _EMPTY_COLS
    bool_cols = target_bool_cols or _EMPTY_COLS
    # Hoist row-invariant checks out of the per-column loop (hot path:
    # every row of every table in a migration).
    coerce_bools = target_is_pg and not source_is_pg and bool(bool_cols)
    encode_json = target_is_pg and bool(json_cols)

    out = {}
    for k, v in row.items():
        if v is None:
            out[k] = None

        elif isinstance(v, memoryview):
            out[k] = bytes(v)

        elif isinstance(v, (dict, list)) and not target_is_pg:
            out[k] = json.dumps(v)

        elif coerce_bools and k in bool_cols and not isinstance(v, bool):
            # SQLite stores bools as INTEGER 0/1. Coerce only 0→False, 1→True;
            # leave invalid values (2, -1, 0.5) for DB validation.
            if isinstance(v, (int, float)):
                if v in (0, 0.0):
                    out[k] = False
                elif v in (1, 1.0):
                    out[k] = True
                else:
                    out[k] = v

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

        elif encode_json and k in json_cols:
            # PG json/jsonb: always send JSON-encoded text.
            # - dict/list → encode (psycopg2 would send a list as PG ARRAY).
            # - "" → NULL. SQLite happily stores an empty string where the
            #   model declares JSON; PG has no such value, and '""' (a JSON
            #   string) would be a different thing from "no document". The
            #   distinction between '' and NULL does not survive, and that is
            #   the closest of the two.
            # - str → pass if valid JSON, else wrap (bare text in a JSON column
            #   is rejected by PG and aborts the entire migration).
            if isinstance(v, (dict, list)):
                out[k] = json.dumps(v)
            elif isinstance(v, str):
                if v == "":
                    out[k] = None
                elif _is_json_text(v):
                    out[k] = v
                else:
                    out[k] = json.dumps(v)
            else:
                out[k] = json.dumps(v)

        else:
            out[k] = v

    return out


def _force_register_all_models() -> None:
    """Import every model module so db.metadata.create_all sees all tables.

    Some modules register lazily (only when their feature runs), so create_all
    on a fresh target would silently miss their tables.
    """
    try:
        # Importing triggers SQLAlchemy registration via class definitions.
        import models  # noqa: F401
        from models import (  # noqa: F401
            acme_models,
            api_key,
            auth_certificate,
            certificate_template,
            crl,
            discovered_certificate,
            email_notification,
            group,
            hsm,
            msca,
            ocsp,
            policy,
            rbac,
            ssh,
            sso,
            truststore,
            webauthn,
        )
    except Exception as e:
        logger.warning(
            "Some core models failed to import: %s",
            _short_err(str(e)),
        )

    # Service-owned tables (lazy-registered)
    for mod in (
        "services.webhook_service",
        "services.notification_service",
    ):
        try:
            __import__(mod)
        except Exception as e:
            logger.debug(
                "Optional model module %s not loaded: %s",
                mod,
                _short_err(str(e)),
            )


def _detect_columns_by_type(
    insp, table_names, matches: Callable[[str], bool]
) -> dict:
    """Return {table: {col_name, ...}} for columns whose rendered type matches.

    A table whose reflection fails is skipped rather than failing the caller.
    """
    out = {}

    for t in table_names:
        try:
            cols = {
                col["name"]
                for col in insp.get_columns(t)
                if matches(str(col.get("type", "")).upper())
            }
        except Exception:
            continue

        if cols:
            out[t] = cols

    return out


def _detect_json_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for columns whose SQL type is JSON/JSONB."""
    # "JSON" as a substring matches both JSON and JSONB.
    return _detect_columns_by_type(insp, table_names, lambda t: "JSON" in t)


def _detect_boolean_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for BOOLEAN/BOOL columns.

    Needed for SQLite → PG: SQLite stores bools as INTEGER, but psycopg2
    refuses int into BOOLEAN. Detected up-front, coerced in _normalize_row.
    """
    # Exact match only — TINYINT/SMALLINT are integers in SQLite even when
    # SQLAlchemy maps them to Boolean.
    return _detect_columns_by_type(
        insp,
        table_names,
        lambda t: t in ("BOOLEAN", "BOOL"),
    )


def _sqlite_dbapi_connection(conn):
    """Return the underlying sqlite3 connection for a SQLAlchemy Connection."""
    connection_fairy = conn.connection
    return (
        getattr(connection_fairy, "driver_connection", None)
        or connection_fairy.connection
    )


def _try_disable_fks(conn, target_is_pg: bool) -> bool:
    """Disable FK checks for bulk load. Returns True if successful.

    PostgreSQL: ``SET LOCAL session_replication_role`` requires SUPERUSER (or
    an explicit ``GRANT SET ON PARAMETER`` on PG 15+); a non-superuser role
    fails and falls back to topological insert order. ``SET LOCAL`` (not
    ``SET``) scopes to the current transaction, preventing leakage into pooled
    connections after commit.

    The statement runs inside a SAVEPOINT: a refused SET puts the whole
    transaction in the failed state (InFailedSqlTransaction, #126), and
    rolling back the *connection* to clear it closes the context-managed
    transaction opened by ``engine.begin()`` (SQLAlchemy 2.x then refuses
    every later statement with "Can't operate on closed transaction inside
    context manager", #305). Rolling back only the savepoint keeps the
    enclosing bulk-load transaction usable. ``SET LOCAL`` issued inside a
    released savepoint stays in effect until the transaction ends.

    SQLite: ``PRAGMA foreign_keys`` cannot be changed inside an active
    transaction — call this before opening the data-load transaction.
    """
    try:
        if target_is_pg:
            with conn.begin_nested():
                conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
            return True

        dbapi_conn = _sqlite_dbapi_connection(conn)

        if dbapi_conn.in_transaction:
            logger.warning(
                "Could not disable SQLite FK checks: an SQLite transaction is "
                "already active. Disable FKs before starting the bulk-load "
                "transaction."
            )
            return False

        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = OFF")
            cursor.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]
        finally:
            cursor.close()

        if enabled:
            logger.warning(
                "Could not disable SQLite FK checks; PRAGMA remained enabled."
            )
            return False

        return True

    except Exception as e:
        logger.warning(
            "Could not disable FK checks (%s); "
            "falling back to topological insert order.",
            _short_err(str(e)),
        )
        return False


def _try_reenable_fks(conn, target_is_pg: bool, was_disabled: bool) -> None:
    """Restore FK enforcement after bulk load.

    For SQLite, call after committing/rolling back the bulk-load transaction.
    Also runs ``foreign_key_check`` once FKs are re-enabled.
    """
    if not was_disabled:
        return

    try:
        if target_is_pg:
            # SET LOCAL resets at transaction end; this restores FK triggers
            # for the remaining transaction.
            conn.execute(text("SET LOCAL session_replication_role = 'origin'"))
            return

        dbapi_conn = _sqlite_dbapi_connection(conn)

        if dbapi_conn.in_transaction:
            logger.warning(
                "Could not re-enable SQLite FK checks: an SQLite transaction "
                "is still active. Re-enable FKs after committing the bulk-load "
                "transaction."
            )
            return

        cursor = dbapi_conn.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys = ON")
            cursor.execute("PRAGMA foreign_keys")
            enabled = cursor.fetchone()[0]

            if not enabled:
                logger.warning(
                    "Could not re-enable SQLite FK checks; PRAGMA remained disabled."
                )
                return

            cursor.execute("PRAGMA foreign_key_check")
            violations = cursor.fetchall()
        finally:
            cursor.close()

        if violations:
            logger.error(
                "SQLite foreign_key_check found %d FK violation(s) after migration.",
                len(violations),
            )

    except Exception as e:
        logger.warning(
            "Could not re-enable FK checks: %s",
            _short_err(str(e)),
        )


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
                # Cycle detected — append the rest in alpha order.
                ordered.extend(sorted(remaining.keys()))
                break

            ready_set = set(ready)  # built once, not once per remaining table
            ordered.extend(ready)

            for t in ready:
                remaining.pop(t)

            for pending_deps in remaining.values():
                pending_deps -= ready_set

        return ordered

    except Exception as e:
        logger.warning(
            "Topo sort failed (%s); using alphabetical order.",
            _short_err(str(e)),
        )
        return sorted(insp.get_table_names())

