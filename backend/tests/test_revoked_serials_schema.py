"""Migration 078 and the RevokedSerial model: revoked_serials table and the
renewal columns of certificates, on SQLite and PostgreSQL."""
import importlib
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

PG_URL = os.getenv('UCM_TEST_PG_URL')
INDEXES = {
    'ix_revoked_serials_caref': ['caref'],
    'ix_revoked_serials_serial_number': ['serial_number'],
    'ix_revoked_serials_certificate_id': ['certificate_id'],
}
COLUMNS = ['id', 'caref', 'serial_number', 'revoked_at', 'revoke_reason',
           'invalidity_at', 'valid_to', 'created_at', 'certificate_id']
NOT_NULL = {'id', 'caref', 'serial_number', 'revoked_at', 'valid_to'}

# Schema as it stood before 078: no revoked_serials, no renewal columns
PRE_078_SQLITE = (
    "CREATE TABLE certificate_authorities (id INTEGER PRIMARY KEY,"
    " refid VARCHAR(36) NOT NULL UNIQUE)",
    "CREATE TABLE certificates (id INTEGER PRIMARY KEY, refid VARCHAR(36) NOT NULL UNIQUE,"
    " caref VARCHAR(36) REFERENCES certificate_authorities (refid), serial_number VARCHAR(100))",
    "INSERT INTO certificate_authorities (id, refid) VALUES (1, 'ca-1')",
    "INSERT INTO certificates (id, refid, caref, serial_number) VALUES (1, 'cert-1', 'ca-1', '42')",
)
PRE_078_PG = (
    "CREATE TABLE certificate_authorities (id SERIAL PRIMARY KEY,"
    " refid VARCHAR(36) NOT NULL UNIQUE)",
    "CREATE TABLE certificates (id SERIAL PRIMARY KEY, refid VARCHAR(36) NOT NULL UNIQUE,"
    " caref VARCHAR(36) REFERENCES certificate_authorities (refid), serial_number VARCHAR(100))",
    "INSERT INTO certificate_authorities (id, refid) VALUES (1, 'ca-1')",
    "INSERT INTO certificates (id, refid, caref, serial_number) VALUES (1, 'cert-1', 'ca-1', '42')",
)


def _migration():
    return importlib.import_module('migrations.078_revoked_serials')


def _snapshot(conn, table='revoked_serials'):
    """Columns, primary key, indexes and foreign keys as the engine reports them."""
    insp = inspect(conn)
    if table not in insp.get_table_names():
        return None
    columns = {
        c['name']: (_type_name(c['type']), c['nullable'],
                    None if c.get('default') is None else str(c['default']))
        for c in insp.get_columns(table)
    }
    indexes = {i['name']: (tuple(i['column_names']), bool(i['unique']))
               for i in insp.get_indexes(table)}
    fks = sorted((tuple(f['constrained_columns']), f['referred_table'],
                  tuple(f['referred_columns'])) for f in insp.get_foreign_keys(table))
    pk = tuple(insp.get_pk_constraint(table)['constrained_columns'])
    return {'columns': columns, 'indexes': indexes, 'fks': fks, 'pk': pk}


def _type_name(sa_type):
    # str() drops the time zone flag of a PostgreSQL TIMESTAMP
    return str(sa_type) + (' WITH TIME ZONE' if getattr(sa_type, 'timezone', False) else '')


def _assert_spec_table(snap, datetime_type):
    assert snap is not None
    assert list(snap['columns']) == COLUMNS
    assert {n for n, (_t, nullable, _d) in snap['columns'].items() if not nullable} == NOT_NULL
    types = {n: t for n, (t, _nn, _d) in snap['columns'].items()}
    assert types['caref'] == 'VARCHAR(36)'
    assert types['serial_number'] == 'VARCHAR(100)'
    assert types['revoke_reason'] == 'VARCHAR(100)'
    assert types['id'] == types['certificate_id'] == 'INTEGER'
    for name in ('revoked_at', 'invalidity_at', 'valid_to', 'created_at'):
        assert types[name] == datetime_type, name
    assert snap['columns']['created_at'][2].upper() == 'CURRENT_TIMESTAMP'
    assert snap['indexes'] == {name: (tuple(cols), False) for name, cols in INDEXES.items()}
    # caref is the only foreign key; certificate_id has none
    assert snap['fks'] == [(('caref',), 'certificate_authorities', ('refid',))]
    assert snap['pk'] == ('id',)


def _assert_renewal_columns(conn, datetime_type):
    cols = {c['name']: c for c in inspect(conn).get_columns('certificates')}
    assert _type_name(cols['renewed_at']['type']) == datetime_type
    assert cols['renewed_at']['nullable'] is True
    assert cols['renewed_at'].get('default') is None
    assert str(cols['renewed_times']['type']) == 'INTEGER'
    assert cols['renewed_times']['nullable'] is False
    assert str(cols['renewed_times']['default']).strip("'") == '0'


# --------------------------------------------------------------------------
# SQLite
# --------------------------------------------------------------------------

@contextmanager
def _sqlite_db(tmp_path, statements=PRE_078_SQLITE, name='ucm.db'):
    path = tmp_path / name
    raw = sqlite3.connect(path)
    for statement in statements:
        raw.execute(statement)
    raw.commit()
    engine = create_engine(f'sqlite:///{path}')
    try:
        yield raw, engine
    finally:
        raw.close()
        engine.dispose()


def _sqlite_master(raw):
    return sorted(raw.execute("SELECT type, name, tbl_name, sql FROM sqlite_master").fetchall())


def _sqlite_snapshot(engine, table='revoked_serials'):
    with engine.connect() as conn:
        return _snapshot(conn, table)


class TestSqliteUpgrade:
    def test_creates_the_table_the_indexes_and_the_columns(self, tmp_path):
        with _sqlite_db(tmp_path) as (raw, engine):
            _migration().upgrade(raw)
            _assert_spec_table(_sqlite_snapshot(engine), 'DATETIME')
            with engine.connect() as conn:
                _assert_renewal_columns(conn, 'DATETIME')
            # An existing certificate was never renewed
            assert raw.execute(
                "SELECT renewed_at, renewed_times FROM certificates WHERE id = 1").fetchone() == (None, 0)
            sql = raw.execute("SELECT sql FROM sqlite_master WHERE name = 'revoked_serials'").fetchone()[0]
            assert 'AUTOINCREMENT' in sql.upper()

    def test_a_second_upgrade_changes_nothing(self, tmp_path):
        with _sqlite_db(tmp_path) as (raw, engine):
            _migration().upgrade(raw)
            before = _sqlite_master(raw)
            _migration().upgrade(raw)
            assert _sqlite_master(raw) == before

    def test_a_table_without_its_indexes_gets_them(self, tmp_path):
        with _sqlite_db(tmp_path) as (raw, engine):
            _migration().upgrade(raw)
            for name in INDEXES:
                raw.execute(f"DROP INDEX {name}")
            raw.commit()
            assert _sqlite_snapshot(engine)['indexes'] == {}
            _migration().upgrade(raw)
            _assert_spec_table(_sqlite_snapshot(engine), 'DATETIME')

    def test_downgrade_then_upgrade_returns_to_the_same_schema(self, tmp_path):
        with _sqlite_db(tmp_path) as (raw, engine):
            _migration().upgrade(raw)
            before = _sqlite_master(raw)
            _migration().downgrade(raw)
            assert _sqlite_snapshot(engine) is None
            _migration().upgrade(raw)
            assert _sqlite_master(raw) == before

    def test_the_table_matches_a_fresh_install(self, tmp_path):
        """Fresh installs build the schema from the models (create_all)."""
        from models import db

        with _sqlite_db(tmp_path) as (raw, migrated), _sqlite_db(tmp_path, (), 'fresh.db') as (_r, fresh):
            _migration().upgrade(raw)
            db.metadata.create_all(bind=fresh)
            assert _sqlite_snapshot(migrated) == _sqlite_snapshot(fresh)
            for engine in (migrated, fresh):
                _assert_renewal_columns_in(_sqlite_snapshot(engine, 'certificates'), 'DATETIME')

    @pytest.mark.parametrize('source', ['migration', 'model'])
    def test_constraints_hold(self, tmp_path, source):
        """valid_to is required, caref must name a CA, certificate_id is free."""
        from models.revoked_serial import RevokedSerial

        with _sqlite_db(tmp_path) as (raw, engine):
            if source == 'migration':
                _migration().upgrade(raw)
            else:
                RevokedSerial.__table__.create(bind=engine)
            raw.execute("PRAGMA foreign_keys = ON")
            _check_constraints(raw.execute, raw.commit, sqlite3.IntegrityError)
            # A deleted row id is never handed out again (AUTOINCREMENT)
            last = raw.execute("SELECT MAX(id) FROM revoked_serials").fetchone()[0]
            raw.execute("DELETE FROM revoked_serials WHERE id = ?", (last,))
            raw.execute(_INSERT_SQL, ('ca-1', '77', '2030-01-01 00:00:00', 1))
            assert raw.execute("SELECT MAX(id) FROM revoked_serials").fetchone()[0] > last


def _assert_renewal_columns_in(snap, datetime_type):
    renewed_at = snap['columns']['renewed_at']
    renewed_times = snap['columns']['renewed_times']
    assert (renewed_at[0], renewed_at[1], renewed_at[2]) == (datetime_type, True, None)
    assert (renewed_times[0], renewed_times[1]) == ('INTEGER', False)
    assert renewed_times[2].strip("'") == '0'


_INSERT_SQL = ("INSERT INTO revoked_serials (caref, serial_number, revoked_at, valid_to, certificate_id)"
               " VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)")


def _check_constraints(execute, commit, integrity_error):
    sql = _INSERT_SQL
    execute(sql, ('ca-1', '42', '2030-01-01 00:00:00', 1))
    commit()
    with pytest.raises(integrity_error):
        execute(sql, ('ca-1', '43', None, None))
    _rollback_after_error(execute)
    with pytest.raises(integrity_error):
        execute(sql, ('ghost-ca', '44', '2030-01-01 00:00:00', None))
    _rollback_after_error(execute)
    # The record outlives its certificate
    execute("DELETE FROM certificates WHERE id = 1")
    commit()
    rows = list(execute("SELECT serial_number, certificate_id, created_at FROM revoked_serials"))
    assert [(r[0], r[1]) for r in rows] == [('42', 1)]
    assert rows[0][2] is not None


def _rollback_after_error(execute):
    owner = getattr(execute, '__self__', None)
    if owner is not None and hasattr(owner, 'rollback'):
        owner.rollback()


# --------------------------------------------------------------------------
# PostgreSQL (opt-in bench)
# --------------------------------------------------------------------------

@contextmanager
def _pg_schema(suffix, statements=PRE_078_PG):
    """A private schema on the shared bench, alone on the search_path."""
    schema = f"b1_078_{suffix}_{os.getenv('PYTEST_XDIST_WORKER', 'main')}"
    engine = create_engine(PG_URL)
    conn = engine.connect()
    try:
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.execute(text(f"CREATE SCHEMA {schema}"))
        conn.execute(text(f"SET search_path TO {schema}"))
        for statement in statements:
            conn.execute(text(statement))
        conn.commit()
        yield conn
    finally:
        conn.rollback()
        conn.execute(text(f"DROP SCHEMA IF EXISTS {schema} CASCADE"))
        conn.commit()
        conn.close()
        engine.dispose()


def _pg_upgrade(conn, step='upgrade'):
    # The runner hands one transaction to the migration and commits it itself
    getattr(_migration(), step)(conn)
    conn.commit()


pg = pytest.mark.skipif(not PG_URL, reason='UCM_TEST_PG_URL not set')


@pytest.mark.postgres
@pg
class TestPostgresUpgrade:
    def test_creates_the_table_the_indexes_and_the_columns(self):
        with _pg_schema('create') as conn:
            _pg_upgrade(conn)
            _assert_spec_table(_snapshot(conn), 'TIMESTAMP')
            _assert_renewal_columns(conn, 'TIMESTAMP')
            assert conn.execute(text(
                "SELECT renewed_at, renewed_times FROM certificates WHERE id = 1")).fetchone() == (None, 0)

    def test_a_second_upgrade_changes_nothing(self):
        with _pg_schema('twice') as conn:
            _pg_upgrade(conn)
            before = (_snapshot(conn), _snapshot(conn, 'certificates'))
            _pg_upgrade(conn)
            assert (_snapshot(conn), _snapshot(conn, 'certificates')) == before

    def test_a_table_without_its_indexes_gets_them(self):
        with _pg_schema('noidx') as conn:
            _pg_upgrade(conn)
            for name in INDEXES:
                conn.execute(text(f"DROP INDEX {name}"))
            conn.commit()
            assert _snapshot(conn)['indexes'] == {}
            _pg_upgrade(conn)
            _assert_spec_table(_snapshot(conn), 'TIMESTAMP')

    def test_downgrade_then_upgrade_returns_to_the_same_schema(self):
        with _pg_schema('down') as conn:
            _pg_upgrade(conn)
            before = (_snapshot(conn), _snapshot(conn, 'certificates'))
            _pg_upgrade(conn, 'downgrade')
            assert _snapshot(conn) is None
            cols = {c['name'] for c in inspect(conn).get_columns('certificates')}
            assert not cols & {'renewed_at', 'renewed_times'}
            _pg_upgrade(conn)
            assert (_snapshot(conn), _snapshot(conn, 'certificates')) == before

    def test_the_table_matches_a_fresh_install(self):
        from models import db

        with _pg_schema('mig') as migrated, _pg_schema('fresh', ()) as fresh:
            _pg_upgrade(migrated)
            db.metadata.create_all(bind=fresh)
            fresh.commit()
            assert _snapshot(migrated) == _snapshot(fresh)
            for conn in (migrated, fresh):
                _assert_renewal_columns_in(_snapshot(conn, 'certificates'), 'TIMESTAMP')

    @pytest.mark.parametrize('source', ['migration', 'model'])
    def test_constraints_hold(self, source):
        from models.revoked_serial import RevokedSerial

        with _pg_schema(f'cons_{source}') as conn:
            if source == 'migration':
                _pg_upgrade(conn)
            else:
                RevokedSerial.__table__.create(bind=conn)
                conn.commit()
            _check_constraints(_PgExec(conn), conn.commit, IntegrityError)


class _PgExec:
    """sqlite3-style execute(sql, params) over a SQLAlchemy connection."""

    def __init__(self, conn):
        self._conn = conn

    def __call__(self, sql, params=()):
        names = [f'p{i}' for i in range(len(params))]
        for name in names:
            sql = sql.replace('?', f':{name}', 1)
        return self._conn.execute(text(sql), dict(zip(names, params)))

    @property
    def __self__(self):
        return self._conn


# --------------------------------------------------------------------------
# Model and API
# --------------------------------------------------------------------------

class TestRevokedSerialModel:
    def test_to_dict_carries_the_nine_keys_with_iso_dates(self):
        from models.revoked_serial import RevokedSerial

        row = RevokedSerial(
            id=7, caref='ca-1', serial_number='1234', revoked_at=datetime(2026, 1, 2, 3, 4, 5),
            revoke_reason='keyCompromise', invalidity_at=None,
            valid_to=datetime(2027, 1, 2, 3, 4, 5), certificate_id=None,
            created_at=datetime(2026, 1, 2, 3, 4, 6))
        data = row.to_dict()
        assert set(data) == set(COLUMNS)
        assert data['revoked_at'] == '2026-01-02T03:04:05Z'
        assert data['valid_to'] == '2027-01-02T03:04:05Z'
        assert data['created_at'] == '2026-01-02T03:04:06Z'
        assert data['invalidity_at'] is None
        assert (data['id'], data['caref'], data['serial_number'], data['revoke_reason'],
                data['certificate_id']) == (7, 'ca-1', '1234', 'keyCompromise', None)
        for key in ('revoked_at', 'valid_to', 'created_at'):
            datetime.fromisoformat(data[key].replace('Z', '+00:00'))

    def test_exported_by_the_package(self):
        import models
        from models.revoked_serial import RevokedSerial

        assert models.RevokedSerial is RevokedSerial
        assert 'RevokedSerial' in models.__all__

    def test_no_relationship_to_certificate(self):
        from sqlalchemy import inspect as sa_inspect
        from models.revoked_serial import RevokedSerial

        assert list(sa_inspect(RevokedSerial).relationships) == []

    def test_defaults_and_survival_in_the_app_database(self, app, create_cert):
        from models import db, Certificate
        from models.revoked_serial import RevokedSerial

        cert = create_cert()
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            record = RevokedSerial(caref=row.caref, serial_number='b1-' + str(row.serial_number),
                                   valid_to=datetime(2030, 1, 1), certificate_id=row.id)
            db.session.add(record)
            db.session.commit()
            record_id = record.id
            assert record.revoked_at is not None and record.created_at is not None
            assert record.revoked_at.tzinfo is None
            # The record is not tied to the certificate row
            db.session.delete(row)
            db.session.commit()
            db.session.expire_all()
            kept = db.session.get(RevokedSerial, record_id)
            assert kept is not None and kept.certificate_id == cert['id']
            db.session.delete(kept)
            db.session.commit()

    def test_valid_to_is_required_in_the_app_database(self, app, create_ca):
        from models import db
        from models.revoked_serial import RevokedSerial

        ca = create_ca()
        with app.app_context():
            db.session.add(RevokedSerial(caref=ca['refid'], serial_number='b1-no-valid-to'))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


class TestCertificateRenewalFields:
    def test_a_new_certificate_was_never_renewed(self, app, auth_client, create_cert):
        from models import db

        cert = create_cert()
        assert cert['renewed_at'] is None and cert['renewed_times'] == 0
        r = auth_client.get(f"/api/v2/certificates/{cert['id']}")
        assert r.status_code == 200
        body = json.loads(r.data)
        data = body.get('data', body)
        assert data['renewed_at'] is None and data['renewed_times'] == 0
        with app.app_context():
            # The suite's own database, not the one ucm.env names
            assert '/opt/ucm' not in str(db.engine.url)
            stored = db.session.execute(text(
                "SELECT renewed_at, renewed_times FROM certificates WHERE id = :i"),
                {'i': cert['id']}).fetchone()
        assert tuple(stored) == (None, 0)

    def test_renewed_at_is_exposed_in_iso_8601(self, app, create_cert):
        from models import db, Certificate

        cert = create_cert()
        with app.app_context():
            row = db.session.get(Certificate, cert['id'])
            row.renewed_at = datetime(2026, 5, 6, 7, 8, 9)
            row.renewed_times = 2
            db.session.commit()
            data = db.session.get(Certificate, cert['id']).to_dict()
        assert data['renewed_at'] == '2026-05-06T07:08:09Z'
        assert data['renewed_times'] == 2

    def test_an_unsaved_certificate_reports_zero_renewals(self, app):
        from models import Certificate

        with app.app_context():
            data = Certificate(refid='b1-unsaved', descr='unsaved').to_dict()
        assert data['renewed_at'] is None and data['renewed_times'] == 0
