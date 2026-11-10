"""A source holding two certificates with one serial under one CA (migration 142 pending)
is refused by a backend migration and by a restore before anything is written."""
import importlib
import sqlite3
import uuid

import pytest
from sqlalchemy import create_engine, text

from models import Certificate, db
from utils.serial_duplicates import duplicates_in_database, duplicates_in_rows

from tests.test_backup_restore_failfast import PASSWORD, _forged, _service

SERIAL = '424242'


def _migration():
    return importlib.import_module('migrations.142_serial_per_ca_and_proxy_links')


def test_the_database_listing_names_each_pair_and_its_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref TEXT, serial_number TEXT)")
    conn.executemany("INSERT INTO certificates VALUES (?, ?, ?)",
                     [(1, 'ca-a', '11'), (2, 'ca-a', '11'), (3, 'ca-b', '11'), (4, 'ca-a', ''),
                      (5, 'ca-a', ''), (6, None, '12'), (7, None, '12'), (8, 'ca-a', '13')])
    conn.commit()
    engine = create_engine('sqlite://', creator=lambda: conn)
    with engine.connect() as c:
        assert duplicates_in_database(c) == [{'caref': 'ca-a', 'serial_number': '11', 'ids': [1, 2]}]
    assert duplicates_in_rows([{'refid': 'r1', 'caref': 'ca-a', 'serial_number': '11'},
                               {'refid': 'r2', 'caref': 'ca-a', 'serial_number': '11'},
                               {'refid': 'r3', 'caref': None, 'serial_number': '11'},
                               {'refid': 'r4', 'caref': 'ca-a', 'serial_number': None}]) == [
        {'caref': 'ca-a', 'serial_number': '11', 'ids': ['r1', 'r2']}]


@pytest.fixture
def duplicate_serials(app):
    """Two rows sharing a serial under one CA, as an installation with migration 142 pending holds."""
    from tests.test_crl_number_monotonic import _authority, _ca_row
    with app.app_context():
        ca = _ca_row(*_authority())
        ca_id, caref = ca.id, ca.refid
        db.session.execute(text(f'DROP INDEX {_migration().INDEX}'))
        rows = [Certificate(refid=f'dup-{uuid.uuid4().hex[:8]}-{n}', descr='duplicate serial', caref=caref,
                            serial_number=SERIAL) for n in (1, 2)]
        db.session.add_all(rows)
        db.session.commit()
        ids = [r.id for r in rows]
    try:
        yield caref, ids
    finally:
        with app.app_context():
            db.session.rollback()
            Certificate.query.filter_by(caref=caref).delete()
            db.session.execute(text('DELETE FROM certificate_authorities WHERE id = :i'), {'i': ca_id})
            db.session.execute(text(_migration().CREATE_INDEX))
            db.session.commit()


def test_a_backend_migration_refuses_a_source_with_duplicate_serials(app, duplicate_serials, tmp_path):
    from services.database_admin.migration import migrate_data
    caref, ids = duplicate_serials
    target = tmp_path / 'target.db'
    with app.app_context():
        ok, message, stats = migrate_data(f'sqlite:///{target}')
    assert not ok and stats['refusal'] == 'preflight' and stats['target_written'] is False
    assert caref in message and SERIAL in message and all(str(i) in message for i in ids)
    assert 'migration 142' in message


def test_a_restore_refuses_an_archive_with_duplicate_serials(app, create_ca):
    from services.backup.errors import BackupSchemaError
    caref = create_ca(cn=f'Dup restore {uuid.uuid4().hex[:6]}')['refid']
    refids = [f'dup-restore-{uuid.uuid4().hex[:8]}' for _ in range(2)]
    with app.app_context():
        blob = _forged(['certificates'], certificates=[
            {'refid': r, 'descr': 'duplicate serial', 'caref': caref, 'serial_number': SERIAL,
             'cert_type': 'server_cert'} for r in refids])
        try:
            with pytest.raises(BackupSchemaError) as refusal:
                _service().restore_backup(blob, PASSWORD, mode='merge')
            assert caref in str(refusal.value) and SERIAL in str(refusal.value)
            assert all(r in str(refusal.value) for r in refids)
            assert 'migration 142' in str(refusal.value)
            assert Certificate.query.filter(Certificate.refid.in_(refids)).count() == 0
        finally:
            Certificate.query.filter(Certificate.refid.in_(refids)).delete()
            db.session.commit()
