"""Reading the source once, consistently, without holding it in memory.

Two defects lived in the copy loop. It read every table with
``list(src.execute(...).mappings())``, so a table of half a million
certificates became half a million dictionaries in the worker's heap before a
single row reached the target. And it read those tables one after another
while the instance kept serving requests, so a certificate issued between the
read of ``certificate_authorities`` and the read of ``certificates`` arrived
on the target without its issuer, or a row was copied twice under two
different identities. Nothing in the result said so.

Both are answered by the same idea: decide *what* is being copied before
copying it. On SQLite that is the snapshot file the migration has already
taken and verified — a consistent image by construction, and reading it does
not lock the database the application is still writing to. On PostgreSQL it
is a single ``REPEATABLE READ`` transaction, which is the server's own way of
saying the same thing. Rows are then streamed out of that view and inserted
in batches, so memory stays flat whatever the size of the installation.
"""
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Tuple
import logging

from sqlalchemy import create_engine, text

from .helpers import (
    _detect_boolean_columns,
    _detect_json_columns,
    _normalize_row,
    _short_err,
    _try_disable_fks,
    _try_reenable_fks,
)
from .snapshot import read_only_uri

logger = logging.getLogger(__name__)

# Rows read from the source and handed to the target per round trip. Large
# enough that the per-statement overhead disappears, small enough that one
# batch of wide rows (a table of PEM blobs) is a few megabytes and not a few
# hundred.
BATCH_SIZE = 500


class CopyError(Exception):
    """The copy could not be completed. Message safe to return to the caller."""


@dataclass
class CopyResult:
    """What was copied, and from which view of the source."""

    source_view: str
    tables: Dict[str, int] = field(default_factory=dict)

    @property
    def rows(self) -> int:
        return sum(self.tables.values())


@contextmanager
def consistent_source(snapshot) -> Iterator[Tuple[object, str, bool]]:
    """Open a view of the source that cannot change while it is being read.

    Yields ``(connection, description, source_is_pg)``. The description is
    returned to the operator: which mechanism was used is the difference
    between a migration that can be reasoned about and one that cannot.

    On SQLite the verified snapshot is opened read-only. It is the same file
    the migration would roll back to, so what lands on the target is exactly
    what the rollback point holds — and the live database is never locked.

    On PostgreSQL the live database is read inside one ``REPEATABLE READ``
    transaction: every statement in it sees the database as of the first one,
    concurrent commits included or excluded as a whole. The dump taken
    earlier is a separate image, taken slightly before; that is not a
    contradiction, because the dump exists to restore the *source*, which
    this transaction never writes to.

    The view covers the rows, not the catalogue: the copy plan is built from
    a separate connection, before the first read establishes the snapshot. A
    schema change landing in that gap is not something this guards against —
    UCM runs its schema migrations at startup, not while serving.
    """
    if snapshot.backend == 'sqlite':
        # Read-only URI: a copy must not be able to write to the artefact it
        # would be rolled back to, not even by an accidental PRAGMA.
        url = f"sqlite:///{read_only_uri(snapshot.path)}&uri=true"
        engine = create_engine(url, hide_parameters=True)
        try:
            with engine.connect() as conn:
                yield conn, f"read-only snapshot {snapshot.path.name}", False
        finally:
            engine.dispose()
        return

    from models import db as _db

    engine = _db.engine
    conn = engine.connect().execution_options(isolation_level='REPEATABLE READ')
    try:
        with conn.begin():
            yield conn, 'REPEATABLE READ transaction on the source', True
    finally:
        conn.close()


def _select_statement(table: str, columns) -> str:
    """Name the columns instead of ``SELECT *``.

    The plan already decided which columns exist on both sides; selecting
    them by name means a column added to the source between the plan and the
    read cannot silently change the shape of the rows being inserted.
    """
    column_list = ', '.join(f'"{c}"' for c in columns)
    return f'SELECT {column_list} FROM "{table}"'


def copy_tables(source, target_engine, plan, *, source_is_pg: bool,
                target_is_pg: bool) -> CopyResult:
    """Copy every table of ``plan`` into the target, in one transaction.

    One transaction for the whole copy, because a target holding half a
    migration is a target an operator has to reason about; there is nothing to
    reason about if the failure leaves it empty.

    Returns the number of rows copied per table, counted here rather than
    re-read from the source afterwards: the source is live, and a count taken
    later would be a different number for reasons that have nothing to do with
    the migration.
    """
    from sqlalchemy import inspect as sa_inspect

    result = CopyResult(source_view='')
    target_insp = sa_inspect(target_engine)
    target_tables = set(target_insp.get_table_names())
    json_cols = _detect_json_columns(target_insp, target_tables)
    bool_cols = _detect_boolean_columns(target_insp, target_tables)
    self_links = _self_links(target_insp, {entry.name for entry in plan} & target_tables)

    # SQLite cannot change ``PRAGMA foreign_keys`` inside a transaction, and
    # the pragma belongs to the connection, not to the engine: the switch has
    # to happen on this very connection, before the copy opens its
    # transaction and after it has committed. PostgreSQL is the opposite —
    # ``SET LOCAL session_replication_role`` only exists inside one.
    connection = target_engine.connect()
    try:
        fk_disabled = False
        if not target_is_pg:
            fk_disabled = _try_disable_fks(connection, False)

        with connection.begin():
            if target_is_pg:
                fk_disabled = _try_disable_fks(connection, True)

            for entry in plan:
                try:
                    copied = _copy_one(
                        source, connection, entry,
                        source_is_pg=source_is_pg,
                        target_is_pg=target_is_pg,
                        json_cols=json_cols.get(entry.name, frozenset()),
                        bool_cols=bool_cols.get(entry.name, frozenset()),
                        self_link=self_links.get(entry.name),
                    )
                except Exception as exc:
                    logger.exception("Migration failed on table %s", entry.name)
                    raise CopyError(
                        f"Copying '{entry.name}' failed: {_short_err(str(exc))}"
                    ) from exc
                result.tables[entry.name] = copied

            if target_is_pg:
                _try_reenable_fks(connection, True, fk_disabled)

        # After the commit, so SQLite accepts the pragma and the
        # ``foreign_key_check`` it runs sees the rows that were inserted.
        if not target_is_pg:
            _try_reenable_fks(connection, False, fk_disabled)
    finally:
        connection.close()

    return result


def _self_links(inspector, tables) -> Dict[str, Tuple[List[str], List[str]]]:
    """{table: (primary key, nullable columns naming a row of the same table)}."""
    links = {}
    for table in tables:
        nullable = {c['name'] for c in inspector.get_columns(table) if c.get('nullable', True)}
        columns = [column for fk in inspector.get_foreign_keys(table)
                   if fk.get('referred_table') == table
                   for column in fk.get('constrained_columns') or [] if column in nullable]
        primary = (inspector.get_pk_constraint(table) or {}).get('constrained_columns') or []
        if columns and primary:
            links[table] = (list(primary), sorted(set(columns)))
    return links


def _copy_one(source, dst, entry, *, source_is_pg: bool, target_is_pg: bool,
              json_cols, bool_cols, self_link=None) -> int:
    """Stream one table from the source view into the target.

    A link to a row of the same table is written once every row is in: the row
    it names can come later in the read, and enforced constraints refuse it.
    """
    columns = list(entry.columns)
    primary, linked = self_link or ([], [])
    linked = [c for c in linked if c in columns]
    if linked and not all(c in columns for c in primary):
        linked = []
    pending_links: List[dict] = []
    placeholders = ', '.join(f":{c}" for c in columns)
    column_list = ', '.join(f'"{c}"' for c in columns)
    insert_sql = text(
        f'INSERT INTO "{entry.name}" ({column_list}) VALUES ({placeholders})')

    # stream_results asks the driver for a server-side cursor where it has
    # one (psycopg2); where it does not (pysqlite), the cursor is already
    # lazy and this is simply ignored.
    cursor = source.execution_options(
        stream_results=True, max_row_buffer=BATCH_SIZE,
    ).execute(text(_select_statement(entry.name, columns)))

    copied = 0
    try:
        while True:
            rows = cursor.fetchmany(BATCH_SIZE)
            if not rows:
                break
            batch: List[dict] = []
            for row in rows:
                values = _normalize_row(
                    dict(zip(columns, row)),
                    source_is_pg, target_is_pg, json_cols, bool_cols)
                row_values = {c: values.get(c) for c in columns}
                if linked and any(row_values[c] is not None for c in linked):
                    pending_links.append({**{f'k_{c}': row_values[c] for c in primary},
                                          **{f'v_{c}': row_values[c] for c in linked}})
                    row_values.update({c: None for c in linked})
                batch.append(row_values)
            dst.execute(insert_sql, batch)
            copied += len(batch)
    finally:
        cursor.close()

    if pending_links:
        assignments = ', '.join(f'"{c}" = :v_{c}' for c in linked)
        condition = ' AND '.join(f'"{c}" = :k_{c}' for c in primary)
        update_sql = text(f'UPDATE "{entry.name}" SET {assignments} WHERE {condition}')
        for start in range(0, len(pending_links), BATCH_SIZE):
            dst.execute(update_sql, pending_links[start:start + BATCH_SIZE])

    return copied


@contextmanager
def consistent_live_source() -> Iterator[Tuple[object, str, bool]]:
    """A consistent view of the live database, without a snapshot file.

    The backend switch copies only the dozen auth and configuration tables,
    and takes no dump: there is nothing to roll back on the source, which it
    never writes to. It still must not read ``users`` and ``group_members``
    at two different moments, or it can bootstrap a target with a membership
    pointing at an account that was not copied.
    """
    from models import db as _db

    engine = _db.engine
    source_is_pg = str(engine.url).startswith('postgresql')
    conn = engine.connect()
    if source_is_pg:
        conn = conn.execution_options(isolation_level='REPEATABLE READ')
    try:
        with conn.begin():
            yield conn, (
                'REPEATABLE READ transaction on the source' if source_is_pg
                else 'single read transaction on the source'
            ), source_is_pg
    finally:
        conn.close()
