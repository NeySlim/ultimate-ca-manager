"""
Database Admin — post-copy verification of a backend migration.

A copy that raised nothing is not a copy that may be switched to. The loader
inserts with foreign keys disabled (``session_replication_role='replica'`` on
PostgreSQL, ``PRAGMA foreign_keys=OFF`` on SQLite) and leaves the target's
sequences wherever ``CREATE TABLE`` left them, so the failures that matter are
exactly the ones it cannot see: a table short of rows, an orphan no INSERT ever
checked, a duplicate a unique index would have refused, a sequence that hands
the next INSERT a primary key that already exists. Encrypted columns add a
second class of silent loss — bytes, memoryview and text cross the two drivers
differently, and a private key or an integration secret that no longer decrypts
copies as a perfectly valid row.

Everything here reads the TARGET only. The source kept serving requests while
the copy ran, so re-reading it would compare against a database that has since
moved; what the copy actually observed is passed in as ``expected_counts``.

A check that cannot run is a failure. "Could not verify" and "verified" must
never reach the operator as the same answer: that answer authorises switching
the whole installation onto the target.
"""

import importlib
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import (
    column as sa_column,
    func,
    inspect,
    select,
    table as sa_table,
    text,
)

from .helpers import (
    _PG_SERIAL_COLUMNS_SQL,
    _force_register_all_models,
    _short_err,
)

logger = logging.getLogger(__name__)


class VerificationError(Exception):
    """A post-copy check failed: the switch is forbidden.

    The message is already safe to hand to an API caller — driver text goes
    through ``_short_err`` (which redacts DB URI passwords) and no secret
    value, connection string or filesystem path is ever interpolated into it.
    """


# Strict SQL identifier shape — letters, digits, underscore; not starting with
# a digit. Same rule as migration.py's ``_SAFE_IDENT_RE``, deliberately spelled
# again here rather than imported: migration.py is the module that CALLS this
# one, so importing from it would make the verification depend on the loader it
# verifies (and close the import cycle). The names checked below come from the
# target's catalogue via inspect(), i.e. from a database an operator pointed us
# at — never trusted for raw interpolation into SQL.
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

# Anti-join and GROUP BY probes stop once they have enough to condemn the
# migration: the operator needs to know a table has orphans, not to wait on a
# full scan of every child table to be told so.
_ORPHAN_SCAN_LIMIT = 1000
_DUPLICATE_SCAN_LIMIT = 1000

# Encrypted columns are sampled, not swept: decryption is per-value work, and
# what this check exists to catch is systematic — a driver handing text back
# as bytes, a normalisation step re-encoding a column — so it shows on the
# first rows or not at all. It is a sample, not a proof: ``_normalize_row``
# branches per value, so a column can in principle break on some rows only.
_SECRET_SAMPLE_LIMIT = 5

# Private keys are not in any Section's `secrets` (the archive carries them
# under another name, see manifest.Section.handled), yet they are both
# encrypted at rest and the one thing a migration must never lose: a CA whose
# key no longer decrypts cannot sign anything again.
_EXTRA_SECRET_COLUMNS: Tuple[Tuple[str, str], ...] = (
    ('certificate_authorities', 'prv'),
    ('certificates', 'prv'),
)

# last_value of a sequence, with the sequence name as a bound parameter (data,
# not SQL). pg_get_serial_sequence() returns names already quoted where they
# need it, so they must not be split, re-quoted or pattern-matched. Returns
# NULL when the sequence has never been called.
_SEQ_LAST_VALUE_SQL = text("SELECT pg_sequence_last_value(CAST(:seq AS regclass))")

_SECRET_UNREADABLE_BYTES = (
    'a stored value is no longer readable text'
)
_SECRET_UNDECRYPTABLE = (
    'a stored value did not decrypt (wrong or missing encryption key, or the '
    'value did not survive the copy)'
)


# ---------------------------------------------------------------------------
# Small shared plumbing
# ---------------------------------------------------------------------------

def _display(name) -> str:
    """Render a database-supplied name for a message bound for the API.

    Table and column names are read from an operator-supplied database, so
    they can carry control characters, quotes or kilobytes of padding. Same
    treatment as ``preflight._display``, for the same reason.
    """
    cleaned = "".join(
        char if char.isprintable() and char not in '"\\' else "?"
        for char in str(name)
    )
    return cleaned[:64] + "..." if len(cleaned) > 64 else cleaned


def _safe_ident(name: str) -> str:
    """Return *name* if it is a safe SQL identifier, else fail the migration."""
    if not isinstance(name, str) or not _SAFE_IDENT_RE.match(name):
        raise VerificationError(
            "Refusing to verify an unsafe SQL identifier from the target: "
            f"'{_display(name)}'"
        )
    return name


def _q(name: str) -> str:
    """Quote a validated identifier for interpolation into a text() query."""
    return f'"{_safe_ident(name)}"'


def _connect(engine):
    """Open a connection to the target, or fail the verification."""
    try:
        return engine.connect()
    except Exception as exc:
        raise VerificationError(
            f"Target database is unreachable for verification: {_short_err(str(exc))}"
        ) from exc


def _scalar(conn, stmt, params: Optional[dict] = None, *, what: str):
    """Run a single-value query, turning any driver failure into a refusal."""
    try:
        return conn.execute(stmt, params or {}).scalar()
    except Exception as exc:
        raise VerificationError(
            f"Could not read {what} on the target: {_short_err(str(exc))}"
        ) from exc


def _reflect(engine) -> Tuple[Any, List[str]]:
    """Return (inspector, table names) for the target.

    Reflection failing is not a reason to verify less — it is a reason to
    refuse, because everything downstream would then be checking a schema
    nobody managed to read.
    """
    try:
        insp = inspect(engine)
        return insp, list(insp.get_table_names())
    except Exception as exc:
        raise VerificationError(
            f"Could not read the target schema: {_short_err(str(exc))}"
        ) from exc


def _columns_of(insp, table_name: str, cache: dict) -> set:
    """Reflected column names of *table_name*, memoised per call site."""
    if table_name not in cache:
        try:
            cache[table_name] = {c['name'] for c in insp.get_columns(table_name)}
        except Exception as exc:
            raise VerificationError(
                f"Could not read the columns of table '{table_name}' on the "
                f"target: {_short_err(str(exc))}"
            ) from exc
    return cache[table_name]


def _bounded(items: List[str], limit: int = 5) -> str:
    """Join a list for an operator-facing message without pasting all of it."""
    head = ', '.join(items[:limit])
    return head if len(items) <= limit else f"{head} (+{len(items) - limit} more)"


# ---------------------------------------------------------------------------
# 1. Row counts
# ---------------------------------------------------------------------------

def check_row_counts(engine, expected_counts: Dict[str, int]) -> Dict[str, Any]:
    """Compare every copied table on the target with what the copy observed.

    ``expected_counts`` was measured while the source was read under one
    consistent snapshot; the source may have moved since, so it is the only
    admissible reference. A table that lost rows on the way (a partial
    transaction, a per-row error that was swallowed) is invisible everywhere
    else — the target is a perfectly valid database, just not the same one.
    """
    per_table: Dict[str, int] = {}

    with _connect(engine) as conn:
        for table_name in sorted(expected_counts):
            expected = expected_counts[table_name]
            actual = _scalar(
                conn,
                text(f'SELECT COUNT(*) FROM {_q(table_name)}'),
                what=f"the row count of table '{table_name}'",
            )
            actual = int(actual or 0)

            if actual != int(expected):
                raise VerificationError(
                    f"Row count mismatch on table '{table_name}': "
                    f"{int(expected)} row(s) copied, {actual} row(s) on the target"
                )

            per_table[table_name] = actual

    return {
        'tables': len(per_table),
        'rows': sum(per_table.values()),
        'per_table': per_table,
    }


# ---------------------------------------------------------------------------
# 2. Foreign keys
# ---------------------------------------------------------------------------

def _orphan_count(conn, child: str, child_cols: List[str],
                  parent: str, parent_cols: List[str]) -> int:
    """Count (up to a cap) child rows whose parent row is absent.

    An anti-join rather than PostgreSQL's ``VALIDATE CONSTRAINT``: the same
    statement has to answer on SQLite, and it also answers for constraints the
    target never declared. NULL follows MATCH SIMPLE, the default on both
    backends — a composite key with any NULL part satisfies the constraint —
    so every child column must be non-NULL for a row to count as an orphan.
    """
    on_clause = ' AND '.join(
        f'ucm_child.{_q(cc)} = ucm_parent.{_q(pc)}'
        for cc, pc in zip(child_cols, parent_cols)
    )
    conditions = [f'ucm_parent.{_q(parent_cols[0])} IS NULL']
    conditions += [f'ucm_child.{_q(cc)} IS NOT NULL' for cc in child_cols]

    stmt = text(
        f'SELECT COUNT(*) FROM (SELECT 1 AS orphan FROM {_q(child)} AS ucm_child '
        f'LEFT JOIN {_q(parent)} AS ucm_parent ON {on_clause} '
        f'WHERE {" AND ".join(conditions)} LIMIT :scan_limit) AS ucm_orphans'
    )
    value = _scalar(
        conn, stmt, {'scan_limit': _ORPHAN_SCAN_LIMIT},
        what=f"orphaned rows of table '{child}'",
    )
    return int(value or 0)


def check_foreign_keys(engine, *, side: str = 'the target',
                       missing_parent_is_fatal: bool = True) -> Dict[str, Any]:
    """Check every reflected foreign key against the rows actually present.

    The bulk load runs with FK enforcement off, so nothing was checked at
    insert time: a child copied without its parent (a table skipped, a row
    dropped, an insert order that a fallback path got wrong) lands as a row
    the database itself would have refused. Re-enabling enforcement afterwards
    does not revisit existing rows on either backend, so the breakage only
    shows up the day someone touches the row.

    ``side`` names the database being checked in the messages, because this
    same check runs on the source before a migration starts: SQLite enforces
    no foreign key unless asked to, so an installation can accumulate orphan
    rows for years, and they have to be found before the copy rather than
    after it.

    ``missing_parent_is_fatal`` is what separates the two uses. On the target,
    a foreign key pointing at a table that is not there means the schema we
    just built is wrong, and nothing else matters. On the source it means the
    opposite: SQLite accepts a reference to a table that does not exist, so an
    installation upgraded through a migration with a typo in it carries that
    declaration forever, harmlessly, because SQLite never enforces it. The
    data still has to be checked — against the target's schema, which is
    correct — so the declaration is recorded and the check moves on.
    """
    insp, table_names = _reflect(engine)
    known = set(table_names)
    checked = 0
    composite = 0
    dangling: List[Dict[str, str]] = []

    with _connect(engine) as conn:
        for table_name in sorted(table_names):
            try:
                foreign_keys = insp.get_foreign_keys(table_name)
            except Exception as exc:
                raise VerificationError(
                    f"Could not read the foreign keys of table '{table_name}' "
                    f"on {side}: {_short_err(str(exc))}"
                ) from exc

            for fk in foreign_keys:
                child_cols = list(fk.get('constrained_columns') or [])
                parent = fk.get('referred_table')
                parent_cols = list(fk.get('referred_columns') or [])
                label = fk.get('name') or f"{table_name}({', '.join(child_cols)})"

                if not child_cols or not parent:
                    raise VerificationError(
                        f"Foreign key '{label}' on table '{table_name}' could "
                        f"not be read from the schema of {side}"
                    )
                if parent not in known:
                    if missing_parent_is_fatal:
                        raise VerificationError(
                            f"Foreign key '{label}' on table '{table_name}' "
                            f"references table '{parent}', which is missing "
                            f"from {side}"
                        )
                    dangling.append({
                        'table': table_name,
                        'constraint': label,
                        'references': str(parent),
                        'reason': ('the referenced table does not exist here; '
                                   'the data is checked against the schema '
                                   'the migration creates'),
                    })
                    continue

                if not parent_cols or any(c is None for c in parent_cols):
                    # A REFERENCES clause without an explicit column list
                    # points at the parent's primary key.
                    try:
                        parent_cols = list(
                            insp.get_pk_constraint(parent).get('constrained_columns') or []
                        )
                    except Exception as exc:
                        raise VerificationError(
                            f"Foreign key '{label}' on table '{table_name}' "
                            f"could not be resolved against '{parent}': "
                            f"{_short_err(str(exc))}"
                        ) from exc

                if len(parent_cols) != len(child_cols):
                    raise VerificationError(
                        f"Foreign key '{label}' on table '{table_name}' could "
                        f"not be matched to columns of '{parent}'"
                    )

                orphans = _orphan_count(
                    conn, table_name, child_cols, parent, parent_cols
                )
                if orphans:
                    at_least = '' if orphans < _ORPHAN_SCAN_LIMIT else 'at least '
                    raise VerificationError(
                        f"Foreign key '{label}' on table '{table_name}' is "
                        f"broken on {side}: {at_least}{orphans} row(s) "
                        f"reference a missing row of '{parent}' "
                        f"({', '.join(child_cols)} -> {', '.join(parent_cols)})"
                    )

                checked += 1
                if len(child_cols) > 1:
                    composite += 1

    return {
        'constraints_checked': checked,
        'composite_constraints': composite,
        'tables': len(table_names),
        'orphans': 0,
        'dangling_count': len(dangling),
        'dangling': dangling,
        'scan_limit': _ORPHAN_SCAN_LIMIT,
    }


def check_declared_foreign_keys(engine, *,
                               side: str = 'the current database') -> Dict[str, Any]:
    """Check rows against the foreign keys the MODELS declare.

    A database created years ago carries the constraints of the schema of
    that day. SQLite cannot add one to an existing table, so a foreign key
    introduced later lives in the models and in every PostgreSQL
    installation, and nowhere in this file — ``check_foreign_keys`` reflects
    what the database declares, and would never look at it.

    The target, though, is built from the models, so those are the
    constraints the data has to satisfy. Checking only what the source
    declares is how a migration gets to the middle of a table before
    PostgreSQL refuses a row and the whole copy is thrown away.

    A constraint whose table or column does not exist here is skipped: this
    database simply has nothing to check against it.
    """
    from models import db as _db

    _force_register_all_models()
    insp, table_names = _reflect(engine)
    present = set(table_names)
    column_cache: dict = {}
    checked = 0
    skipped = 0

    with _connect(engine) as conn:
        for table in _db.metadata.sorted_tables:
            if table.name not in present:
                skipped += 1
                continue

            child_present = _columns_of(insp, table.name, column_cache)

            for constraint in sorted(table.foreign_key_constraints,
                                     key=lambda c: str(c.elements[0].target_fullname)):
                elements = list(constraint.elements)
                child_cols = [element.parent.name for element in elements]
                parent = elements[0].column.table.name
                parent_cols = [element.column.name for element in elements]

                if parent not in present:
                    skipped += 1
                    continue
                parent_present = _columns_of(insp, parent, column_cache)
                if (not set(child_cols) <= child_present
                        or not set(parent_cols) <= parent_present):
                    skipped += 1
                    continue

                orphans = _orphan_count(
                    conn, table.name, child_cols, parent, parent_cols)
                if orphans:
                    at_least = '' if orphans < _ORPHAN_SCAN_LIMIT else 'at least '
                    raise VerificationError(
                        f"Table '{table.name}' holds {at_least}{orphans} row(s) "
                        f"referencing a missing row of '{parent}' "
                        f"({', '.join(child_cols)} -> {', '.join(parent_cols)}) "
                        f"on {side}"
                    )
                checked += 1

    return {
        'constraints_checked': checked,
        'constraints_skipped': skipped,
        'tables': len(table_names),
        'orphans': 0,
        'scan_limit': _ORPHAN_SCAN_LIMIT,
    }


# ---------------------------------------------------------------------------
# 3. Unique constraints and unique indexes
# ---------------------------------------------------------------------------

def _duplicate_groups(conn, table_name: str, cols: List[str]) -> int:
    """Count (up to a cap) value groups appearing more than once.

    NULLs are excluded: both backends treat NULL as distinct for uniqueness,
    while GROUP BY folds them into one group — counting them would condemn a
    perfectly legal target.
    """
    quoted = [_q(c) for c in cols]
    not_null = ' AND '.join(f'{c} IS NOT NULL' for c in quoted)
    stmt = text(
        f'SELECT COUNT(*) FROM (SELECT 1 AS duplicated FROM {_q(table_name)} '
        f'WHERE {not_null} GROUP BY {", ".join(quoted)} '
        f'HAVING COUNT(*) > 1 LIMIT :scan_limit) AS ucm_duplicates'
    )
    value = _scalar(
        conn, stmt, {'scan_limit': _DUPLICATE_SCAN_LIMIT},
        what=f"duplicate values of table '{table_name}'",
    )
    return int(value or 0)


def _partial_index_reason(index: dict) -> Optional[str]:
    """Why this index cannot be checked by a global GROUP BY, if it cannot.

    A partial index (``CREATE UNIQUE INDEX ... WHERE ...``) constrains a subset
    of the rows, e.g. ``uq_windows_enrollment_profiles_default``, which allows
    one default profile. A GROUP BY over the whole table would report the
    profiles that are not the default as duplicates and block a migration that
    is perfectly correct, so the index is declared unverifiable instead of being
    answered wrongly.
    """
    options = index.get('dialect_options') or {}
    if any(key.endswith('_where') for key in options):
        return ('partial index (WHERE clause): its scope is a subset of the '
                'table, which a global GROUP BY cannot represent')

    columns = index.get('column_names')
    if not columns or any(c is None for c in columns):
        return ('index over an expression rather than plain columns, which a '
                'GROUP BY on columns cannot reproduce')

    return None


def check_unique_constraints(engine) -> Dict[str, Any]:
    """Look for values a unique constraint or index would have refused.

    The copy never asks: a UNIQUE index is enforced per INSERT, and rows that
    arrived through a path where the constraint did not yet exist, or under a
    collation/case handling that differs between the two backends, sit there
    until the first write touches them.

    Constraints that cannot be expressed as a global GROUP BY are reported as
    skipped, with the reason and the count — an unchecked index the report is
    silent about is the failure mode this whole module exists to remove.
    """
    insp, table_names = _reflect(engine)
    constraints_checked = 0
    indexes_checked = 0
    skipped: List[Dict[str, str]] = []

    with _connect(engine) as conn:
        for table_name in sorted(table_names):
            try:
                unique_constraints = insp.get_unique_constraints(table_name)
                indexes = insp.get_indexes(table_name)
            except Exception as exc:
                raise VerificationError(
                    f"Could not read the unique constraints of table "
                    f"'{table_name}' on the target: {_short_err(str(exc))}"
                ) from exc

            seen: set = set()

            for constraint in unique_constraints:
                cols = list(constraint.get('column_names') or [])
                label = constraint.get('name') or f"{table_name}({', '.join(cols)})"

                if not cols or any(c is None for c in cols):
                    skipped.append({
                        'table': table_name,
                        'constraint': label,
                        'reason': 'no column list reflected for this constraint',
                    })
                    continue

                duplicates = _duplicate_groups(conn, table_name, cols)
                if duplicates:
                    raise VerificationError(
                        f"Unique constraint '{label}' on table '{table_name}' "
                        f"is violated on the target: {duplicates} duplicated "
                        f"value group(s) over ({', '.join(cols)})"
                    )

                seen.add(tuple(cols))
                constraints_checked += 1

            for index in indexes:
                if not index.get('unique'):
                    continue

                cols = list(index.get('column_names') or [])
                label = index.get('name') or f"{table_name}({', '.join(str(c) for c in cols)})"

                reason = _partial_index_reason(index)
                if reason:
                    skipped.append({
                        'table': table_name,
                        'constraint': label,
                        'reason': reason,
                    })
                    continue

                if tuple(cols) in seen:
                    continue  # same column set already checked as a constraint

                duplicates = _duplicate_groups(conn, table_name, cols)
                if duplicates:
                    raise VerificationError(
                        f"Unique index '{label}' on table '{table_name}' is "
                        f"violated on the target: {duplicates} duplicated "
                        f"value group(s) over ({', '.join(cols)})"
                    )

                seen.add(tuple(cols))
                indexes_checked += 1

    return {
        'constraints_checked': constraints_checked,
        'unique_indexes_checked': indexes_checked,
        'duplicate_groups': 0,
        'skipped_count': len(skipped),
        'skipped': skipped,
        'scan_limit': _DUPLICATE_SCAN_LIMIT,
    }


def check_local_email_flags(engine) -> Dict[str, Any]:
    """``users.has_sso_identity`` agrees with ``user_sso_identities`` on every account.

    The flag is what ``ix_users_email_local`` reads to hold the e-mail of local accounts
    unique: a wrong flag takes an account out of that index, or puts it in, unnoticed."""
    insp, table_names = _reflect(engine)
    if 'users' not in table_names or 'user_sso_identities' not in table_names:
        return {'accounts_checked': 0, 'skipped_count': 1, 'skipped': [{
            'table': 'users', 'constraint': 'has_sso_identity',
            'reason': 'users or user_sso_identities is missing on the target'}]}
    held = ('EXISTS (SELECT 1 FROM "user_sso_identities" i WHERE i."user_id" = u."id")')
    with _connect(engine) as conn:
        wrong = _scalar(conn, text(
            f'SELECT COUNT(*) FROM "users" u WHERE u."has_sso_identity" <> {held}'),
            what="the SSO flag of the accounts")
        checked = _scalar(conn, text('SELECT COUNT(*) FROM "users"'), what="the accounts")
    if wrong:
        raise VerificationError(
            f"users.has_sso_identity disagrees with user_sso_identities on {int(wrong)} "
            "account(s): the e-mail of local accounts would not be held unique")
    return {'accounts_checked': int(checked or 0), 'disagreeing': 0}


# ---------------------------------------------------------------------------
# 4. Sequences (PostgreSQL only)
# ---------------------------------------------------------------------------

def _pg_max_stmt(schema_name: str, table_name: str, column_name: str):
    """MAX() of one serial column, with identifiers rendered by the compiler.

    Same construction as helpers._pg_setval_stmt: nothing from the catalogue
    is concatenated on the Python side, and the table stays schema-qualified so
    a search_path cannot silently point MAX() at another table.
    """
    col = sa_column(column_name)
    tbl = sa_table(table_name, col, schema=schema_name)
    return select(func.max(col)).select_from(tbl)


def check_sequences(engine) -> Dict[str, Any]:
    """Check that no sequence would hand out a key the table already holds.

    Rows are copied WITH their primary keys, which leaves every sequence on a
    freshly created target at its starting value. ``_reset_pg_sequences``
    fixes that, but it only logs a warning when a ``setval()`` is refused
    (a non-owner role, a revoked grant), and a sequence left behind the data
    is invisible until the first INSERT fails with a duplicate key — after the
    switch, in production.

    SQLite has no sequences: its ids come from rowid/AUTOINCREMENT, derived
    from the table itself, so there is nothing that can fall behind.
    """
    dialect = getattr(engine.dialect, 'name', '') or ''
    if not dialect.startswith('postgres'):
        return {
            'applicable': False,
            'backend': dialect or 'unknown',
            'reason': ('not applicable: SQLite derives new ids from the table '
                       '(rowid/AUTOINCREMENT), so no counter can lag behind it'),
            'sequences_checked': 0,
        }

    checked = 0
    unresolved: List[Dict[str, str]] = []
    _, table_names = _reflect(engine)

    with _connect(engine) as conn:
        try:
            rows = conn.execute(_PG_SERIAL_COLUMNS_SQL).fetchall()
        except Exception as exc:
            raise VerificationError(
                f"Could not list the serial columns of the target: "
                f"{_short_err(str(exc))}"
            ) from exc

        for schema_name, table_name, column_name, sequence_name in rows:
            if not sequence_name:
                # nextval() default without a sequence owned by the column
                # (a shared or operator-managed sequence). Nothing links the
                # column to a counter we could compare, so it is named in the
                # report rather than silently counted as verified.
                unresolved.append({
                    'table': str(table_name),
                    'column': str(column_name),
                    'reason': ('the column default calls a sequence it does '
                               'not own; its value cannot be resolved'),
                })
                continue

            max_value = _scalar(
                conn,
                _pg_max_stmt(schema_name, table_name, column_name),
                what=f"the highest value of '{table_name}.{column_name}'",
            )
            last_value = _scalar(
                conn, _SEQ_LAST_VALUE_SQL, {'seq': sequence_name},
                what=f"the sequence of '{table_name}.{column_name}'",
            )

            if max_value is not None and (last_value is None or last_value < max_value):
                next_value = 1 if last_value is None else int(last_value) + 1
                raise VerificationError(
                    f"Sequence behind the data on '{table_name}.{column_name}': "
                    f"the column already holds values up to {int(max_value)} "
                    f"while the sequence would hand out {next_value} next: "
                    "the first insert on the target would violate the primary key"
                )

            checked += 1

    if not checked and table_names:
        # A target this migration built has a serial primary key on every
        # table. Finding none means the catalogue query looked somewhere else
        # — a search_path pointing at another schema, for instance — and
        # ``_reset_pg_sequences`` looked there too, so nothing was reset.
        # "Could not look" and "verified" must not be the same answer.
        raise VerificationError(
            f"No sequence was found on the target although it holds "
            f"{len(table_names)} table(s). Nothing could be reset or checked, "
            "and the first insert after the switch would collide with the "
            "copied rows. Check that the connection's search_path resolves "
            "to the schema the migration created."
        )

    if unresolved:
        first = unresolved[0]
        raise VerificationError(
            f"The sequence behind '{first['table']}.{first['column']}' could "
            f"not be resolved on the target ({len(unresolved)} column(s) in "
            "all), so nothing can say whether it would hand out a key the "
            "table already holds. The migration created this schema itself, "
            "so a column whose counter cannot be found means the target is "
            "not the one the migration built."
        )

    return {
        'applicable': True,
        'backend': 'postgresql',
        'sequences_checked': checked,
        'unresolved_count': 0,
        'unresolved': [],
    }


# ---------------------------------------------------------------------------
# 5. Schema
# ---------------------------------------------------------------------------

def check_schema(engine) -> Dict[str, Any]:
    """Check the target carries every table and column the models declare.

    ``create_all`` only creates what is registered, and several model modules
    register lazily — a target built while one of them had not been imported
    is missing whole tables, and the copy reacts by skipping them with a log
    line nobody reads. The comparison is made after forcing every model module
    in, so "absent from the target" cannot mean "absent from this process".
    """
    _force_register_all_models()
    from models import db as _db

    insp, table_names = _reflect(engine)
    present_tables = set(table_names)
    cache: Dict[str, set] = {}

    missing_tables: List[str] = []
    missing_columns: List[str] = []
    columns_checked = 0

    for tbl in _db.metadata.sorted_tables:
        if tbl.name not in present_tables:
            missing_tables.append(tbl.name)
            continue

        present_columns = _columns_of(insp, tbl.name, cache)
        for col in tbl.columns:
            columns_checked += 1
            if col.name not in present_columns:
                missing_columns.append(f"{tbl.name}.{col.name}")

    if missing_tables or missing_columns:
        details = []
        if missing_tables:
            details.append(f"missing table(s): {_bounded(missing_tables)}")
        if missing_columns:
            details.append(f"missing column(s): {_bounded(missing_columns)}")
        raise VerificationError(
            "Target schema is incomplete: " + '; '.join(details)
        )

    return {
        'tables_expected': len(_db.metadata.sorted_tables),
        'tables_present': len(present_tables),
        'columns_checked': columns_checked,
    }


# ---------------------------------------------------------------------------
# 6. Encrypted columns
# ---------------------------------------------------------------------------

def _secret_columns_of_section(section_name: str, section) -> List[Tuple[str, str]]:
    """Resolve one manifest section to the (table, column) pairs it encrypts.

    The manifest names models and model attributes, neither of which is a
    table or a column: ``models.sso:SSOProvider`` lives in
    ``pro_sso_providers``, and a secret is often a property over a private
    column (``auth_token`` over ``_auth_token``). Both are resolved through
    the mapper, with the same two spellings ``tests/test_backup_manifest.py``
    accepts — a name that resolves to neither is a refusal, because a secret
    nobody can locate is a secret nobody verified.
    """
    module_name, _, class_name = section.model.partition(':')
    try:
        module = importlib.import_module(module_name)
        model = getattr(module, class_name)
        mapped_table = inspect(model).local_table
    except Exception as exc:
        raise VerificationError(
            f"Cannot verify the encrypted columns of section '{section_name}': "
            f"its model could not be resolved ({_short_err(str(exc))})"
        ) from exc

    by_key = {col.key: col.name for col in mapped_table.columns}
    resolved: List[Tuple[str, str]] = []

    for secret in section.secrets:
        for candidate in (secret, f'_{secret}'):
            if candidate in by_key:
                resolved.append((mapped_table.name, by_key[candidate]))
                break
        else:
            raise VerificationError(
                f"Cannot verify the encrypted columns of section "
                f"'{section_name}': '{secret}' is not a column of table "
                f"'{mapped_table.name}'"
            )

    return resolved


def encrypted_columns() -> List[Tuple[str, str]]:
    """Return [(table, column)] for every column stored encrypted at rest.

    The authority is the backup manifest, so a secret declared there is
    verified here without anyone having to remember to write it down twice.
    """
    from services.backup.manifest import SECTIONS

    columns = set(_EXTRA_SECRET_COLUMNS)
    for section_name, section in SECTIONS.items():
        if not section.secrets:
            continue
        columns.update(_secret_columns_of_section(section_name, section))

    return sorted(columns)


def _probe_secret_value(value) -> Tuple[str, Optional[str]]:
    """Classify one stored value, as (verdict, reason).

    The verdict is 'decrypted', 'plaintext', 'empty' or 'unreadable'; the
    reason accompanies 'unreadable' only, and is one of this module's fixed
    phrases — never anything derived from the value itself.

    The two at-rest layers fail open by design — ``decrypt_text`` hands back
    its input when it cannot decrypt, ``decrypt_value`` answers None — so a
    caller that only looks at the return value cannot tell a secret from its
    own ciphertext. This is the same reasoning as
    ``services/backup/key_material.py``, which refuses to archive a value it
    could not read.

    A value that was never encrypted (a row predating at-rest encryption) is
    readable by definition and is reported as such, not as a failure.
    """
    if value is None:
        return 'empty', None

    if isinstance(value, memoryview):
        value = bytes(value)

    if isinstance(value, bytes):
        # A round trip through the other driver must not turn text into bytes
        # that no longer decode — that is the corruption this check is for.
        try:
            value = value.decode('utf-8')
        except UnicodeDecodeError:
            return 'unreadable', _SECRET_UNREADABLE_BYTES

    if not isinstance(value, str):
        return 'unreadable', _SECRET_UNREADABLE_BYTES

    if not value.strip():
        return 'empty', None

    # Integration secrets: utils.encryption (Fernet token, 'gAAAAA' prefix).
    from utils.encryption import decrypt_value, is_encrypted as is_db_encrypted

    if is_db_encrypted(value):
        try:
            cleartext = decrypt_value(value)
        except Exception:
            return 'unreadable', _SECRET_UNDECRYPTABLE
        if not cleartext:
            return 'unreadable', _SECRET_UNDECRYPTABLE
        return 'decrypted', None

    # Key material and text secrets: security.encryption ('ENC:' marker).
    from security.encryption import decrypt_text, key_encryption

    if key_encryption.is_string_encrypted(value):
        try:
            cleartext = decrypt_text(value)
        except Exception:
            return 'unreadable', _SECRET_UNDECRYPTABLE
        # decrypt_text returns its input unchanged when the key is missing or
        # the token is invalid; an actual decryption never gives that back.
        if not cleartext or cleartext == value:
            return 'unreadable', _SECRET_UNDECRYPTABLE
        return 'decrypted', None

    return 'plaintext', None


def check_secret_decryption(engine) -> Dict[str, Any]:
    """Read back a bounded sample of every encrypted column on the target.

    Encrypted columns are where a cross-backend copy hurts most quietly: PG
    hands text back as memoryview or bytes where SQLite hands str, a
    normalisation step can re-encode a value, and the row still looks complete.
    Nothing notices until a CA has to sign, an SSO login has to bind, or SMTP
    has to authenticate — all of them after the switch.

    Nothing read here is logged or returned: the report carries the table, the
    column and the verdict, never a value, encrypted or not. A value that never
    went through encryption cannot be told apart from a readable one, which is
    the honest limit of the check and the reason it counts them separately.
    """
    _force_register_all_models()

    insp, table_names = _reflect(engine)
    present_tables = set(table_names)
    cache: Dict[str, set] = {}

    columns = encrypted_columns()
    per_column: Dict[str, Dict[str, int]] = {}
    sampled = decrypted = plaintext = 0

    with _connect(engine) as conn:
        for table_name, column_name in columns:
            if table_name not in present_tables:
                raise VerificationError(
                    f"Encrypted column '{table_name}.{column_name}' cannot be "
                    f"verified: table '{table_name}' is missing from the target"
                )

            if column_name not in _columns_of(insp, table_name, cache):
                raise VerificationError(
                    f"Encrypted column '{table_name}.{column_name}' is missing "
                    "from the target"
                )

            stmt = text(
                f'SELECT {_q(column_name)} FROM {_q(table_name)} '
                f'WHERE {_q(column_name)} IS NOT NULL LIMIT :sample_limit'
            )
            try:
                rows = conn.execute(
                    stmt, {'sample_limit': _SECRET_SAMPLE_LIMIT}
                ).fetchall()
            except Exception as exc:
                raise VerificationError(
                    f"Could not read the encrypted column "
                    f"'{table_name}.{column_name}' on the target: "
                    f"{_short_err(str(exc))}"
                ) from exc

            stats = {'sampled': 0, 'decrypted': 0, 'plaintext': 0, 'empty': 0}

            for row in rows:
                verdict, reason = _probe_secret_value(row[0])
                if verdict == 'unreadable':
                    raise VerificationError(
                        f"Encrypted column '{table_name}.{column_name}' did "
                        f"not survive the copy: {reason}"
                    )
                stats['sampled'] += 1
                stats[verdict] += 1

            sampled += stats['sampled']
            decrypted += stats['decrypted']
            plaintext += stats['plaintext']

            if stats['sampled']:
                per_column[f"{table_name}.{column_name}"] = stats

    return {
        'columns_checked': len(columns),
        'values_sampled': sampled,
        'values_decrypted': decrypted,
        'values_plaintext': plaintext,
        'sample_limit': _SECRET_SAMPLE_LIMIT,
        'per_column': per_column,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def verify_migration(target_engine, expected_counts: Dict[str, int], *,
                     target_is_pg: bool) -> Dict[str, Any]:
    """Run every post-copy check on the target and return the proof.

    ``expected_counts`` is {table: rows copied}, measured during the copy under
    a consistent snapshot: the source is not re-read, it may have moved since.
    Raises VerificationError on the first check that fails. The returned
    dictionary is handed to the operator by the API as-is and recorded in the
    audit log: it is JSON-serialisable and carries no credential, no absolute
    path and no secret value — table names, column names and counts only.

    The checks run schema first, then data: an operator told "certificates is
    short of 12 rows" when the table was never created at all has been sent
    the wrong way.
    """
    dialect = getattr(target_engine.dialect, 'name', '') or 'unknown'
    engine_is_pg = dialect.startswith('postgres')

    if engine_is_pg != bool(target_is_pg):
        # Verifying the wrong database would produce a clean report about a
        # target nobody is switching to.
        raise VerificationError(
            "Verification aborted: the migration targeted "
            f"{'PostgreSQL' if target_is_pg else 'SQLite'} but the engine to "
            f"verify is '{dialect}'"
        )

    checks = (
        ('schema', lambda: check_schema(target_engine)),
        ('row_counts', lambda: check_row_counts(target_engine, expected_counts)),
        ('foreign_keys', lambda: check_foreign_keys(target_engine)),
        ('unique_constraints', lambda: check_unique_constraints(target_engine)),
        ('local_email_flags', lambda: check_local_email_flags(target_engine)),
        ('sequences', lambda: check_sequences(target_engine)),
        ('secrets', lambda: check_secret_decryption(target_engine)),
    )

    report: Dict[str, Any] = {
        'ok': False,
        'target_backend': 'postgresql' if engine_is_pg else dialect,
        'checks_run': [name for name, _ in checks],
        'checks': {},
    }

    for name, run in checks:
        try:
            report['checks'][name] = run()
        except VerificationError:
            raise
        except Exception as exc:
            # An unexpected failure is still a failure: the switch must not be
            # authorised by a check that never finished.
            logger.exception("Migration verification check '%s' crashed", name)
            raise VerificationError(
                f"Verification check '{name}' could not run: "
                f"{_short_err(str(exc))}"
            ) from exc

    # What no check could look at, gathered where a reader will see it. A
    # partial or expression-based unique index cannot be checked by a global
    # GROUP BY, and refusing every migration over one would be absurd — but
    # burying it three levels down in a per-check dictionary is how "verified"
    # comes to mean less than it says.
    report['not_verified'] = _not_verified(report['checks'])
    report['ok'] = True
    logger.info(
        "Migration verification passed on %s: %d table(s), %d row(s), "
        "%d constraint(s) not verifiable",
        report['target_backend'],
        report['checks']['row_counts']['tables'],
        report['checks']['row_counts']['rows'],
        len(report['not_verified']),
    )
    return report


def _not_verified(checks: Dict[str, Any]) -> List[Dict[str, str]]:
    """Everything a check declared it could not look at, in one list."""
    gathered: List[Dict[str, str]] = []
    for name, result in checks.items():
        if not isinstance(result, dict):
            continue
        for entry in result.get('skipped') or ():
            item = dict(entry)
            item['check'] = name
            gathered.append(item)
        for entry in result.get('dangling') or ():
            item = dict(entry)
            item['check'] = name
            gathered.append(item)
    return gathered
