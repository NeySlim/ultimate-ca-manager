"""Moving an installation to another database backend, or refusing to.

The sequence is deliberately rigid, and every step is allowed to stop it:

1. the target answers, and holds nothing (``preflight``);
2. the source is whole — nothing in it already breaks its own foreign keys,
   which SQLite never enforced and which PostgreSQL will (``verify``);
3. the source is snapshotted and the snapshot is read back (``snapshot``);
4. the schema is built on the target and checked, column by column;
5. the source is read through one consistent view and streamed over in
   batches (``copy``);
6. what landed is counted, joined, deduplicated and decrypted (``verify``);
7. only then does the caller persist ``ucm.env`` and restart.

What this file no longer does is as important as what it does. It does not
report success with a list of ``skipped`` tables and ``dropped_columns``; it
does not carry on when the snapshot could not be taken; it does not return
before anything has been verified. Each of those was a way for an operator to
be told that a migration had worked when it had not.
"""
import logging
import re
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, inspect, text

from utils.db_url import sqlalchemy_url

from .copy import (
    CopyError,
    consistent_live_source,
    consistent_source,
    copy_tables,
)
from .helpers import (
    _force_register_all_models,
    _reset_pg_sequences,
    _short_err,
    _topo_sort_tables,
)
from .lock import MigrationBusyError, database_migration_lock
from .preflight import (
    LEGACY_COLUMNS,
    PreflightError,
    TablePlan,
    build_copy_plan,
    check_target_is_empty,
    check_target_schema,
    dropped_columns,
)
from .snapshot import SnapshotError, create_source_snapshot
from .status import test_connection
from .verify import (
    VerificationError,
    check_declared_foreign_keys,
    verify_migration,
)

logger = logging.getLogger(__name__)


# Strict SQL identifier shape — letters, digits, underscore; not starting with a
# digit. Anything else is rejected before being interpolated into a query.
# Names returned by SQLAlchemy's inspect() normally satisfy this, but the
# *source* DB during a migration is operator-controlled (could be a malicious
# SQLite file or a hostile PG with crafted catalog entries) and we MUST NOT
# trust it for raw string interpolation into SQL.
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')


def _display(name) -> str:
    """Render a database-supplied name for a message bound for the API.

    Same treatment as ``preflight._display`` and ``verify._display``, for the
    same reason: these names come from an operator-supplied database and can
    carry control characters, quotes or kilobytes of padding. This module was
    the one that still put the raw value in its message.
    """
    cleaned = "".join(
        char if char.isprintable() and char not in '"\\' else "?"
        for char in str(name)
    )
    return cleaned[:64] + "..." if len(cleaned) > 64 else cleaned


def _safe_ident(name: str) -> str:
    """Return *name* if it is a safe SQL identifier, else raise ValueError."""
    if not isinstance(name, str) or not _SAFE_IDENT_RE.match(name):
        raise ValueError(f"Unsafe SQL identifier: {_display(name)!r}")
    return name


# Tables that must be present on a target backend even when an admin switches
# WITHOUT migrating data, so we don't lock everyone out of the new empty DB.
# This is the SET to carry over; the ORDER to insert them in is computed from
# the target's own foreign keys in ``_bootstrap_plan``. It used to be this
# hand-written order, described as "parents before children" while ``users``
# — a child of ``pro_custom_roles`` and ``pro_sso_providers`` — sat first: on
# a PostgreSQL target with a role that cannot disable constraints, which is
# the very case the fallback exists for, a switch from an installation using
# custom roles or SSO died on a foreign key violation.
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


def _migrations_ddl(target_is_pg: bool) -> str:
    """The one table that is not part of the SQLAlchemy metadata.

    The migration runner owns it, so ``create_all`` knows nothing about it,
    and a target without it would re-run every schema migration on first
    boot against data that already has them applied.
    """
    identity = (
        "id SERIAL PRIMARY KEY" if target_is_pg
        else "id INTEGER PRIMARY KEY AUTOINCREMENT"
    )
    return f"""
        CREATE TABLE IF NOT EXISTS _migrations (
            {identity},
            name VARCHAR(255) NOT NULL UNIQUE,
            applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """


def _create_target_schema(target_engine, target_is_pg: bool) -> None:
    """Build the whole schema on the target before a single row is copied."""
    from models import db as _db

    _db.metadata.create_all(target_engine)
    # Its own transaction, so it commits before the bulk load begins: if the
    # copy then fails, the operator still sees a target with a schema rather
    # than one that looks half-created.
    with target_engine.begin() as tx:
        tx.execute(text(_migrations_ddl(target_is_pg)))


def _bootstrap_plan(source_engine, target_engine) -> List[TablePlan]:
    """Which columns of the auth tables are copied by a backend switch.

    Unlike a full migration this is a fixed, ordered list of tables, but the
    same rule applies to their columns: a column present on the source and
    absent from the target is a refusal, not a line in a ``skipped`` list. A
    switch that quietly dropped ``users.totp_secret`` would lock out every
    administrator with MFA enabled.
    """
    source_insp = inspect(source_engine)
    target_insp = inspect(target_engine)
    source_tables = set(source_insp.get_table_names())
    target_tables = set(target_insp.get_table_names())

    # Parents first, decided by the target's constraints: those are the ones
    # that will be enforced when the rows arrive.
    wanted = set(BOOTSTRAP_AUTH_TABLES)
    ordered = [t for t in _topo_sort_tables(target_insp) if t in wanted]
    ordered += [t for t in BOOTSTRAP_AUTH_TABLES if t not in set(ordered)]

    plan: List[TablePlan] = []
    for name in ordered:
        if name not in source_tables:
            raise PreflightError(
                f"Table '{name}' is missing from the current database; "
                "the backend switch was not started.")
        if name not in target_tables:
            raise PreflightError(
                f"Table '{name}' could not be created on the target; "
                "the backend switch was not started.")

        source_cols = [c['name'] for c in source_insp.get_columns(name)]
        target_cols = {c['name'] for c in target_insp.get_columns(name)}
        # The same standing approval a full migration honours: an
        # installation still carries columns the models dropped long ago
        # (`group_members.created_at` is one, and this list copies
        # `group_members`), and the target, built from the models, has
        # nowhere to put them. Anything else missing is a refusal.
        approved = LEGACY_COLUMNS.get(name, {})
        missing = [c for c in source_cols
                   if c not in target_cols and c not in approved]
        if missing:
            raise PreflightError(
                f"Column '{name}.{missing[0]}' has no counterpart on the "
                "target; the backend switch was not started.")

        copied = [c for c in source_cols if c in target_cols]
        unquotable = [c for c in copied if not _SAFE_IDENT_RE.match(c)]
        if unquotable:
            # Filtering it out is how a switch quietly leaves an MFA secret
            # behind: a column that cannot be addressed cannot be copied, and
            # that is a refusal.
            raise PreflightError(
                f"Column '{name}.{unquotable[0]}' is not a plain SQL "
                "identifier, so it cannot be copied safely; the backend "
                "switch was not started.")

        plan.append(TablePlan(name=name, columns=tuple(copied)))

    return plan


def _source_drift(copied: Dict[str, int]) -> Dict[str, int]:
    """How far the live source moved while it was being copied.

    The copy reads a fixed image of the source — a snapshot file on SQLite, a
    ``REPEATABLE READ`` transaction on PostgreSQL — and the verification
    compares the target to what that image held. Both are then in perfect
    agreement about a target that is missing every row written since. On an
    instance still serving requests that is a certificate issued, an audit
    entry, an ACME order: real work, silently left on the old backend.

    Stopping writes for the duration is the operator's decision to make, not
    ours, so this does not refuse anything. It measures the gap and says so,
    which is the one thing nothing else in the pipeline does.
    """
    from models import db as _db

    drift: Dict[str, int] = {}
    try:
        with _db.engine.connect() as conn:
            for table, copied_rows in copied.items():
                try:
                    now = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{_safe_ident(table)}"')
                    ).scalar()
                except Exception:
                    # A table that cannot be counted now says nothing about
                    # what was copied; the copy itself already succeeded.
                    continue
                if now is not None and int(now) != copied_rows:
                    drift[table] = int(now) - copied_rows
    except Exception as exc:
        logger.warning("Could not measure the source drift: %s",
                       _short_err(str(exc)))
    return drift


def _check_source_integrity() -> Dict[str, object]:
    """Refuse to copy a database that already breaks its own foreign keys.

    SQLite enforces no foreign key unless a connection asks it to, and UCM's
    never has, so an installation can carry orphan rows for years without
    anything saying so. Copying them into PostgreSQL produces a database that
    contradicts its own schema — or, with a role that cannot disable the
    constraints, a migration that dies halfway through on a driver error
    naming one row.

    Checked here rather than only after the copy, so that the operator is
    told before an hour of copying, and told about the database it is
    actually true of: their own. It is a check of the source as it stands
    now, not of the snapshot taken a moment later, so it is the fast answer
    rather than the authoritative one — that is ``verify_migration`` on the
    target, which runs on exactly what was copied.
    """
    from models import db as _db

    try:
        # Against the foreign keys the models declare, not the ones this
        # database happens to carry: the target is built from the models, so
        # those are the constraints the data will have to satisfy — including
        # the ones SQLite could never add to a table it had already created.
        return check_declared_foreign_keys(
            _db.engine, side='the current database')
    except VerificationError as exc:
        raise PreflightError(
            f"{exc}. The migration was not started: those rows cannot be "
            "copied into a database that enforces foreign keys. Remove them "
            "(or restore the rows they point at) and retry."
        ) from exc


def _target_has_users(target_engine) -> bool:
    """Whether the target is already a provisioned installation.

    Fail-closed: a target whose ``users`` table cannot be read is treated as
    populated, because bootstrapping over an installation that is already in
    use is the one outcome that has no undo.
    """
    try:
        if 'users' not in inspect(target_engine).get_table_names():
            return False
        with target_engine.connect() as probe:
            row = probe.execute(text('SELECT COUNT(*) FROM "users"')).fetchone()
        return bool(row and row[0])
    except Exception as exc:
        raise PreflightError(
            f"The target's users table could not be read "
            f"({_short_err(str(exc))}); the backend switch was not started.")


def bootstrap_auth_to_target(target_url: str) -> Tuple[bool, str, dict]:
    """
    Copy auth/RBAC/SSO/MFA tables from the current DB to a fresh target so
    admins, custom roles and SSO config survive a `switch_backend` call.

    Used when the user switches backends WITHOUT a full data migration.
    Without this, the new DB has no users → nobody can log in → lockout.

    Safe to call against an empty target. If the target already has any users,
    bootstrap is skipped (we assume the operator manages that DB themselves).

    Every table goes over in **one** transaction. It used to be one
    transaction per table, with each failure appended to a ``skipped`` list
    and the whole thing reported as a success as long as ``users`` alone had
    made it: an administrator could land on a target holding their account
    but none of their group memberships, their custom role or their SSO
    provider — locked out of everything they were not personally granted.
    """
    # Force-load every model module so db.metadata.create_all() sees them.
    # Some modules (webhooks, …) are only imported when their feature runs.
    _force_register_all_models()

    stats: Dict[str, object] = {
        "tables_bootstrapped": 0,
        "rows_copied": 0,
        "tables": {},
        "target_written": False,
    }
    target_engine = None
    try:
        target_engine = create_engine(sqlalchemy_url(target_url), pool_pre_ping=True)
        target_is_pg = target_url.startswith("postgresql")

        if _target_has_users(target_engine):
            return True, "Target already has users; bootstrap skipped.", stats

        # From here on the target carries a schema, which changes what the
        # operator has to do before retrying.
        stats["target_written"] = True
        _create_target_schema(target_engine, target_is_pg)

        with consistent_live_source() as (src, source_view, source_is_pg):
            plan = _bootstrap_plan(src.engine, target_engine)
            result = copy_tables(
                src, target_engine, plan,
                source_is_pg=source_is_pg, target_is_pg=target_is_pg)

        if target_is_pg:
            _reset_pg_sequences(target_engine)

        stats["tables"] = dict(result.tables)
        stats["tables_bootstrapped"] = len(result.tables)
        stats["rows_copied"] = result.rows
        stats["source_view"] = source_view

        if not result.tables.get('users'):
            stats["refusal"] = "verification"
            return (
                False,
                "No user account reached the target: switch aborted to "
                "prevent lockout",
                stats,
            )

        report = verify_migration(
            target_engine, result.tables, target_is_pg=target_is_pg)
        stats["validation"] = report

        return True, "Auth tables bootstrapped to target", stats

    except (PreflightError, CopyError, VerificationError) as exc:
        logger.error("Bootstrap refused: %s", exc)
        stats["refusal"] = _refusal_kind(exc)
        return False, f"Bootstrap failed: {exc}", stats
    except Exception as e:
        logger.exception("bootstrap_auth_to_target failed")
        stats["refusal"] = "error"
        return False, f"Bootstrap failed: {_short_err(str(e))}", stats
    finally:
        if target_engine is not None:
            target_engine.dispose()


def migrate_data(target_url: str) -> Tuple[bool, str, dict]:
    """
    Migrate all data from current backend → target_url.

    Steps, in order, each of which can stop the migration:
      1. the target answers and is empty (no UCM table holds a row, no
         unknown table, no partial UCM table);
      2. the source does not already break its own foreign keys;
      3. the source is snapshotted and the snapshot is read back;
      4. the schema is created on the target and checked;
      5. every table is streamed over from one consistent view of the source;
      6. counts, foreign keys, unique constraints, sequences, schema and
         secret decryption are checked on the target.

    On failure: the target is left in whatever state it reached, the caller
    must NOT persist the URL, and the source is untouched. The message says
    whether the target has to be reset, and names the snapshot when one was
    taken and verified before the failure.
    """
    # Force-load every model module so db.metadata.create_all() sees them.
    _force_register_all_models()

    stats: Dict[str, object] = {
        "tables_migrated": 0,
        "rows_migrated": 0,
        "snapshot": None,
        "tables": {},
        "dropped_columns": {},
        "source_drift": {},
        "target_written": False,
    }

    ok, msg = test_connection(target_url)
    if not ok:
        stats["refusal"] = "preflight"
        return False, f"Target unreachable: {msg}", stats

    target_engine = None
    try:
        target_engine = create_engine(sqlalchemy_url(target_url), pool_pre_ping=True)
        target_is_pg = target_url.startswith("postgresql")

        # 1. Nothing is touched until the target is known to be empty.
        # Kept as a count rather than a table-by-table listing: what the
        # operator (and the audit entry) needs is that every table was looked
        # at, not sixty lines of zeroes.
        inspected = check_target_is_empty(target_engine)
        stats["target_inspected"] = {
            'tables': len(inspected), 'rows': sum(inspected.values())}

        # 2. The source has to be copyable before it is worth dumping.
        stats["source_integrity"] = _check_source_integrity()

        # 3. No migration without a rollback point that has been read back.
        snapshot = create_source_snapshot()
        # The proof names the snapshot; where the instance keeps it is not
        # the caller's business, and these statistics go to the audit log.
        stats["snapshot"] = snapshot.as_proof()

        # 4. Schema first, checked before a row is inserted. From here on
        # the target has been written to, which changes what the operator
        # has to do before retrying.
        stats["target_written"] = True
        _create_target_schema(target_engine, target_is_pg)
        check_target_schema(target_engine)

        # 5. One consistent view of the source, streamed over in batches.
        with consistent_source(snapshot) as (src, source_view, source_is_pg):
            plan = build_copy_plan(src.engine, target_engine)
            # What the standing approval in preflight.LEGACY_COLUMNS costs on
            # this particular database. Reported rather than merely allowed:
            # an operator who is told which columns were left behind, and
            # why, can check the claim.
            stats["dropped_columns"] = dropped_columns(src.engine, target_engine)
            result = copy_tables(
                src, target_engine, plan,
                source_is_pg=source_is_pg, target_is_pg=target_is_pg)

        stats["source_view"] = source_view
        stats["tables"] = dict(result.tables)
        stats["tables_migrated"] = len(result.tables)
        stats["rows_migrated"] = result.rows

        # Sequences are reset before they are verified: a sequence left
        # behind the data is a primary-key violation on the first insert
        # after the switch, and the check below is what makes it blocking.
        if target_is_pg:
            _reset_pg_sequences(target_engine)

        # 6. What landed is checked before the caller is told it can switch.
        stats["validation"] = verify_migration(
            target_engine, result.tables, target_is_pg=target_is_pg)

        # Measured last, so it covers the whole copy and its verification.
        drift = _source_drift(result.tables)
        stats["source_drift"] = drift

        message = "Data migrated and verified"
        if drift:
            written = sum(count for count in drift.values() if count > 0)
            message += (
                f". {written} row(s) reached the source after the snapshot "
                f"was taken ({len(drift)} table(s) moved) and are NOT on the "
                "target: stop writing to this instance before switching, or "
                "migrate again from a quiet source"
            )
        return True, message, stats

    except (PreflightError, SnapshotError, CopyError, VerificationError) as exc:
        logger.error("Migration refused: %s", exc)
        stats["refusal"] = _refusal_kind(exc)
        return False, f"{exc}{_rollback_hint(target_url, stats)}", stats
    except Exception as e:
        logger.exception("Data migration failed")
        stats["refusal"] = "error"
        return False, (
            f"Migration failed: {_short_err(str(e))}."
            f"{_rollback_hint(target_url, stats)}"
        ), stats
    finally:
        if target_engine is not None:
            target_engine.dispose()


# What kind of refusal the caller is looking at. The HTTP layer turns a
# refusal that happened before anything was written into 409 Conflict and a
# failure during the work into 500, and it must not do that by matching on
# the wording of a message.
_REFUSAL_KINDS = (
    (PreflightError, 'preflight'),
    (SnapshotError, 'snapshot'),
    (CopyError, 'copy'),
    (VerificationError, 'verification'),
)


def _refusal_kind(exc: Exception) -> str:
    for kind, name in _REFUSAL_KINDS:
        if isinstance(exc, kind):
            return name
    return 'error'


def _rollback_hint(target_url: str, stats: dict) -> str:
    """What the operator has to do next, and what they still have.

    The snapshot is named only when one was actually taken and verified:
    pointing at a rollback point that does not exist is how an operator
    deletes the database they still needed.
    """
    hint = " The source database is untouched."

    # Only tell the operator to reset the target if the migration got far
    # enough to write to it: sending someone to drop a schema that this
    # migration never created is how an unrelated database gets dropped.
    if stats.get("target_written"):
        cleanup = (
            'DROP SCHEMA public CASCADE; CREATE SCHEMA public;'
            if target_url.startswith("postgresql")
            else 'delete the target SQLite file'
        )
        hint += f" Reset the target before retrying: {cleanup}"

    snapshot = stats.get("snapshot") or {}
    if snapshot.get("name"):
        hint += f" A verified snapshot of the source was kept ({snapshot['name']})."
    return hint


__all__ = [
    'BOOTSTRAP_AUTH_TABLES',
    'MigrationBusyError',
    'bootstrap_auth_to_target',
    'database_migration_lock',
    'migrate_data',
]
