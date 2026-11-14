"""What a migration after the 2.254 upgrade does to a populated 3.0 database, and what of it the
release before cannot live with (CONTRIBUTING.md, "Migrations and rolling updates"). Each
migration runs through the runner on a copy of the schema it receives; the schema and the row
counts are compared before and after, never its source text."""
import re
import shutil
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import MetaData, inspect, text

from tests.upgrade_2254_support import make_base, snapshot

PIVOT = '300_upgrade_from_2_254'


def post_pivot_names(directory):
    """Migrations of *directory* numbered after the pivot, in the order the runner applies them."""
    import migration_runner
    return [f.stem for f in sorted(Path(directory).glob('*.py'))
            if not f.name.startswith('_') and migration_runner._migration_index(f.stem) > 300]


# --- Rows: one per table where a generic row fits, so a deletion shows ----------------------

def _filler(column, referred=None):
    if referred is not None:
        return _filler(referred)
    try:
        kind = column.type.python_type
    except NotImplementedError:
        kind = str
    if kind is bool:
        return False
    if kind is int:
        return 1
    if kind is float or kind is Decimal:
        return 1
    if kind is datetime:
        return datetime(2026, 1, 1)
    if kind is date:
        return date(2026, 1, 1)
    if kind is bytes:
        return b'x'
    if kind in (dict, list):
        return {}
    length = getattr(column.type, 'length', None) or 32
    return f'{column.name}1'[:length]


def _generated(table, column, dialect):
    """A value the database gives itself: sequence, identity or the SQLite rowid."""
    if column.server_default is not None or column.identity is not None:
        return True
    pk = list(table.primary_key.columns)
    return (dialect == 'sqlite' and len(pk) == 1 and pk[0] is column
            and 'INT' in str(column.type).upper())


def seed(engine):
    """One row in every table where required values alone fit; returns the tables seeded."""
    meta = MetaData()
    meta.reflect(engine)
    seeded = []
    for table in meta.sorted_tables:
        if table.name in ('_migrations', 'sqlite_sequence'):
            continue
        values = {}
        for column in table.columns:
            if column.nullable and not column.primary_key:
                continue
            if _generated(table, column, engine.dialect.name):
                continue
            referred = next((fk.column for fk in column.foreign_keys), None)
            values[column.name] = _filler(column, referred)
        try:
            with engine.begin() as conn:
                conn.execute(table.insert().values(**values))
            seeded.append(table.name)
        except Exception:  # noqa: BLE001 - a table a generic row does not fit stays empty
            continue
    return seeded


# --- Observation and comparison -------------------------------------------------------------

def observe(engine):
    """The schema snapshot of the upgrade tests, plus the row count of every table."""
    shot = snapshot(engine)
    with engine.connect() as conn:
        for table in inspect(engine).get_table_names():
            if table != 'sqlite_sequence':
                shot[('rows', table, '')] = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar()
    return shot


_BARE = re.compile(r'"?([A-Za-z_][A-Za-z0-9_]*)"?(\s+(asc|desc))?$', re.I)


def _columns_of(index_def):
    """The column names an index keys on, or None when a key is not a bare column (an expression)."""
    start = (index_def or '').find('(')
    if start < 0:
        return None
    depth, keys, key = 0, [], ''
    for ch in index_def[start + 1:]:
        if ch == ')' and depth == 0:
            break
        depth += {'(': 1, ')': -1}.get(ch, 0)
        if ch == ',' and depth == 0:
            keys.append(key)
            key = ''
        else:
            key += ch
    keys.append(key)
    bare = [_BARE.match(k.strip()) for k in keys]
    return [m.group(1) for m in bare] if all(bare) else None


def violations(before, after):
    """What *after* removes or narrows of *before*, as (kind, table, name) sorted."""
    tables_before = {k[1] for k in before if k[0] == 'table'}
    tables_after = {k[1] for k in after if k[0] == 'table'}
    cols_before = {(k[1], k[2]): v for k, v in before.items() if k[0] == 'column'}
    cols_after = {(k[1], k[2]): v for k, v in after.items() if k[0] == 'column'}
    kept = tables_before & tables_after
    out = {('drop table', t, '') for t in tables_before - tables_after}
    for (t, c), (kind, nullable, _) in cols_before.items():
        if t not in kept:
            continue
        if (t, c) not in cols_after:
            out.add(('drop column', t, c))
            continue
        kind2, nullable2, default2 = cols_after[(t, c)]
        if kind2 != kind:
            out.add(('alter type', t, c))
        if nullable and not nullable2 and default2 is None:
            out.add(('set not null', t, c))
    for (t, c), (_, nullable, default) in cols_after.items():
        if t in kept and (t, c) not in cols_before and not nullable and default is None:
            out.add(('not null column', t, c))
    for key, value in after.items():
        kind, t, name = key
        if t not in kept or before.get(key) == value:
            continue
        if kind == 'rows' and value < before[key]:
            out.add(('delete rows', t, ''))
        elif kind == 'check':
            out.add(('check', t, name))
        elif kind == 'primary key':
            out.add(('primary key', t, ''))
        elif kind in ('unique', 'foreign key'):
            if any((t, c) in cols_before for c in name.split(',')):
                out.add((kind, t, name))
        elif kind == 'index' and str(value).startswith('unique'):
            cols = _columns_of(value)
            if cols is None or any((t, c) in cols_before for c in cols):
                out.add(('unique', t, name))
    return sorted(out)


# --- One run: every post-pivot migration of a directory, one at a time ----------------------

def check(dialect, tmp_path, monkeypatch, source, label='contract'):
    """{name: (full-stop reason or None, violations)} for each post-pivot migration of *source*,
    applied by the runner in order on a populated 3.0 database of *dialect*."""
    import migration_runner
    work = Path(tmp_path) / f'{label}_migrations'
    work.mkdir()
    shutil.copy(migration_runner.MIGRATIONS_DIR / f'{PIVOT}.py', work)
    names = post_pivot_names(source)
    results = {}
    for db in make_base(dialect, tmp_path, monkeypatch, label):
        monkeypatch.setattr(migration_runner, 'MIGRATIONS_DIR', work)
        assert db.upgrade(), 'the 2.254 upgrade did not complete'
        seed(db.engine)
        for name in names:
            shutil.copy(Path(source) / f'{name}.py', work)
            before = observe(db.engine)
            assert db.upgrade(), f'{name} failed to apply'
            assert name in db.registry()
            # The reason the runner itself reads, never a second reading of the file
            reason = migration_runner.full_stop_reason(work / f'{name}.py')
            results[name] = (reason, violations(before, observe(db.engine)))
    return results


def unmarked(results):
    """The migrations that remove or narrow something without the full-stop mark."""
    return {name: found for name, (reason, found) in results.items() if found and not reason}


BACKENDS = [pytest.param('sqlite', id='sqlite'),
            pytest.param('postgresql', id='postgresql', marks=pytest.mark.postgres)]
