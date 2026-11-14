"""
Database Admin — entry control for a backend migration.

A migration copies every row of the live database into another one. Two
questions decide whether that is safe, and both are answered here, before the
first INSERT:

  * is the target acceptable — empty, and either bare or carrying exactly the
    UCM schema and nothing else;
  * what exactly gets copied — a plan that either covers every table and every
    column of the source, or does not exist at all.

The rule throughout is that the answer to both is a yes/no, never a "mostly".
The migration this module guards used to accept a target holding certificates,
templates or HSM keys as long as ``users`` and ``certificates`` were empty (it
also probed a table named ``cas``, which has never existed — the table is
``certificate_authorities``, so that third probe was always a no-op), and it
logged a warning for a source table the target did not have, dropped columns
the target did not have, and still reported success. Silent partial copies are
the failure mode worth preventing: the operator switches the backend, the app
comes up, and the missing rows are only discovered much later, after the
source has moved on.

So every check here is fail-closed. An inspection that raises, a COUNT that
cannot run, a table whose name we cannot safely quote — all refusals. Nothing
is ever assumed empty or assumed copyable. The single exception is written
down, column by column and with a reason, in :data:`LEGACY_COLUMNS`.

Messages raised by :class:`PreflightError` travel to the API. They name tables
and columns, because that is what the operator needs to act on, and they never
carry a filesystem path or a connection URI: driver text goes through
``_short_err`` (which redacts credentials) and names coming from the database
go through ``_display``.
"""

import logging
import re
from dataclasses import dataclass
from typing import Dict, List, Sequence, Set

from sqlalchemy import inspect, text

from .helpers import _force_register_all_models, _short_err, _topo_sort_tables

logger = logging.getLogger(__name__)


class PreflightError(Exception):
    """Refusal to migrate, with a message already safe to return to the API.

    Raised instead of returning a flag so that no caller can keep going past a
    check it did not pass: the only way to reach the copy is for every check to
    return normally.
    """


# Tables that live outside ``db.metadata`` and are deliberately NOT copied.
# Each entry is a decision, not an oversight — anything else outside the
# metadata is a refusal, so this set is the only place such an approval exists.
#
#   alembic_version — a one-row schema stamp owned by Alembic. UCM manages its
#       own schema (``migrations/``, tracked in ``_migrations``), so the stamp
#       describes a history the target does not share; copying it would tell a
#       future Alembic run that migrations it never applied are already done.
#   flask_sessions — the SQL session store: live sessions of the old database,
#       meaningless on the new one and never copied; a non-empty table on the
#       target still fails check_target_is_empty.
IGNORED_TABLES = frozenset({"alembic_version", "flask_sessions"})

# Tables that live outside ``db.metadata`` and ARE copied.
#
#   _migrations — UCM's own applied-migrations ledger, created by the migration
#       runner rather than by a model, so ``db.metadata`` knows nothing about
#       it. It must be copied: a target without those rows re-runs every
#       migration against a schema that already has them.
INTERNAL_TABLES = frozenset({"_migrations"})

# {table: {column: reason}} — columns an installation still carries and the
# models no longer declare, so ``create_all`` does not create them on the
# target and their values cannot go anywhere.
#
# They are the only columns allowed to be left behind, and the same rule as
# ``services/backup/manifest.py`` applies: a column is copied unless someone
# wrote down why it is not. They all come from the 2.52 baseline schema, which a
# 2.254 database upgraded from it still carries, and
# ``tests/test_database_migration_preflight.py`` compares this list to it (frozen
# as a fixture): a column dropped from a model without a line here fails the suite.
#
# The reason says what became of the value, and that is NOT always "another
# column carries it". Three of these were replaced by a column that was added
# empty, with no migration copying anything across: on an installation old
# enough to have used the previous model, this column is the only copy of
# what it holds. Each reason below was checked against the migration that is
# supposed to have done the carrying, and says plainly when nothing did.
#
# Adding an entry is a decision to lose data. :func:`dropped_columns` counts
# what each one still holds on the database being migrated, so the decision is
# measured rather than assumed.
LEGACY_COLUMNS: Dict[str, Dict[str, str]] = {
    "trusted_certificates": {
        "source": "no code path has ever written it; the origin is recorded in added_by",
        "created_at": "replaced by added_at, which legacy migration 020 backfilled from it",
    },
    "group_members": {
        "created_at": "the membership date moved to joined_at (legacy migration 021), "
                      "which was added empty: on a row created before that "
                      "migration this is the only copy of the date",
    },
    "user_sessions": {
        "last_active": "replaced by last_activity, which legacy migration 030 "
                       "backfilled from it",
    },
    "certificate_policies": {
        "oid": "no code path has ever written it; policy qualifiers were never "
               "implemented on this table",
        "cps_uri": "no code path has ever written it; policy qualifiers were "
                   "never implemented on this table",
        "user_notice": "no code path has ever written it; policy qualifiers were "
                       "never implemented on this table",
        "enabled": "replaced by is_active, which legacy migration 030 backfilled from it",
    },
    "approval_requests": {
        "target_id": "the approval model UCM replaced; certificate_id and policy_id "
                     "took over and legacy migration 030 added them empty",
        "target_type": "the approval model UCM replaced; certificate_id and policy_id "
                       "took over and legacy migration 030 added them empty",
        "data": "the request payload of the replaced approval model; migration 005 "
                "added request_data empty",
        "reviewed_at": "the review date of the replaced approval model; legacy "
                       "migration 030 added resolved_at empty",
        "reviewer_id": "the review trail of the replaced approval model; legacy "
                       "migration 030 added the approvals JSON empty",
        "review_comment": "the review trail of the replaced approval model; legacy "
                          "migration 030 added the approvals JSON empty",
    },
}

# Strict SQL identifier shape — letters, digits, underscore; not starting with
# a digit. Deliberately a copy of migration.py's ``_SAFE_IDENT_RE`` rather than
# an import: this module is the gate, and a gate that imports its own condition
# from the code it guards is one refactor away from losing it. Both the source
# and the target are operator-supplied databases (a hostile SQLite file, a PG
# instance with crafted catalog rows), so a name read from either one is data,
# never SQL, and nothing that fails this shape is interpolated into a query.
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# How many names a single refusal spells out. The point of the message is to
# let the operator act; the full list of a foreign database's tables would
# bury that under noise.
_MAX_NAMES_IN_MESSAGE = 8

# Ceiling on a single name in a message. A name is attacker-influenced text.
_MAX_NAME_LENGTH = 64

# Returned by _table_row_count when rows exist but COUNT(*) gave nothing back.
_ROWS_UNCOUNTED = -1


@dataclass(frozen=True)
class TablePlan:
    """One table to copy, and the exact columns to copy from it.

    Frozen because the plan is evidence: it is built once, before any write,
    and what the copy executes must be what the checks approved.

    ``columns`` keeps the source's own column order so a reader can line the
    plan up against the source schema; the tuple is the complete set of the
    source's columns, never a subset (a column that could not be copied is a
    refusal, so no plan exists in that case).
    """

    name: str
    columns: tuple


def _display(name) -> str:
    """Render a database-supplied name for a message bound for the API.

    Table and column names are read from an operator-supplied database, so
    they can carry control characters, quotes or kilobytes of padding. They
    are shown because the operator needs them, after being made harmless to
    paste into a log line or a JSON response.
    """
    text_value = str(name)
    cleaned = "".join(
        char if char.isprintable() and char not in '"\\' else "?"
        for char in text_value
    )
    if len(cleaned) > _MAX_NAME_LENGTH:
        cleaned = cleaned[:_MAX_NAME_LENGTH] + "..."
    return cleaned


def _join(names: Sequence) -> str:
    """List names for a message, capped, with the remainder counted not shown."""
    shown = [_display(n) for n in list(names)[:_MAX_NAMES_IN_MESSAGE]]
    hidden = len(names) - len(shown)
    listed = ", ".join(shown)
    return f"{listed} (+{hidden} more)" if hidden > 0 else listed


def _safe_ident(name: str) -> str:
    """Return *name* if it can be quoted into SQL, else refuse the migration.

    The old code filtered such names out of the column list and carried on,
    which is the silent-data-loss path this module exists to close: a column
    we cannot address is a column we cannot copy, and that is a refusal.
    """
    if not isinstance(name, str) or not _SAFE_IDENT_RE.match(name):
        raise PreflightError(
            f"Database object name '{_display(name)}' is not a plain SQL "
            "identifier, so it cannot be inspected or copied safely. "
            "Refusing to migrate."
        )
    return name


def _inspector(engine, side: str):
    """Reflect *engine*, turning any failure into a refusal.

    Everything downstream is derived from this reflection: an engine we cannot
    read tells us nothing about what the target holds, which is exactly the
    case where assuming "probably empty" destroys data.
    """
    try:
        return inspect(engine)
    except Exception as exc:
        raise PreflightError(
            f"Could not inspect the {side} database "
            f"({_short_err(str(exc))}). Refusing to migrate: an unreadable "
            "database cannot be shown to be safe to write to."
        ) from exc


def _table_names(inspector, side: str) -> List[str]:
    """Table names on one side, or a refusal."""
    try:
        return list(inspector.get_table_names())
    except Exception as exc:
        raise PreflightError(
            f"Could not list the tables of the {side} database "
            f"({_short_err(str(exc))}). Refusing to migrate."
        ) from exc


def _column_names(inspector, table: str, side: str) -> List[str]:
    """Column names of one table, in declaration order, or a refusal."""
    try:
        return [col["name"] for col in inspector.get_columns(table)]
    except Exception as exc:
        raise PreflightError(
            f"Could not read the columns of {side} table "
            f"'{_display(table)}' ({_short_err(str(exc))}). "
            "Refusing to migrate."
        ) from exc


def _connect(engine, side: str):
    """Open a connection, or refuse."""
    try:
        return engine.connect()
    except Exception as exc:
        raise PreflightError(
            f"Could not connect to the {side} database "
            f"({_short_err(str(exc))}). Refusing to migrate."
        ) from exc


def _table_row_count(conn, table: str) -> int:
    """Rows in *table*: 0, a positive count, or ``_ROWS_UNCOUNTED``.

    Emptiness is decided by ``SELECT 1 ... LIMIT 1``, which stops at the first
    row: the common answer is "empty", and the expensive answer (a full COUNT
    over a large table) is only worth paying for once we already know the
    migration is going to be refused and the operator needs the number.

    Exceptions are left to the caller, which knows which side and which table
    is being probed and turns them into a refusal.
    """
    quoted = _safe_ident(table)

    if conn.execute(text(f'SELECT 1 FROM "{quoted}" LIMIT 1')).first() is None:
        return 0

    row = conn.execute(text(f'SELECT COUNT(*) FROM "{quoted}"')).first()
    if row is None or row[0] is None:
        return _ROWS_UNCOUNTED
    return int(row[0])


def _describe_rows(table: str, count: int) -> str:
    """One "table X holds N rows" fragment for a refusal message."""
    if count == _ROWS_UNCOUNTED:
        return f"table '{_display(table)}' contains rows"
    return f"table '{_display(table)}' contains {count} row(s)"


def expected_schema() -> Dict[str, Set[str]]:
    """``{table: {column, ...}}`` for the whole UCM schema.

    Read from ``db.metadata`` after ``_force_register_all_models()`` because
    several model modules are imported only when their feature runs; without
    that call the metadata is a subset of the real schema, and every check
    here would be comparing against an incomplete idea of UCM.

    Keys are bare table names (``table.name``, not the ``schema.table`` key
    used by the metadata dict) so they line up with what an inspector returns.
    """
    _force_register_all_models()

    from models import db as _db

    return {
        table.name: {column.name for column in table.columns}
        for table in _db.metadata.tables.values()
    }


def check_target_is_empty(target_engine) -> Dict[str, int]:
    """Refuse unless the target is safe to write the whole database into.

    Runs *before* any schema creation, which is what makes it meaningful: once
    ``create_all`` has run, a bare database and a UCM database look alike.

    Three things get refused, in the order that explains the target best:

      * tables that are not UCM's — the operator pointed at a database that
        belongs to something else, and a migration would bury it;
      * a UCM table missing columns — a half-created or outdated schema, which
        would silently drop whatever those columns hold on the source;
      * a single row anywhere — including in ``_migrations`` and in
        :data:`IGNORED_TABLES`, which are not copied but whose contents still
        prove the database is somebody's, not nobody's.

    An already-created but completely empty UCM schema is accepted: that is
    what a target prepared by an earlier aborted attempt looks like, and
    ``create_all`` is happy to run over it.

    Returns ``{table: 0}`` for every table inspected — the evidence of what
    the check actually covered. An empty dict means an empty database (no
    tables at all), which is the nominal case.
    """
    expected = expected_schema()
    inspector = _inspector(target_engine, "target")
    tables = _table_names(inspector, "target")

    known = set(expected) | INTERNAL_TABLES | IGNORED_TABLES
    foreign = sorted(t for t in tables if t not in known)
    if foreign:
        raise PreflightError(
            f"Target database contains {len(foreign)} table(s) that are not "
            f"part of UCM ({_join(foreign)}). Refusing to migrate into a "
            "database that belongs to another application."
        )

    incomplete = []
    for table in sorted(tables):
        if table not in expected:
            continue
        missing = expected[table] - set(_column_names(inspector, table, "target"))
        if missing:
            incomplete.append(
                f"'{_display(table)}' is missing {_join(sorted(missing))}"
            )
    if incomplete:
        raise PreflightError(
            "Target database has a partial UCM schema: "
            + "; ".join(incomplete[:_MAX_NAMES_IN_MESSAGE])
            + ". Refusing to migrate: point at an empty database and let the "
            "migration create the schema."
        )

    inspected: Dict[str, int] = {}
    populated: List[str] = []

    conn = _connect(target_engine, "target")
    try:
        for table in sorted(tables):
            try:
                count = _table_row_count(conn, table)
            except PreflightError:
                raise
            except Exception as exc:
                raise PreflightError(
                    f"Could not verify that target table '{_display(table)}' "
                    f"is empty ({_short_err(str(exc))}). Refusing to migrate: "
                    "a table that cannot be read cannot be shown to be empty."
                ) from exc

            if count == 0:
                inspected[table] = 0
            else:
                populated.append(_describe_rows(table, count))
    finally:
        conn.close()

    if populated:
        raise PreflightError(
            "Target database is not empty: "
            + "; ".join(populated[:_MAX_NAMES_IN_MESSAGE])
            + ". Refusing to overwrite it. Reset the target database, or "
            "point the migration at an empty one."
        )

    logger.info("Preflight: target verified empty (%d table(s) inspected)", len(inspected))
    return inspected


def check_target_schema(target_engine) -> None:
    """Refuse unless the target now carries the complete UCM schema.

    Called after ``create_all``. ``create_all`` reports nothing when it
    cannot create a table (an existing object of the same name, a revoked
    privilege on one schema), and the copy that follows would then be the
    thing to discover it — one table at a time, halfway through the data.

    Only ``db.metadata`` tables are required here. ``_migrations`` is created
    separately by the migration itself, so demanding it at this point would
    depend on which of the two ran first; :func:`build_copy_plan` is where its
    absence on the target is caught.
    """
    expected = expected_schema()
    inspector = _inspector(target_engine, "target")
    tables = set(_table_names(inspector, "target"))

    missing_tables = sorted(t for t in expected if t not in tables)
    if missing_tables:
        raise PreflightError(
            f"Target schema is incomplete after creation: "
            f"{len(missing_tables)} table(s) missing ({_join(missing_tables)}). "
            "Refusing to migrate."
        )

    missing_columns = []
    for table in sorted(expected):
        missing = expected[table] - set(_column_names(inspector, table, "target"))
        if missing:
            missing_columns.append(
                f"'{_display(table)}' is missing {_join(sorted(missing))}"
            )
    if missing_columns:
        raise PreflightError(
            "Target schema is incomplete after creation: "
            + "; ".join(missing_columns[:_MAX_NAMES_IN_MESSAGE])
            + ". Refusing to migrate."
        )


def build_copy_plan(source_engine, target_engine) -> List[TablePlan]:
    """The complete list of what to copy, or a refusal.

    "Complete" is the whole point: every table of the source except
    :data:`IGNORED_TABLES`, and for each one every single column. What used to
    be a running tally of tables skipped and columns dropped — filled in as the
    copy went, and reported alongside a success — is gone: anything that cannot
    be copied is decided here, before the first INSERT. A source table the
    target does not have, a source column the target does not have, a metadata
    table the source does not have, a name that cannot be quoted: each refuses
    the migration while the source is still untouched and the operator can fix
    the target.

    Tables come back parents-first, so the copy satisfies foreign keys even
    when FK enforcement cannot be turned off (a non-superuser PostgreSQL role
    cannot set ``session_replication_role``). The order is taken from the
    TARGET, because the target's constraints are the ones that will be
    enforced: SQLite cannot add a foreign key to a table it has already
    created, so a constraint introduced after an installation was built
    exists in the models and on every PostgreSQL target, and nowhere in that
    installation's own schema. Ordering by the source would then insert a
    child before its parent and PostgreSQL would refuse the row — halfway
    through the copy, after the whole table had been read. Any table the
    sort leaves out is appended rather than dropped: a sort that degraded
    must not quietly shrink the plan.

    The one exception is :data:`LEGACY_COLUMNS`: a column the models dropped
    long ago, whose replacement holds the same information, and whose loss
    someone wrote down. Everything else the target cannot hold stops the
    migration. :func:`dropped_columns` reports what that exception actually
    cost on this source, so the operator reads it rather than guesses it.

    A source table outside ``db.metadata`` that the target also has is copied
    as-is. It is operator data on an operator-controlled database, and
    refusing to carry it over would lose it just as surely as the old skip did.
    """
    expected = expected_schema()

    source_inspector = _inspector(source_engine, "source")
    target_inspector = _inspector(target_engine, "target")

    source_tables = set(_table_names(source_inspector, "source"))
    target_tables = set(_table_names(target_inspector, "target"))

    absent_from_source = sorted(t for t in expected if t not in source_tables)
    if absent_from_source:
        raise PreflightError(
            f"Source database is missing {len(absent_from_source)} table(s) of "
            f"the UCM schema ({_join(absent_from_source)}). Refusing to "
            "migrate from a database whose schema is not the one this version "
            "expects."
        )

    ordered = [t for t in _topo_sort_tables(target_inspector) if t in source_tables]
    ordered += sorted(t for t in source_tables if t not in set(ordered))

    plan: List[TablePlan] = []
    missing_tables: List[str] = []
    missing_columns: List[str] = []

    for table in ordered:
        if table in IGNORED_TABLES:
            continue

        if table not in target_tables:
            missing_tables.append(table)
            continue

        source_columns = _column_names(source_inspector, table, "source")
        target_columns = set(_column_names(target_inspector, table, "target"))
        approved = LEGACY_COLUMNS.get(table, {})
        absent = [c for c in source_columns if c not in target_columns]
        unapproved = [c for c in absent if c not in approved]
        if unapproved:
            missing_columns.append(f"'{_display(table)}': {_join(unapproved)}")
            continue

        copied = tuple(_safe_ident(c) for c in source_columns if c in target_columns)
        if not copied:
            # Every column approved for dropping means the whole row is
            # dropped, which no approval covers.
            raise PreflightError(
                f"No column of source table '{_display(table)}' has a "
                "counterpart on the target. Refusing to migrate."
            )
        if absent:
            logger.info(
                "Preflight: %s drops approved legacy column(s): %s",
                table, ", ".join(sorted(absent)),
            )

        plan.append(TablePlan(name=_safe_ident(table), columns=copied))

    if missing_tables:
        raise PreflightError(
            f"Target database has no table for {len(missing_tables)} source "
            f"table(s) ({_join(missing_tables)}). Refusing to migrate: their "
            "rows would be dropped without a trace."
        )

    if missing_columns:
        raise PreflightError(
            "Target database is missing columns that hold source data: "
            + "; ".join(missing_columns[:_MAX_NAMES_IN_MESSAGE])
            + ". Refusing to migrate: those values would be dropped without a "
            "trace."
        )

    logger.info("Preflight: copy plan covers %d table(s)", len(plan))
    return plan


def dropped_columns(source_engine, target_engine) -> Dict[str, Dict[str, dict]]:
    """What this migration leaves behind, and how much of it there is.

    The approval in :data:`LEGACY_COLUMNS` is a standing one; this is what it
    costs on the database actually being migrated. Only columns this source
    really has, and that the target really lacks, are reported — an entry for
    a column a more recent installation never had would otherwise announce a
    loss that did not happen.

    Each entry carries the reason and the number of rows where the column is
    not NULL, because that is the difference between an approval and a
    rubber stamp: three of these columns were replaced by a column that was
    added empty, so on an old installation they are the only copy of what
    they hold, and an operator deserves to see "12 values" rather than a
    sentence. A count that cannot be taken is reported as unknown rather than
    as zero: this is the one number nobody should be reassured about by
    accident.
    """
    source_inspector = _inspector(source_engine, "source")
    target_inspector = _inspector(target_engine, "target")
    source_tables = set(_table_names(source_inspector, "source"))
    target_tables = set(_table_names(target_inspector, "target"))

    report: Dict[str, Dict[str, dict]] = {}
    conn = _connect(source_engine, "source")
    try:
        for table, approved in LEGACY_COLUMNS.items():
            if table not in source_tables or table not in target_tables:
                continue

            present = set(_column_names(source_inspector, table, "source"))
            on_target = set(_column_names(target_inspector, table, "target"))
            dropped = {}
            for column, reason in approved.items():
                if column not in present or column in on_target:
                    continue
                dropped[column] = {
                    'reason': reason,
                    'values': _non_null_count(conn, table, column),
                }
            if dropped:
                report[table] = dropped
    finally:
        conn.close()

    return report


def _non_null_count(conn, table: str, column: str):
    """How many rows of ``table`` have something in ``column``.

    Returns ``'unknown'`` rather than 0 when the count cannot be taken: a
    number that means "we did not look" must not read as "nothing was lost".
    """
    try:
        row = conn.execute(text(
            f'SELECT COUNT(*) FROM "{_safe_ident(table)}" '
            f'WHERE "{_safe_ident(column)}" IS NOT NULL')).first()
    except Exception as exc:
        logger.warning(
            "Could not count the values of %s.%s being dropped: %s",
            table, column, _short_err(str(exc)))
        return 'unknown'
    return int(row[0]) if row and row[0] is not None else 'unknown'
