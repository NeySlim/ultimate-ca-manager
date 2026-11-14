"""A migration after the 2.254 upgrade only adds, unless it carries the full-stop mark: what it
does is measured on a populated database of each backend (schema and row counts before and
after), and factice migrations of each kind show what the measure catches and what it lets by."""
import textwrap

import pytest

from tests.migration_contract_support import BACKENDS, check, post_pivot_names, unmarked


@pytest.mark.parametrize('dialect', BACKENDS)
def test_no_migration_after_the_upgrade_removes_or_narrows_without_the_mark(dialect, tmp_path,
                                                                             monkeypatch):
    import migration_runner
    results = check(dialect, tmp_path, monkeypatch, migration_runner.MIGRATIONS_DIR, 'real')
    assert set(results) == set(post_pivot_names(migration_runner.MIGRATIONS_DIR))
    assert unmarked(results) == {}, (
        'these migrations remove or narrow what the release before reads or writes: make them '
        'add only, or set requires_full_stop (CONTRIBUTING.md, "Migrations and rolling updates")')


# Each factice runs on its own table or column, in this order, on the same database
PRELUDE = '''
import re
import sqlite3

from sqlalchemy import text

pg_compatible = True


def lite(conn):
    return isinstance(conn, sqlite3.Connection)


def run(conn, *statements):
    for s in statements:
        conn.execute(s) if lite(conn) else conn.execute(text(s))


def rebuild(conn, table, edit, extra=()):
    """SQLite: *table* again from its edited CREATE statement, rows and indexes kept;
    *extra* is (column, SQL value) for each column the edit adds."""
    sql = conn.execute("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                       (table,)).fetchone()[0]
    indexes = [r[0] for r in conn.execute("SELECT sql FROM sqlite_master WHERE type = 'index' "
                                          "AND tbl_name = ? AND sql IS NOT NULL", (table,))]
    cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")')]
    new = re.sub(r'^CREATE TABLE "?' + table + r'"?', f'CREATE TABLE {table}_rebuilt', edit(sql))
    conn.execute(new)
    into = ', '.join(cols + [c for c, _ in extra])
    values = ', '.join(cols + [v for _, v in extra])
    conn.execute(f'INSERT INTO {table}_rebuilt ({into}) SELECT {values} FROM {table}')
    conn.execute(f'DROP TABLE {table}')
    conn.execute(f'ALTER TABLE {table}_rebuilt RENAME TO {table}')
    for index in indexes:
        conn.execute(index)
'''

FACTICES = {
    # Adds a nullable column, a NOT NULL column with a default, a table, an index, and a unique
    # index on the new table only: what the release before never sees
    'adds_only': '''
def upgrade(conn):
    run(conn, "ALTER TABLE websocket_relay ADD COLUMN note VARCHAR(64)",
        "ALTER TABLE websocket_relay ADD COLUMN flag INTEGER NOT NULL DEFAULT 0",
        "CREATE TABLE added_table (id INTEGER PRIMARY KEY, label VARCHAR(32))",
        "CREATE INDEX ix_websocket_relay_note ON websocket_relay (note)",
        "CREATE UNIQUE INDEX ux_added_table_label ON added_table (label)")
''',
    # Its text names DROP TABLE and RENAME, yet it only adds: a scratch table created then
    # dropped, and on SQLite the table rebuild that adds a column
    'drops_only_its_scratch': '''
def upgrade(conn):
    run(conn, "CREATE TABLE scratch_one (id INTEGER)",
        "ALTER TABLE scratch_one RENAME TO scratch_two", "DROP TABLE scratch_two")
    if lite(conn):
        rebuild(conn, 'shared_files', lambda s: s[:-1] + ', checksum VARCHAR(64))',
                extra=[('checksum', 'NULL')])
    else:
        run(conn, "ALTER TABLE shared_files ADD COLUMN checksum VARCHAR(64)")
''',
    'drops_a_table': '''
def upgrade(conn):
    run(conn, "DROP TABLE acme_nonces")
''',
    'drops_a_column': '''
def upgrade(conn):
    run(conn, "ALTER TABLE cluster_commands DROP COLUMN created_by")
''',
    'renames_a_column': '''
def upgrade(conn):
    run(conn, "ALTER TABLE crl_number_counters RENAME COLUMN updated_at TO changed_at")
''',
    'renames_a_table': '''
def upgrade(conn):
    run(conn, "ALTER TABLE related_cert_requests RENAME TO related_cert_requests_old")
''',
    'changes_a_type': '''
def upgrade(conn):
    if lite(conn):
        rebuild(conn, 'pro_sso_saml_message_ids',
                lambda s: s.replace('next_path VARCHAR(512)', 'next_path TEXT'))
    else:
        run(conn, "ALTER TABLE pro_sso_saml_message_ids ALTER COLUMN next_path TYPE TEXT")
''',
    'sets_not_null_without_default': '''
def upgrade(conn):
    run(conn, "UPDATE scheduler_requests SET requested_by = 'system' WHERE requested_by IS NULL")
    if lite(conn):
        rebuild(conn, 'scheduler_requests', lambda s: s.replace(
            'requested_by VARCHAR(255)', 'requested_by VARCHAR(255) NOT NULL'))
    else:
        run(conn, "ALTER TABLE scheduler_requests ALTER COLUMN requested_by SET NOT NULL")
''',
    # NOT NULL with a default: an insert of the release before that leaves it out still passes
    'sets_not_null_with_default': '''
def upgrade(conn):
    run(conn, "UPDATE cluster_commands SET node_id = 'all' WHERE node_id IS NULL")
    if lite(conn):
        rebuild(conn, 'cluster_commands', lambda s: s.replace(
            'node_id VARCHAR(255)', "node_id VARCHAR(255) NOT NULL DEFAULT 'all'"))
    else:
        run(conn, "ALTER TABLE cluster_commands ALTER COLUMN node_id SET DEFAULT 'all'",
            "ALTER TABLE cluster_commands ALTER COLUMN node_id SET NOT NULL")
''',
    'adds_a_required_column': '''
def upgrade(conn):
    if lite(conn):
        rebuild(conn, 'encryption_keys', lambda s: s[:-1] + ', purpose VARCHAR(8) NOT NULL)',
                extra=[('purpose', "'data'")])
    else:
        run(conn, "ALTER TABLE encryption_keys ADD COLUMN purpose VARCHAR(8) NOT NULL DEFAULT 'data'",
            "ALTER TABLE encryption_keys ALTER COLUMN purpose DROP DEFAULT")
''',
    'deletes_rows': '''
def upgrade(conn):
    run(conn, "DELETE FROM websocket_relay")
''',
    # No destructive word in its text: the statement is put together at run time
    'drops_a_column_out_of_sight': '''
def upgrade(conn):
    verb = ''.join(chr(c) for c in (68, 82, 79, 80))
    run(conn, f"ALTER TABLE encryption_keys {verb} COLUMN retire_after")
''',
    'adds_a_unique_index': '''
def upgrade(conn):
    run(conn, "CREATE UNIQUE INDEX ux_scheduler_requests_task ON scheduler_requests (task_name)")
''',
    # Its key is an expression: no column name to compare, the new uniqueness still binds 3.0
    'adds_a_unique_expression_index': '''
def upgrade(conn):
    run(conn, "CREATE UNIQUE INDEX ux_websocket_relay_note_ci ON websocket_relay (lower(note))")
''',
    'adds_a_check': '''
def upgrade(conn):
    if lite(conn):
        rebuild(conn, 'crl_number_counters', lambda s: s[:-1] + ', CHECK (last_number >= 0))')
    else:
        run(conn, "ALTER TABLE crl_number_counters ADD CONSTRAINT ck_last_number CHECK (last_number >= 0)")
''',
    'drops_a_column_marked': '''
requires_full_stop = "the relay payload moved to Redis; 3.1 nodes no longer read it"


def upgrade(conn):
    run(conn, "ALTER TABLE websocket_relay DROP COLUMN payload")
''',
}

EXPECTED = {
    'adds_only': [],
    'drops_only_its_scratch': [],
    'drops_a_table': [('drop table', 'acme_nonces', '')],
    'drops_a_column': [('drop column', 'cluster_commands', 'created_by')],
    'renames_a_column': [('drop column', 'crl_number_counters', 'updated_at')],
    'renames_a_table': [('drop table', 'related_cert_requests', '')],
    'changes_a_type': [('alter type', 'pro_sso_saml_message_ids', 'next_path')],
    'sets_not_null_without_default': [('set not null', 'scheduler_requests', 'requested_by')],
    'sets_not_null_with_default': [],
    'adds_a_required_column': [('not null column', 'encryption_keys', 'purpose')],
    'deletes_rows': [('delete rows', 'websocket_relay', '')],
    'drops_a_column_out_of_sight': [('drop column', 'encryption_keys', 'retire_after')],
    'adds_a_unique_index': [('unique', 'scheduler_requests', 'ux_scheduler_requests_task')],
    'adds_a_unique_expression_index': [('unique', 'websocket_relay', 'ux_websocket_relay_note_ci')],
    'adds_a_check': [('check', 'crl_number_counters', 'last_number >= 0')],
    'drops_a_column_marked': [('drop column', 'websocket_relay', 'payload')],
}


def _name(i, key):
    return f'{301 + i}_{key}'


@pytest.fixture(scope='module', params=BACKENDS)
def factices(request, tmp_path_factory):
    source = tmp_path_factory.mktemp('factices')
    for i, (key, body) in enumerate(FACTICES.items()):
        (source / f'{_name(i, key)}.py').write_text(PRELUDE + textwrap.dedent(body))
    with pytest.MonkeyPatch.context() as mp:
        results = check(request.param, tmp_path_factory.mktemp('run'), mp, source)
    return {key: results[_name(i, key)] for i, key in enumerate(FACTICES)}


@pytest.mark.parametrize('key', sorted(EXPECTED))
def test_each_factice_is_measured_by_what_it_does(factices, key):
    reason, found = factices[key]
    assert found == EXPECTED[key]


def test_only_the_marked_destructive_factice_passes_the_gate(factices):
    flagged = {k for k, (_, found) in factices.items() if found}
    assert set(unmarked(factices)) == flagged - {'drops_a_column_marked'}
    assert factices['drops_a_column_marked'][0].startswith('the relay payload moved')
