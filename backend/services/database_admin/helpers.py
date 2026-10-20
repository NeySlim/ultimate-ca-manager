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
from pathlib import Path
from typing import Optional

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
        # Core model packages — importing the package triggers SQLAlchemy
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


# PLANB-D.8: à implémenter selon SPEC
def _discard(path) -> None:
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _prune_db_migration_snapshots(keep: int = DB_MIGRATION_KEEP) -> int:
    """Keep only the ``keep`` most recent pre-migration snapshots. Returns count removed."""
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _backup_current_db(reasons: Optional[list] = None,
                       details: Optional[dict] = None) -> Optional[Path]:
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _pg_setval_stmt(schema_name, table_name, column_name):
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _reset_pg_sequences(engine):
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _normalize_row(row: dict, source_is_pg: bool, target_is_pg: bool,
                   target_json_cols: Optional[set] = None, target_bool_cols: Optional[set] = None) -> dict:
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _detect_json_columns(insp, table_names) -> dict:
    """Return {table: {col_name, ...}} for columns whose SQL type is JSON/JSONB."""
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _detect_boolean_columns(insp, table_names) -> dict:
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
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
    """
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _try_reenable_fks(conn, target_is_pg: bool, was_disabled: bool) -> None:
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC
def _topo_sort_tables(insp) -> list:
    """Return table names in FK-dependency order (parents first).

    Falls back to alphabetical on any error so a sort failure doesn't
    abort the whole migration.
    """
    raise NotImplementedError('PLANB-D.8')
# PLANB-D.8: à implémenter selon SPEC (colonnes à séquence du schéma public)
_PG_SERIAL_COLUMNS_SQL = None
def _apply_libpq_options(env: dict, url, libpq_query_options: dict) -> None:
    # PLANB-D.8: appelée par _backup_current_db avec la table des options libpq (voir SPEC)
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
