"""Migration 157 adds certificates.subject_key, filled from crt, and its index with caref;
it is idempotent on both backends."""
import base64
import importlib
import os
import sqlite3

import pytest
from cryptography import x509
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, inspect, text

from tests.dashboard_pem import self_signed
from utils.dn_match import name_key

PG_URL = os.getenv('UCM_TEST_PG_URL')
INDEX = 'ix_certificates_caref_subject_key'


def _migration():
    return importlib.import_module('migrations._from_2_254.157_certificate_subject_key')


def _key(cn):
    return name_key(x509.Name([x509.NameAttribute(x509.oid.NameOID.COMMON_NAME, cn)]))


def _rows():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return [(1, self_signed(key, cn='Alice Martin')), (2, self_signed(key, cn='alice  martin')),
            (3, self_signed(key, cn='WIN11-WiFi')), (4, base64.b64encode(b'not a certificate').decode()),
            (5, None)]


EXPECTED = [(1, _key('Alice Martin')), (2, _key('Alice Martin')), (3, _key('win11-wifi')), (4, None), (5, None)]


def test_the_table_is_the_model_s():
    from models import Certificate
    assert Certificate.__tablename__ == 'certificates'
    assert INDEX in {i.name for i in Certificate.__table__.indexes}


def test_sqlite_backfills_and_indexes_idempotently(monkeypatch):
    monkeypatch.setattr(_migration(), '_BATCH', 2)  # several batches over five rows
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref VARCHAR(36), crt TEXT)')
    conn.executemany('INSERT INTO certificates (id, crt) VALUES (?, ?)', _rows())
    _migration().upgrade(conn)
    _migration().upgrade(conn)
    assert conn.execute('SELECT id, subject_key FROM certificates ORDER BY id').fetchall() == EXPECTED
    assert [r[2] for r in conn.execute(f'PRAGMA index_info({INDEX})')] == ['caref', 'subject_key']


def test_sqlite_without_the_table_is_a_no_op():
    conn = sqlite3.connect(':memory:')
    _migration().upgrade(conn)
    assert conn.execute('SELECT count(*) FROM sqlite_master').fetchone()[0] == 0


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_backfills_and_indexes_idempotently(monkeypatch):
    from tests.conftest import pg_bench_exclusive
    monkeypatch.setattr(_migration(), '_BATCH', 2)
    with pg_bench_exclusive():
        _postgres_round()


def _postgres_round():
    schema = f"migtest_157_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        conn.execute(text('CREATE TABLE certificates (id SERIAL PRIMARY KEY, caref VARCHAR(36), crt TEXT)'))
        conn.execute(text('INSERT INTO certificates (id, crt) VALUES (:id, :crt)'),
                     [{'id': i, 'crt': c} for i, c in _rows()])
        _migration().upgrade(conn)
        _migration().upgrade(conn)
        assert conn.execute(text('SELECT id, subject_key FROM certificates ORDER BY id')).fetchall() == EXPECTED
        indexes = {i['name']: i['column_names'] for i in inspect(conn).get_indexes('certificates', schema=schema)}
        assert indexes[INDEX] == ['caref', 'subject_key']
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


def test_the_app_schema_carries_the_column_and_index(app):
    from models import db
    with app.app_context():
        inspector = inspect(db.engine)
        assert 'subject_key' in {c['name'] for c in inspector.get_columns('certificates')}
        assert INDEX in {i['name'] for i in inspector.get_indexes('certificates')}


@pytest.mark.slow
def test_the_backfill_of_100000_certificates_is_measured(tmp_path, capsys):
    """pins the SQLite duration of the backfill (printed with -s); proves no fix.
    Each stored certificate is parsed once, in batches: the cost grows linearly with the table."""
    import time
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pems = [self_signed(key, cn=f'host-{i}.measure.test') for i in range(50)]
    conn = sqlite3.connect(tmp_path / 'measure.db')
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref VARCHAR(36), crt TEXT)')
    conn.executemany('INSERT INTO certificates (id, caref, crt) VALUES (?, ?, ?)',
                     ((i, 'ca-measure', pems[i % len(pems)]) for i in range(1, 100_001)))
    conn.commit()
    started = time.monotonic()
    _migration().upgrade(conn)
    elapsed = time.monotonic() - started
    with capsys.disabled():
        print(f'\nmigration 157: 100000 certificates backfilled in {elapsed:.1f} s')
    assert conn.execute('SELECT count(*) FROM certificates WHERE subject_key IS NULL').fetchone()[0] == 0
    assert elapsed < 600


@pytest.mark.slow
@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_the_backfill_of_100000_certificates_is_measured_on_postgresql(capsys):
    """pins the PostgreSQL duration of the backfill (printed with -s); proves no fix."""
    import time
    from tests.conftest import pg_bench_exclusive
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pems = [self_signed(key, cn=f'host-{i}.measure.test') for i in range(50)]
    schema = f"measure_157_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    with pg_bench_exclusive(), engine.connect() as conn:
        try:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            conn.execute(text('CREATE TABLE pems (n INTEGER PRIMARY KEY, crt TEXT)'))
            conn.execute(text('INSERT INTO pems (n, crt) VALUES (:n, :crt)'),
                         [{'n': n, 'crt': crt} for n, crt in enumerate(pems)])
            conn.execute(text('CREATE TABLE certificates (id SERIAL PRIMARY KEY, caref VARCHAR(36), crt TEXT)'))
            conn.execute(text("INSERT INTO certificates (id, caref, crt) SELECT g, 'ca-measure', p.crt "
                              "FROM generate_series(1, 100000) g JOIN pems p ON p.n = g % 50"))
            conn.commit()
            conn.execute(text(f'SET search_path TO {schema}'))
            started = time.monotonic()
            _migration().upgrade(conn)
            conn.commit()
            elapsed = time.monotonic() - started
            with capsys.disabled():
                print(f'\nmigration 157 on PostgreSQL: 100000 certificates backfilled in {elapsed:.1f} s')
            conn.execute(text(f'SET search_path TO {schema}'))
            assert conn.execute(text('SELECT count(*) FROM certificates WHERE subject_key IS NULL')).scalar() == 0
            assert elapsed < 600
        finally:
            conn.rollback()
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
            conn.commit()
    engine.dispose()


# --- Holders: the form 2.254 data is read with, and its cost --------------------------------

ORDER_INDEX = 'ix_acme_orders_certificate_id'
# The statements of the step as first written, kept here to compare the step's result with
_OLD_ACME = ("UPDATE certificates SET subject_holder = 'acme:' || (SELECT o.account_id FROM acme_orders o "
             "WHERE o.certificate_id = certificates.id ORDER BY o.id LIMIT 1) "
             "WHERE subject_holder IS NULL AND EXISTS "
             "(SELECT 1 FROM acme_orders o WHERE o.certificate_id = certificates.id)")
_OLD_PAIR = ("UPDATE certificates SET subject_holder = 'cert:' || (SELECT a.refid FROM certificates a "
             "WHERE a.id = certificates.related_certificate_id) "
             "WHERE subject_holder IS NULL AND hybrid_role = 'pq' AND related_certificate_id IS NOT NULL "
             "AND EXISTS (SELECT 1 FROM certificates a WHERE a.id = certificates.related_certificate_id)")
_HOLDER_TABLES = (
    'CREATE TABLE certificates (id INTEGER PRIMARY KEY, refid VARCHAR(36), caref VARCHAR(36), crt TEXT, '
    'subject_holder VARCHAR(100), hybrid_role VARCHAR(16), related_certificate_id INTEGER)',
    'CREATE TABLE acme_orders (id INTEGER PRIMARY KEY, account_id VARCHAR(64), certificate_id INTEGER)',
)
# id, refid, subject_holder, hybrid_role, related_certificate_id
_HOLDER_CERTS = [
    (1, 'r1', None, None, None),        # two orders: the lowest order id names the account
    (2, 'r2', None, None, None),        # its only order has no account
    (3, 'r3', 'manual:kept', None, None),  # already named: left as it is
    (4, 'r4', None, None, None),        # no order
    (5, 'r5', None, 'classical', 6),    # the classical member of a pair
    (6, 'r6', None, 'pq', 5),           # its post-quantum member takes the classical one's lineage
    (7, 'r7', None, 'pq', 999),         # names a certificate that is gone
    (8, 'r8', None, 'pq', 1),           # pq member issued through ACME: the order wins
    (9, 'r9', 'cert:old', 'pq', 5),     # already named
    (10, 'r10', None, 'classical', 5),  # not the pq member
]
_HOLDER_ORDERS = [(20, 'acct-b', 1), (11, 'acct-z', 1), (30, 'acct-c', 1), (12, None, 2),
                  (13, 'acct-k', 3), (14, None, None), (15, 'acct-p', 8)]
EXPECTED_HOLDERS = [(1, 'acme:acct-z'), (2, None), (3, 'manual:kept'), (4, None), (5, None),
                    (6, 'cert:r5'), (7, None), (8, 'acme:acct-p'), (9, 'cert:old'), (10, None)]


def _holder_db():
    conn = sqlite3.connect(':memory:')
    for ddl in _HOLDER_TABLES:
        conn.execute(ddl)
    conn.executemany('INSERT INTO certificates (id, refid, subject_holder, hybrid_role, related_certificate_id) '
                     'VALUES (?, ?, ?, ?, ?)', _HOLDER_CERTS)
    conn.executemany('INSERT INTO acme_orders (id, account_id, certificate_id) VALUES (?, ?, ?)', _HOLDER_ORDERS)
    return conn


def test_sqlite_holders_match_the_first_form_row_for_row():
    old, new = _holder_db(), _holder_db()
    old.execute(_OLD_ACME)
    old.execute(_OLD_PAIR)
    _migration().upgrade(new)
    _migration().upgrade(new)
    query = 'SELECT id, subject_holder FROM certificates ORDER BY id'
    assert new.execute(query).fetchall() == old.execute(query).fetchall() == EXPECTED_HOLDERS


def test_sqlite_holders_never_scan_the_orders_per_certificate():
    conn = _holder_db()
    _migration().upgrade(conn)
    plan = [row[3] for row in conn.execute('EXPLAIN QUERY PLAN ' + _migration()._ACME_HOLDERS)]
    assert not [d for d in plan if d.startswith('SCAN o')], plan
    assert any(ORDER_INDEX in d for d in plan), plan


def _holder_cost(n):
    """SQLite virtual machine steps of the step over n certificates, every other one ordered once."""
    conn = sqlite3.connect(':memory:')
    for ddl in _HOLDER_TABLES:
        conn.execute(ddl)
    conn.executemany('INSERT INTO certificates (id, refid) VALUES (?, ?)', ((i, f'r{i}') for i in range(1, n + 1)))
    conn.executemany('INSERT INTO acme_orders (account_id, certificate_id) VALUES (?, ?)',
                     ((f'acct-{i % 13}', i) for i in range(1, n + 1, 2)))
    steps = [0]

    def count():
        steps[0] += 1
        return 0
    conn.set_progress_handler(count, 100)
    _migration().upgrade(conn)
    return steps[0]


def test_sqlite_holders_cost_grows_linearly_with_the_table():
    # Four times the rows: about four times the work, sixteen for a scan per row
    assert _holder_cost(4000) < 6 * _holder_cost(1000)


def test_the_order_index_is_the_model_s():
    from models.acme_models import AcmeOrder
    assert AcmeOrder.__tablename__ == 'acme_orders'
    assert {i.name: [c.name for c in i.columns] for i in AcmeOrder.__table__.indexes}[ORDER_INDEX] == \
        ['certificate_id']


@pytest.mark.postgres
@pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')
def test_postgres_holders_match_the_first_form_and_use_the_index():
    from tests.conftest import pg_bench_exclusive
    with pg_bench_exclusive():
        old = _postgres_holders(lambda conn: (conn.execute(text(_OLD_ACME)), conn.execute(text(_OLD_PAIR))), 'old')
        new = _postgres_holders(lambda conn: (_migration().upgrade(conn), _migration().upgrade(conn)), 'new',
                                plan=True)
    assert new == old == EXPECTED_HOLDERS


def _postgres_holders(run, label, plan=False):
    schema = f"migtest_157_{label}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.execute(text(f'CREATE SCHEMA {schema}'))
        conn.execute(text(f'SET search_path TO {schema}'))
        for ddl in _HOLDER_TABLES:
            conn.execute(text(ddl))
        conn.execute(text('INSERT INTO certificates (id, refid, subject_holder, hybrid_role, related_certificate_id) '
                          'VALUES (:i, :r, :h, :role, :rel)'),
                     [dict(zip(('i', 'r', 'h', 'role', 'rel'), row)) for row in _HOLDER_CERTS])
        conn.execute(text('INSERT INTO acme_orders (id, account_id, certificate_id) VALUES (:i, :a, :c)'),
                     [dict(zip(('i', 'a', 'c'), row)) for row in _HOLDER_ORDERS])
        run(conn)
        if plan:
            # With sequential scans priced out, only an index on certificate_id avoids one per certificate
            conn.execute(text('SET LOCAL enable_seqscan = off'))
            lines = [r[0] for r in conn.execute(text('EXPLAIN ' + _migration()._ACME_HOLDERS))]
            assert not [x for x in lines if 'Seq Scan on acme_orders' in x], lines
        return conn.execute(text('SELECT id, subject_holder FROM certificates ORDER BY id')).fetchall()
    finally:
        conn.rollback()
        conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        conn.commit()
        conn.close()
        engine.dispose()


class _Clock:
    def __init__(self, step):
        self.now, self.step = 0.0, step

    def __call__(self):
        self.now += self.step
        return self.now


# The total counts the rows the loop reads (no crt: none), a resumed run only those left
@pytest.mark.parametrize('seconds,resume,lines', [(31, False, ['2 of 4', '4 of 4']), (1, False, []),
                                                  (31, True, ['2 of 2'])])
def test_sqlite_backfill_logs_its_progress_at_most_every_30_seconds(monkeypatch, capsys, seconds, resume, lines):
    import migrations._from_2_254 as package
    monkeypatch.setattr(_migration(), '_BATCH', 2)
    conn = sqlite3.connect(':memory:')
    conn.execute('CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref VARCHAR(36), crt TEXT)')
    conn.executemany('INSERT INTO certificates (id, crt) VALUES (?, ?)', _rows())
    if resume:
        _migration().upgrade(conn)
        conn.execute('UPDATE certificates SET subject_key = NULL WHERE id = 1')
        capsys.readouterr()
    monkeypatch.setattr(package, '_clock', _Clock(seconds))
    _migration().upgrade(conn)
    out = [line for line in capsys.readouterr().out.splitlines() if '157_certificate_subject_key' in line]
    assert out == [f'    step 157_certificate_subject_key: {n} rows' for n in lines]
