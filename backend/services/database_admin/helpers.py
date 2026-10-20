"""
Database Admin — shared helpers and constants.
Used by status.py, persistence.py, and migration.py.
"""

import os
import re
import json
import logging
import shutil
import sqlite3
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from sqlalchemy import Text, bindparam, cast, event, func, select, text
from sqlalchemy import column as sa_column, table as sa_table
from sqlalchemy.dialects.postgresql import REGCLASS
from sqlalchemy.pool import Pool
from sqlalchemy.sql import sqltypes

import fips_mode
from config.settings import Config, DATA_DIR

logger = logging.getLogger(__name__)

UCM_ENV_PATH = Path("/etc/ucm/ucm.env")
BACKUP_DIR = DATA_DIR / "backups" / "db_migration"

try:
    DB_MIGRATION_KEEP = max(1, int(os.environ.get("UCM_DB_MIGRATION_KEEP", "5")))
except ValueError:
    DB_MIGRATION_KEEP = 5

# Credentials of a DB URI, matched up to the last '@' of the authority so an
# un-encoded '@' inside a password cannot leave a fragment behind. The user
# part may be empty (postgresql://:secret@host/db is a valid URI).
_URI_CRED_RE = re.compile(r"://([^:/?#@]*):[^/?#\s]*@")
# libpq also accepts the password as a query parameter, spelled password,
# passwd, pwd or sslpassword (the client key's passphrase), which the
# authority pattern above does not cover.
_URI_QUERY_PASSWORD_RE = re.compile(
    r"(?i)([A-Za-z0-9_]*(?:password|passwd|pwd))=[^&\s]*"
)

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


def _redact_uri(uri: str) -> str:
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
    """Collapse an error to one short line, without the password or the layout."""
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


def _force_register_all_models() -> None:
    """Import every model module so db.metadata.create_all sees all tables.

    Some modules are registered lazily (only when their feature runs) which
    means create_all on a fresh target would silently miss their tables.
    """
    try:
        # Core model packages: importing the package triggers SQLAlchemy
        # registration via class definitions.
        import models  # noqa: F401
        from models import (  # noqa: F401
            acme_models, api_key, auth_certificate, certificate_template,
            crl, discovered_certificate, email_notification, group, hsm,
            msca, ocsp, policy, rbac, ssh, sso, truststore, webauthn,
        )
    except Exception as e:
        logger.warning("Some core models failed to import: %s", _short_err(str(e)))

    # Service-owned tables (lazy-registered)
    for mod in (
        "services.webhook_service",
        "services.notification_service",
    ):
        try:
            __import__(mod)
        except Exception as e:
            logger.debug("Optional model module %s not loaded: %s", mod, _short_err(str(e)))




def _discard(path) -> None:
    """Remove a file of ours if it is there; never raise."""
    if not path:
        return
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    except OSError as e:
        logger.warning("Could not remove %s: %s", Path(path).name, _short_err(str(e)))


def _snapshot_files() -> list:
    directory = Path(BACKUP_DIR)
    if not directory.is_dir():
        return []
    found = []
    for pattern in ("ucm-*.db", "ucm-*.dump"):
        found.extend(p for p in directory.glob(pattern)
                     if p.is_file() and not p.is_symlink())
    return found


def _prune_db_migration_snapshots(keep: int = DB_MIGRATION_KEEP) -> int:
    """Keep only the ``keep`` most recent pre-migration snapshots. Returns count removed."""
    try:
        keep = max(1, int(keep))
    except (TypeError, ValueError):
        keep = 5

    def _mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    removed = 0
    for old in sorted(_snapshot_files(), key=_mtime, reverse=True)[keep:]:
        try:
            old.unlink()
            removed += 1
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Could not prune snapshot %s: %s", old.name, _short_err(str(e)))
    if removed:
        logger.info("Pruned %d pre-migration snapshot(s), keeping %d", removed, keep)
    return removed


# URL query option -> libpq environment variable, passed to pg_dump.
# libpq has no variable for sslpassword: PGSSLPASSWORD is set for the
# contract but ignored by libpq, and the passphrase never goes to argv.
_LIBPQ_QUERY_OPTIONS = {
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

# URL attribute -> libpq variable; absent from the URL means absent from
# pg_dump's environment, so nothing inherited is used behind the caller's back.
_PG_CONNECTION_ENV = (
    ("host", "PGHOST"),
    ("port", "PGPORT"),
    ("username", "PGUSER"),
    ("database", "PGDATABASE"),
    ("password", "PGPASSWORD"),
)

_PG_DUMP_TIMEOUT = 3600


def _pg_dump_env(url) -> dict:
    """Environment for pg_dump: every connection setting as a PG* variable."""
    env = dict(os.environ)
    for attr, var in _PG_CONNECTION_ENV:
        value = getattr(url, attr, None)
        if attr == "host" and not value:
            # psycopg2 URLs may carry a socket directory as ?host=
            query_host = url.query.get("host")
            value = query_host if isinstance(query_host, str) else None
        if value is None or value == "":
            env.pop(var, None)
        else:
            # make_url has already percent-decoded the password.
            env[var] = str(value)
    _apply_libpq_options(env, url, _LIBPQ_QUERY_OPTIONS)
    return env


def _dump_postgresql(url, path: Path, reasons: list, details: dict) -> bool:
    details["method"] = "pg_dump, custom format"
    binary = shutil.which("pg_dump") or "pg_dump"
    cmd = [binary, "--no-password", "-F", "c", f"--file={path}"]
    try:
        result = subprocess.run(cmd, env=_pg_dump_env(url), capture_output=True,
                                timeout=_PG_DUMP_TIMEOUT, check=False)
    except FileNotFoundError:
        reasons.append("pg_dump is not installed; install the PostgreSQL client tools")
        return False
    except subprocess.TimeoutExpired:
        reasons.append(f"pg_dump did not finish within {_PG_DUMP_TIMEOUT} seconds")
        return False
    except OSError as e:
        reasons.append(f"pg_dump could not be started: {_short_err(str(e))}")
        return False
    if result.returncode != 0:
        stderr = result.stderr or b""
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        reasons.append(f"pg_dump failed: {_short_err(stderr) or 'no error output'}")
        return False
    return True


def _is_memory_sqlite(url) -> bool:
    database = url.database or ""
    if database in ("", ":memory:"):
        return True
    return database.startswith("file:") and (
        database.startswith("file::memory:") or "mode=memory" in database)


def _sqlite_backup(source, target) -> None:
    """Online backup in one step, giving up once a writer held it too long."""
    deadline = time.monotonic() + _SQLITE_SNAPSHOT_TIMEOUT

    def _progress(status, remaining, total):
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"the database stayed locked by a writer for more than "
                f"{_SQLITE_SNAPSHOT_TIMEOUT:g} seconds")

    source.backup(target, pages=-1, progress=_progress, sleep=0.1)


def _dump_sqlite(url, path: Path, reasons: list, details: dict) -> bool:
    """Copy the live SQLite database with the online backup API, never a file copy."""
    target = None
    raw = source = None
    try:
        if _is_memory_sqlite(url):
            details["method"] = "online backup from the live connection"
            raw, source = _live_sqlite_connection()
        else:
            details["method"] = "online backup of the database file"
            database = url.database
            if str(url.query.get("uri", "")).lower() in ("true", "1"):
                source = sqlite3.connect(database, uri=True,
                                         timeout=_SQLITE_SNAPSHOT_TIMEOUT)
            else:
                # mode=rw opens the existing file and never creates an empty one.
                uri = f"file:{quote(os.path.abspath(database))}?mode=rw"
                source = sqlite3.connect(uri, uri=True,
                                         timeout=_SQLITE_SNAPSHOT_TIMEOUT)
        target = sqlite3.connect(str(path))
        _sqlite_backup(source, target)
        return True
    except Exception as e:
        reasons.append(f"the SQLite online backup failed: {_short_err(str(e))}")
        return False
    finally:
        if target is not None:
            target.close()
        if raw is not None:
            raw.close()
        elif source is not None:
            source.close()


def _backup_current_db(reasons: Optional[list] = None,
                       details: Optional[dict] = None) -> Optional[Path]:
    """Snapshot the database the application is connected to before a migration.

    Returns the artefact, or None with a short sentence appended to ``reasons``.
    """
    reasons = reasons if reasons is not None else []
    details = details if details is not None else {}

    try:
        url = _live_database_url()
        backend = url.get_backend_name()
    except Exception as e:
        reasons.append(f"the database in use could not be identified: {_short_err(str(e))}")
        return None

    if backend == "sqlite":
        kind, suffix, dump = "sqlite", "db", _dump_sqlite
        if not _is_memory_sqlite(url) and not str(url.database).startswith("file:") \
                and not os.path.exists(url.database):
            reasons.append("the SQLite database file does not exist, nothing to snapshot")
            return None
    elif backend.startswith("postgres"):
        kind, suffix, dump = "pg", "dump", _dump_postgresql
    else:
        reasons.append(f"no snapshot method for the '{backend}' backend")
        return None

    directory = Path(BACKUP_DIR)
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(directory, 0o700)
    except OSError as e:
        reasons.append(f"the snapshot directory is not usable: {_short_err(str(e))}")
        return None

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    path = directory / f"ucm-{kind}-{stamp}-{uuid.uuid4().hex}.{suffix}"
    try:
        _reserve(path)
    except FileExistsError:
        # Someone else's artefact: never removed from here.
        reasons.append("the snapshot name is already taken by another migration")
        return None
    except OSError as e:
        reasons.append(f"the snapshot file could not be created: {_short_err(str(e))}")
        return None

    try:
        ok = dump(url, path, reasons, details)
    except Exception as e:
        reasons.append(f"the snapshot failed: {_short_err(str(e))}")
        ok = False
    if not ok:
        logger.error("Pre-migration snapshot failed: %s", reasons[-1] if reasons else "unknown")
        for leftover in (path, Path(f"{path}-journal"), Path(f"{path}-wal")):
            _discard(leftover)
        return None

    try:
        os.chmod(path, 0o600)
    except OSError as e:
        logger.warning("Could not restrict %s: %s", path.name, _short_err(str(e)))

    try:
        _prune_db_migration_snapshots(DB_MIGRATION_KEEP)
    except Exception as e:
        logger.warning("Snapshot pruning failed: %s", _short_err(str(e)))

    logger.info("Pre-migration snapshot written: %s (%s)", path.name, details.get("method"))
    return path


# Columns of the public schema whose default is nextval(), with the sequence
# the column owns (NULL when it owns none). The catalogue quotes the table
# name itself, so no metadata is concatenated on the Python side.
_PG_SERIAL_COLUMNS_SQL = text(
    "SELECT c.table_schema, c.table_name, c.column_name, "
    "pg_get_serial_sequence("
    "quote_ident(c.table_schema) || '.' || quote_ident(c.table_name), "
    "c.column_name) AS sequence_name "
    "FROM information_schema.columns AS c "
    "JOIN information_schema.tables AS t "
    "ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
    "WHERE c.table_schema = 'public' AND t.table_type = 'BASE TABLE' "
    "AND strpos(c.column_default, 'nextval(') = 1 "
    "ORDER BY c.table_name, c.column_name"
)


def _pg_setval_stmt(schema_name, table_name, column_name):
    """setval() for one serial column; the sequence is the bound parameter ``seq``.

    Identifiers are rendered by the dialect. An empty table sets is_called to
    false, so the next nextval() returns 1; otherwise it returns MAX + 1.
    """
    col = sa_column(column_name)
    tbl = sa_table(table_name, col, schema=schema_name)
    highest = func.max(col)
    return select(func.setval(
        cast(bindparam("seq", type_=Text()), REGCLASS),
        func.coalesce(highest, 1),
        highest.isnot(None),
    )).select_from(tbl)


def _reset_pg_sequences(engine):
    """Realign every serial sequence of the public schema on its table's data."""
    if not str(getattr(engine.dialect, "name", "")).startswith("postgres"):
        return
    done = failed = 0
    with engine.begin() as conn:
        try:
            with conn.begin_nested():
                rows = conn.execute(_PG_SERIAL_COLUMNS_SQL).fetchall()
        except Exception as e:
            logger.warning("Could not list the serial columns: %s", _short_err(str(e)))
            return
        for schema_name, table_name, column_name, sequence_name in rows:
            if not sequence_name:
                logger.debug("%s.%s calls a sequence it does not own; skipped",
                             table_name, column_name)
                continue
            try:
                # One savepoint each: a refused setval() leaves the others intact.
                with conn.begin_nested():
                    conn.execute(_pg_setval_stmt(schema_name, table_name, column_name),
                                 {"seq": sequence_name})
                done += 1
            except Exception as e:
                failed += 1
                logger.warning("Could not reset the sequence of %s.%s: %s",
                               table_name, column_name, _short_err(str(e)))
    logger.info("Reset %d PostgreSQL sequence(s), %d failed", done, failed)


def _type_name(col_type) -> str:
    name = getattr(col_type, "__visit_name__", None) or type(col_type).__name__
    return str(name).split("(", 1)[0].strip().upper()


def _detect_columns_by_type(insp, table_names, matches) -> dict:
    """Return {table: {col_name, ...}} for columns whose reflected type ``matches``."""
    found = {}
    for table in table_names:
        try:
            columns = insp.get_columns(table)
        except Exception as e:
            logger.warning("Could not reflect %s, its columns are not converted: %s",
                           table, _short_err(str(e)))
            continue
        names = {c["name"] for c in columns if c.get("type") is not None and matches(c["type"])}
        if names:
            found[table] = names
    return found


def _detect_json_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for columns whose SQL type is JSON/JSONB."""
    return _detect_columns_by_type(
        insp, table_names,
        lambda t: isinstance(t, sqltypes.JSON) or _type_name(t) in ("JSON", "JSONB"))


def _detect_boolean_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for BOOLEAN/BOOL columns, never small integers."""
    return _detect_columns_by_type(
        insp, table_names,
        lambda t: isinstance(t, sqltypes.Boolean) or _type_name(t) in ("BOOLEAN", "BOOL"))


_TRUE_STRINGS = frozenset(("1", "true", "t", "yes", "y", "on"))
_FALSE_STRINGS = frozenset(("0", "false", "f", "no", "n", "off", ""))


def _to_bool(value):
    """Convert 0/1 and recognised strings; any other value is left to the database."""
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value) if value in (0, 1) else value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode(errors="replace")
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _TRUE_STRINGS:
            return True
        if lowered in _FALSE_STRINGS:
            return False
    # Anything else is left for the target to refuse loudly.
    return value


def _to_json_text(value):
    # SQLite holds '' where the model declares JSON: that is NULL, not a JSON string.
    if value is None or value == "":
        return None
    if isinstance(value, str):
        try:
            json.loads(value)
            return value
        except ValueError:
            # Raw text in a JSON column is a JSON string, not a parse error.
            return json.dumps(value)
    return json.dumps(value)


def _normalize_row(row: dict, source_is_pg: bool, target_is_pg: bool,
                   target_json_cols: Optional[set] = None, target_bool_cols: Optional[set] = None) -> dict:
    """Adapt one row's JSON, binary and boolean values to the target dialect."""
    json_cols = target_json_cols or ()
    bool_cols = target_bool_cols or ()
    out = {}
    for key, value in row.items():
        if isinstance(value, memoryview):
            value = value.tobytes()
        if target_is_pg:
            if key in json_cols:
                value = _to_json_text(value)
            elif key in bool_cols:
                value = _to_bool(value)
        elif isinstance(value, (dict, list)):
            # SQLite has no JSON type: it stores the text.
            value = json.dumps(value)
        out[key] = value
    return out


_FKS_DISABLED_KEY = "ucm_fks_disabled"


def _restore_sqlite_fks(dbapi_conn, record) -> None:
    """Pool check-in: a connection never goes back with its checks still off."""
    if record.info.pop(_FKS_DISABLED_KEY, False):
        try:
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
        except Exception as e:
            logger.warning("Could not re-enable SQLite foreign keys: %s", _short_err(str(e)))


# Registered once on the Pool class: a per-pool listener can be skipped when a
# disposed pool's id is reused, since the event registry is keyed by id().
event.listen(Pool, "checkin", _restore_sqlite_fks)


def _try_disable_fks(conn, target_is_pg: bool) -> bool:
    """Disable FK checks for bulk load. Returns True if successful.

    PostgreSQL: ``SET LOCAL session_replication_role`` needs SUPERUSER (or
    ``GRANT SET ON PARAMETER``); it runs in its own SAVEPOINT so a refusal
    leaves the enclosing load transaction usable, and topological order remains.
    SQLite: the PRAGMA is a no-op inside a transaction, so it must come first.
    """
    if target_is_pg:
        try:
            with conn.begin_nested():
                conn.execute(text("SET LOCAL session_replication_role = 'replica'"))
            return True
        except Exception as e:
            logger.info("Foreign keys stay enforced, loading in dependency order: %s",
                        _short_err(str(e)))
            return False

    try:
        dbapi_conn = conn.connection.dbapi_connection
        if conn.in_transaction() or getattr(dbapi_conn, "in_transaction", False):
            return False
        dbapi_conn.execute("PRAGMA foreign_keys=OFF")
        state = dbapi_conn.execute("PRAGMA foreign_keys").fetchone()
    except Exception as e:
        logger.info("Could not disable SQLite foreign keys: %s", _short_err(str(e)))
        return False
    if not state or state[0]:
        return False
    conn.connection.info[_FKS_DISABLED_KEY] = True
    return True


def _try_reenable_fks(conn, target_is_pg: bool, was_disabled: bool) -> None:
    """Undo ``_try_disable_fks``; on SQLite, report what ``foreign_key_check`` finds."""
    if not was_disabled:
        return
    if target_is_pg:
        try:
            with conn.begin_nested():
                conn.execute(text("SET LOCAL session_replication_role = 'origin'"))
        except Exception as e:
            logger.warning("Could not restore session_replication_role: %s", _short_err(str(e)))
        return

    try:
        dbapi_conn = conn.connection.dbapi_connection
        dbapi_conn.execute("PRAGMA foreign_keys=ON")
        conn.connection.info.pop(_FKS_DISABLED_KEY, None)
        violations = dbapi_conn.execute("PRAGMA foreign_key_check").fetchall()
    except Exception as e:
        logger.warning("Could not re-enable SQLite foreign keys: %s", _short_err(str(e)))
        return
    if violations:
        tables = sorted({str(v[0]) for v in violations})
        logger.warning("foreign_key_check found %d violation(s) in: %s",
                       len(violations), ", ".join(tables[:10]))


def _topo_sort_tables(insp) -> list:
    """Return table names in FK-dependency order (parents first).

    Tables caught in a cycle come last, alphabetically. Falls back to
    alphabetical on any error so a sort failure doesn't abort the migration.
    """
    try:
        names = sorted(insp.get_table_names())
    except Exception as e:
        logger.warning("Could not list tables for ordering: %s", _short_err(str(e)))
        return []
    try:
        known = set(names)
        parents = {}
        for table in names:
            parents[table] = {
                fk.get("referred_table") for fk in insp.get_foreign_keys(table)
                if fk.get("referred_table") in known and fk.get("referred_table") != table
            }
        ordered, placed = [], set()
        while len(ordered) < len(names):
            ready = [t for t in names if t not in placed and parents[t] <= placed]
            if not ready:
                rest = [t for t in names if t not in placed]
                logger.warning("Foreign key cycle among %s; ordered alphabetically", ", ".join(rest))
                ordered.extend(rest)
                break
            ordered.extend(ready)
            placed.update(ready)
        return ordered
    except Exception as e:
        logger.warning("Table ordering failed, using alphabetical order: %s", _short_err(str(e)))
        return names


def _apply_libpq_options(env: dict, url, libpq_query_options: dict) -> None:
    # As in libpq, the URL wins; otherwise the service's own setting, which the
    # live connection uses too, is kept. PGSERVICE is not: its file would
    # override the host and database taken from the URL above.
    for query_key, env_key in dict(libpq_query_options).items():
        if url.query.get(query_key):
            env[env_key] = str(url.query[query_key])
        elif env_key == "PGSERVICE":
            env.pop(env_key, None)
    if fips_mode.requested():
        env['PGGSSENCMODE'] = 'disable'  # GSSAPI encryption runs outside the FIPS module
