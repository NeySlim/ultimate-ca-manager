"""A restore the database refuses, told with the table and the row's identity.

Constraint violations, and on PostgreSQL a value longer than its column.

Read from the failed statement: once a flush fails, the session holds nothing to ask.
"""
import re
from typing import Any, Dict, List, Optional

from utils.db_errors import sqlstate

from ..errors import BackupSchemaError
from ..export_generic import load_model
from ..manifest import SECTIONS

_VALUE_LIMIT = 64
_STATEMENT = re.compile(r'\s*(INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+"?(\w+)"?', re.IGNORECASE)


class RestoreConflictError(BackupSchemaError):
    """The database refused a row of the restore; the transaction is rolled back."""


def _section_of_table(table: str) -> Optional[str]:
    for name, section in SECTIONS.items():
        try:
            if load_model(section).__table__.name == table:
                return name
        except Exception:
            continue
    return None


def _shown(value: Any) -> str:
    text = str(value)
    return text if len(text) <= _VALUE_LIMIT else text[:_VALUE_LIMIT] + '...'


def describe_row(name: str, key: Any) -> str:
    """`<section> <identity>` for a row here, by its primary key."""
    section = SECTIONS.get(name)
    if section is None:
        return f"{name} row {key}"
    try:
        from models import db
        row = db.session.get(load_model(section), key)
    except Exception:
        row = None
    if row is None:
        return f"{name} row {key}"
    return f"{name} {_identity_text(section, {field: getattr(row, field, None) for field in section.identity})}"


def _identity_text(section, values: Dict[str, Any]) -> str:
    return ', '.join(f"{field}={_shown(values.get(field))!s}" for field in section.identity)


def _columns(statement: str, kind: str) -> List[str]:
    if kind.startswith('INSERT'):
        match = re.search(r'\(([^)]*)\)\s*VALUES', statement, re.IGNORECASE)
        return [c.strip().strip('"') for c in match.group(1).split(',')] if match else []
    if kind == 'UPDATE':
        match = re.search(r'\bSET\s+(.*?)\s+WHERE\b', statement, re.IGNORECASE | re.DOTALL)
        names = [part.split('=')[0].strip().strip('"') for part in match.group(1).split(',')] if match else []
        return names + ['__key__']
    return ['__key__']


def _rows(exc, kind: str) -> List[Dict[str, Any]]:
    """Each row the failed statement wrote, as column -> value."""
    params = exc.params
    statement = exc.statement or ''
    if isinstance(params, dict):
        params = [params]
    if not isinstance(params, (list, tuple)) or not params:
        return []
    if all(isinstance(item, dict) for item in params):
        rows = []
        table = (_STATEMENT.match(statement) or [None, None, ''])[2]
        for item in params:
            numbered: Dict[str, Dict[str, Any]] = {}
            for key, value in item.items():
                base, _, index = key.rpartition('__')
                if base and index.isdigit():
                    numbered.setdefault(index, {})[base] = value
                else:
                    numbered.setdefault('', {})[key] = value
            for row in numbered.values():
                # The ORM binds an UPDATE's primary key as <table>_id
                if kind == 'UPDATE' and f'{table}_id' in row:
                    row.setdefault('__key__', row[f'{table}_id'])
            rows.extend(numbered.values())
        return rows
    if all(isinstance(item, (list, tuple)) for item in params):
        groups = list(params)
    else:
        groups = [params]
    names = _columns(statement, kind)
    rows = []
    for group in groups:
        width = len(names) or len(group)
        for start in range(0, len(group), width):
            rows.append(dict(zip(names, group[start:start + width])))
    return rows


def _unique_violation_detail(orig):
    """PostgreSQL's DETAIL for a duplicate key; any other DETAIL can quote a whole row."""
    if sqlstate(orig) != _UNIQUE_VIOLATION:
        return None
    return getattr(getattr(orig, 'diag', None), 'message_detail', None)


_UNIQUE_VIOLATION = '23505'
_STRING_TOO_LONG = '22001'


def is_value_too_long(exc) -> bool:
    """A PostgreSQL refusal of a string longer than its column (SQLite stores it)."""
    return sqlstate(getattr(exc, 'orig', None)) == _STRING_TOO_LONG


def _overlong(table: str, rows: List[Dict[str, Any]]):
    """(row, column, length, limit) of the first value longer than its column."""
    from models import db
    columns = db.metadata.tables.get(table)
    if columns is None:
        return None
    for row in rows:
        for name, value in row.items():
            column = columns.c.get(name)
            limit = getattr(getattr(column, 'type', None), 'length', None)
            if limit and isinstance(value, str) and len(value) > limit:
                return row, name, len(value), limit
    return None


def conflict_from_integrity_error(exc) -> RestoreConflictError:
    """The refusal to hand the operator for a failed restore statement."""
    statement = exc.statement or ''
    match = _STATEMENT.match(statement)
    kind = ' '.join(match.group(1).upper().split()) if match else ''
    table = match.group(2) if match else 'an unknown table'
    reason = str(getattr(exc, 'orig', exc)).strip().splitlines()[0] if str(getattr(exc, 'orig', exc)).strip() else 'a constraint'
    detail = _unique_violation_detail(getattr(exc, 'orig', None))

    section_name = _section_of_table(table) if match else None
    rows = _rows(exc, kind) if match else []
    if detail and len(rows) > 1:
        # PostgreSQL names the key: keep the rows that hold it
        found = re.search(r'Key \((.*?)\)=\((.*?)\)', detail)
        if found:
            column, value = found.group(1).split(',')[0].strip('" '), found.group(2).split(',')[0].strip()
            rows = [row for row in rows if str(row.get(column)) == value] or rows

    overlong = _overlong(table, rows) if is_value_too_long(exc) and match else None
    if overlong:
        row, column, length, limit = overlong
        rows = [row]
        reason = f"{column} is {length} characters long, the column holds {limit}"

    described = []
    if section_name is not None:
        section = SECTIONS[section_name]
        for row in rows[:3]:
            if all(field in row for field in section.identity):
                described.append(f"{section_name} {_identity_text(section, row)}")
            elif row.get('__key__') is not None:
                described.append(describe_row(section_name, row['__key__']))
    what = '; '.join(described) or (f"a row of {section_name or table}")
    if detail:
        reason = f"{reason} ({detail.strip()})"
    return RestoreConflictError(
        f"The database refused the restore at {what} (table '{table}'): {reason}. "
        "Nothing has been changed.")
