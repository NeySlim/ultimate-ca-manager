"""A 2.254 database on either backend, built from tests/fixtures/schema_v2254_*.sql, and the
schema snapshot the upgrade tests compare. The PostgreSQL half needs UCM_TEST_PG_URL."""
import os
import re
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text

PG_URL = os.getenv('UCM_TEST_PG_URL')
FIXTURES = Path(__file__).parent / 'fixtures'


def schema_2254(dialect):
    return (FIXTURES / f'schema_v2254_{dialect}.sql').read_text()


class Base:
    """One database: ``run`` executes SQL and returns the rows, ``upgrade`` starts the runner."""

    def __init__(self, dialect, engine, monkeypatch, url, sqlite_path=None, options=None):
        self.dialect, self.engine, self.url, self.sqlite_path = dialect, engine, url, sqlite_path
        self.options = options
        self._monkeypatch = monkeypatch

    def run(self, sql, params=None):
        if self.dialect == 'sqlite':
            sql = re.sub(r'\bTRUE\b', '1', re.sub(r'\bFALSE\b', '0', sql))
        with self.engine.begin() as conn:
            result = conn.execute(text(sql), params or {})
            return [tuple(r) for r in result.fetchall()] if result.returns_rows else []

    def tables(self):
        return set(inspect(self.engine).get_table_names())

    def registry(self):
        if '_migrations' not in self.tables():
            return None
        return sorted(r[0] for r in self.run("SELECT name FROM _migrations"))

    def _route(self):
        """Point the runner at this database, without touching the configured one."""
        import migration_runner
        if self.dialect == 'sqlite':
            self._monkeypatch.setenv('DATABASE_URL', self.url)
        else:
            self._monkeypatch.setattr(migration_runner, '_get_db_url', lambda: self.url)
            self._monkeypatch.setattr(migration_runner, 'create_engine', lambda *a, **k: create_engine(
                self.url, hide_parameters=True, connect_args={'options': self.options}))
        return migration_runner

    def upgrade(self):
        """``run_all_migrations`` as a start runs it: True when the start may go on."""
        return self._route().run_all_migrations()

    def mark_all_applied(self):
        self._route().mark_all_applied()

    def connection(self):
        """What the runner hands a migration: sqlite3 connection or SQLAlchemy connection."""
        if self.dialect == 'sqlite':
            return sqlite3.connect(self.sqlite_path)
        return self.engine.begin()


def _pg_schema_engine(name):
    admin = create_engine(PG_URL)
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {name}"))
    engine = create_engine(PG_URL, connect_args={'options': f'-csearch_path={name}'})
    return admin, engine, f'-csearch_path={name}'


def _drop_pg_schema(admin, engine, name):
    engine.dispose()
    with admin.begin() as conn:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {name} CASCADE"))
    admin.dispose()


def make_base(dialect, tmp_path, monkeypatch, label, sql=None):
    """Context generator: a database of *dialect* holding *sql* (default: the 2.254 fixture)."""
    sql = schema_2254(dialect) if sql is None else sql
    if dialect == 'sqlite':
        path = tmp_path / f'{label}.db'
        conn = sqlite3.connect(path)
        conn.executescript(sql)
        conn.commit()
        conn.close()
        engine = create_engine(f'sqlite:///{path}')
        try:
            yield Base('sqlite', engine, monkeypatch, f'sqlite:///{path}', str(path))
        finally:
            engine.dispose()
        return
    if not PG_URL:
        pytest.skip('UCM_TEST_PG_URL not set')
    name = f"up2254_{label}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    admin, engine, options = _pg_schema_engine(name)
    if sql:
        with engine.begin() as conn:
            conn.exec_driver_sql(sql)
    try:
        yield Base('postgresql', engine, monkeypatch, PG_URL, options=options)
    finally:
        _drop_pg_schema(admin, engine, name)


BACKENDS = [pytest.param('sqlite', id='sqlite'),
            pytest.param('postgresql', id='postgresql', marks=pytest.mark.postgres)]


def fresh_metadata():
    """The tables a fresh 3.0 start creates with create_all (app.py imports the same modules)."""
    import models  # noqa: F401
    import models.rbac, models.sso, models.policy, models.hsm  # noqa: E401,F401
    import services.webhook_service  # noqa: F401
    from models import db
    return db.metadata


# --- Schema snapshot ------------------------------------------------------------------------

def _norm(sql):
    sql = (sql or '').replace('"', '').replace('`', '').replace('public.', '')
    sql = re.sub(r'\bIF NOT EXISTS\b', '', sql, flags=re.I)
    sql = re.sub(r'\s+', ' ', sql).strip().lower()
    return re.sub(r'\(\s+', '(', re.sub(r'\s+\)', ')', sql))


def _default(value):
    if value is None:
        return None
    value = str(value).strip()
    while value.startswith('(') and value.endswith(')'):
        value = value[1:-1].strip()
    if value.startswith('nextval('):
        return 'nextval'
    value = re.sub(r"::[a-z ]+$", '', value).strip("'")
    return {'false': '0', 'true': '1'}.get(value.lower(), value)


def _sqlite_keys(engine, table, pk, out):
    """Inline and table-level UNIQUE and REFERENCES clauses alike, read from the pragmas."""
    with engine.connect() as conn:
        for _, name, _, origin, _ in conn.exec_driver_sql(f'PRAGMA index_list("{table}")').fetchall():
            if origin == 'u':
                cols = [r[2] for r in conn.exec_driver_sql(f'PRAGMA index_info("{name}")')]
                out[('unique', table, ','.join(cols))] = 'unique'
        fks = {}
        for row in conn.exec_driver_sql(f'PRAGMA foreign_key_list("{table}")'):
            fks.setdefault(row[0], []).append(row)
        for rows in fks.values():
            cols = ','.join(r[3] for r in rows)
            delete = rows[0][6].upper()
            out[('foreign key', table, cols)] = (rows[0][2], tuple(r[4] for r in rows),
                                                 None if delete == 'NO ACTION' else delete)
    # An INTEGER PRIMARY KEY is the rowid: it never holds NULL, NOT NULL written or not
    if len(pk) == 1 and out[('column', table, pk[0])][0] == 'INTEGER':
        kind, _, default = out[('column', table, pk[0])]
        out[('column', table, pk[0])] = (kind, False, default)


def snapshot(engine):
    """{(kind, table, name): description} of everything the comparison covers."""
    insp = inspect(engine)
    dialect = engine.dialect.name
    out = {}
    for table in sorted(insp.get_table_names()):
        if table == 'sqlite_sequence':
            continue
        out[('table', table, '')] = 'present'
        for col in insp.get_columns(table):
            out[('column', table, col['name'])] = (
                str(col['type']).upper(), bool(col['nullable']), _default(col.get('default')))
        pk = tuple(insp.get_pk_constraint(table).get('constrained_columns') or ())
        out[('primary key', table, '')] = pk
        for ck in insp.get_check_constraints(table):
            out[('check', table, _norm(ck['sqltext']))] = 'check'
        if dialect == 'sqlite':
            _sqlite_keys(engine, table, pk, out)
            continue
        for uq in insp.get_unique_constraints(table):
            out[('unique', table, ','.join(uq['column_names']))] = 'unique'
        for fk in insp.get_foreign_keys(table):
            out[('foreign key', table, ','.join(fk['constrained_columns']))] = (
                fk['referred_table'], tuple(fk['referred_columns']),
                ((fk.get('options') or {}).get('ondelete') or '').upper() or None)
    with engine.connect() as conn:
        if dialect == 'sqlite':
            for name, table, sql in conn.execute(text(
                    "SELECT name, tbl_name, sql FROM sqlite_master WHERE type = 'index'")):
                if sql is None:
                    continue  # the automatic index of a UNIQUE or PRIMARY KEY clause
                out[('index', table, name)] = re.sub(r'^create (unique )?index \S+ on ', r'\1',
                                                     _norm(sql))
            for name, sql in conn.execute(text("SELECT name, sql FROM sqlite_master WHERE type = 'table'")):
                if name != 'sqlite_sequence':
                    out[('autoincrement', name, '')] = 'autoincrement' in (sql or '').lower()
        else:
            for table, name, sql in conn.execute(text(
                    "SELECT tablename, indexname, indexdef FROM pg_indexes WHERE schemaname = current_schema()")):
                out[('index', table, name)] = re.sub(r'^create (unique )?index \S+ on (\S+\.)?(\S+) using btree ',
                                                     r'\1\3 ', _norm(sql))
            for table, column, seq_type in conn.execute(text(
                    "SELECT t.relname, a.attname, format_type(s.seqtypid, NULL) FROM pg_depend d "
                    "JOIN pg_class c ON c.oid = d.objid AND c.relkind = 'S' "
                    "JOIN pg_sequence s ON s.seqrelid = c.oid "
                    "JOIN pg_class t ON t.oid = d.refobjid "
                    "JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid "
                    "JOIN pg_namespace n ON n.oid = t.relnamespace AND n.nspname = current_schema() "
                    "WHERE d.deptype IN ('a', 'i')")):
                out[('sequence', table, column)] = seq_type
    return out


def differences(upgraded, fresh):
    """Sorted (kind, table, name, upgraded value, fresh value) where the snapshots differ."""
    keys = set(upgraded) | set(fresh)
    return sorted((k[0], k[1], k[2], upgraded.get(k), fresh.get(k)) for k in keys
                  if upgraded.get(k) != fresh.get(k))
