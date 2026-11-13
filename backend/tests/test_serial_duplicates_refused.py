"""A source holding two certificates with one serial under one CA (migration 142 pending)
is refused by a backend migration and by a restore before anything is written."""
import importlib
import sqlite3
import uuid

import pytest
from sqlalchemy import create_engine, text

from models import CA, Certificate, db
from utils.serial_duplicates import duplicates_in_database, duplicates_in_rows

from tests.test_backup_restore_failfast import PASSWORD, _forged, _service

SERIAL = '424242'


def _migration():
    return importlib.import_module('migrations._from_2_254.142_serial_per_ca_and_proxy_links')


def _states_the_procedure(message):
    """Packages ship no docs/: the message itself says how to clear the duplicates."""
    assert 'docs/' not in message and '.md' not in message
    assert 'Delete all but one' in message and 'revoked row still counts' in message
    assert "'300_upgrade_from_2_254'" in message and '_migrations' in message


def test_the_database_listing_names_each_pair_and_its_rows():
    conn = sqlite3.connect(':memory:')
    conn.execute("CREATE TABLE certificates (id INTEGER PRIMARY KEY, caref TEXT, serial_number TEXT, crt TEXT)")
    conn.executemany("INSERT INTO certificates VALUES (?, ?, ?, NULL)",
                     [(1, 'ca-a', '11'), (2, 'ca-a', '11'), (3, 'ca-b', '11'), (4, 'ca-a', ''),
                      (5, 'ca-a', ''), (6, None, '12'), (7, None, '12'), (8, 'ca-a', '13')])
    conn.commit()
    engine = create_engine('sqlite://', creator=lambda: conn)
    with engine.connect() as c:
        assert duplicates_in_database(c) == [
            {'caref': 'ca-a', 'serial_number': '11', 'ids': [1, 2], 'stored': ['11', '11']}]
    assert duplicates_in_rows([{'refid': 'r1', 'caref': 'ca-a', 'serial_number': '11'},
                               {'refid': 'r2', 'caref': 'ca-a', 'serial_number': '11'},
                               {'refid': 'r3', 'caref': None, 'serial_number': '11'},
                               {'refid': 'r4', 'caref': 'ca-a', 'serial_number': None}]) == [
        {'caref': 'ca-a', 'serial_number': '11', 'ids': ['r1', 'r2'], 'stored': ['11', '11']}]


def test_describe_gives_each_id_with_the_spelling_stored():
    from utils.serial_duplicates import describe
    pair = {'caref': 'ca-a', 'serial_number': '11', 'ids': [4, 9], 'stored': ['11', 'b']}
    assert describe([pair]) == "CA ca-a serial 11: 4 (stored as '11'), 9 (stored as 'b')"
    assert describe([{'caref': 'c', 'serial_number': '1', 'ids': [1, 2]}]) == 'CA c serial 1: 1, 2'


@pytest.fixture
def duplicate_serials(app):
    """Two rows sharing a serial under one CA, as an installation with migration 142 pending holds."""
    from tests.test_crl_number_monotonic import _authority, _ca_row
    with app.app_context():
        ca = _ca_row(*_authority())
        ca_id, caref = ca.id, ca.refid
        db.session.execute(text(f'DROP INDEX IF EXISTS {_migration().INDEX}'))
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
    assert caref in message and SERIAL in message
    assert all(f"{i} (stored as '{SERIAL}')" in message for i in ids)
    assert 'upgrade from 2.254' in message
    _states_the_procedure(message)


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
            assert all(f"{r} (stored as '{SERIAL}')" in str(refusal.value) for r in refids)
            assert 'upgrade from 2.254' in str(refusal.value)
            _states_the_procedure(str(refusal.value))
            assert Certificate.query.filter(Certificate.refid.in_(refids)).count() == 0
        finally:
            Certificate.query.filter(Certificate.refid.in_(refids)).delete()
            CA.query.filter_by(refid=caref).delete()
            db.session.commit()


def test_a_target_without_the_index_restores_an_archive_with_duplicate_serials(app, create_ca):
    """An installation whose migration 142 is pending restores its own backups."""
    caref = create_ca(cn=f'Dup pending {uuid.uuid4().hex[:6]}')['refid']
    refids = [f'dup-pending-{uuid.uuid4().hex[:8]}' for _ in range(2)]
    with app.app_context():
        db.session.execute(text(f'DROP INDEX IF EXISTS {_migration().INDEX}'))
        db.session.commit()
        blob = _forged(['certificates'], certificates=[
            {'refid': r, 'descr': 'duplicate serial', 'caref': caref, 'serial_number': SERIAL,
             'cert_type': 'server_cert'} for r in refids])
        try:
            _service().restore_backup(blob, PASSWORD, mode='merge')
            assert Certificate.query.filter(Certificate.refid.in_(refids)).count() == 2
        finally:
            db.session.rollback()
            Certificate.query.filter(Certificate.refid.in_(refids)).delete()
            CA.query.filter_by(refid=caref).delete()
            db.session.execute(text(_migration().CREATE_INDEX))
            db.session.commit()


def _pending_flag(app):
    """Generator: yields a setter for the shared `serial_unique_index_pending` row, puts the value found back."""
    import json
    from models import SystemConfig
    from utils.serial_duplicates import PENDING_KEY, check_pending_serial_index

    def write(value):
        SystemConfig.query.filter_by(key=PENDING_KEY).delete()
        if value is not None:
            db.session.add(SystemConfig(key=PENDING_KEY, value=value))
        db.session.commit()

    with app.app_context():
        row = SystemConfig.query.filter_by(key=PENDING_KEY).first()
        original = None if row is None else row.value

    def set_entries(entries):
        with app.app_context():
            write(json.dumps({'duplicates': entries}))

    yield set_entries
    with app.app_context():
        db.session.rollback()
        write(original)
    check_pending_serial_index(app)


@pytest.fixture
def pending_flag(app):
    yield from _pending_flag(app)


@pytest.mark.parametrize('before', [None, '{"duplicates": [{"caref": "ca-k", "serial_number": "5", "count": 2}]}'])
def test_the_pending_flag_fixture_puts_back_what_it_found(app, before, pending_flag):
    # The outer fixture puts back the row of the shared database once this test has replaced it
    from models import SystemConfig
    from utils.serial_duplicates import PENDING_KEY

    def stored():
        with app.app_context():
            row = SystemConfig.query.filter_by(key=PENDING_KEY).first()
            return None if row is None else row.value

    with app.app_context():
        SystemConfig.query.filter_by(key=PENDING_KEY).delete()
        if before is not None:
            db.session.add(SystemConfig(key=PENDING_KEY, value=before))
        db.session.commit()
    try:
        cycle = _pending_flag(app)
        next(cycle)(['changed'])
        assert stored() != before
        next(cycle, None)
        assert stored() == before
    finally:
        with app.app_context():
            SystemConfig.query.filter_by(key=PENDING_KEY).delete()
            db.session.commit()

def test_a_pending_serial_index_is_logged_at_start_and_shown_by_health(app, client, caplog, pending_flag):
    import logging
    from utils.serial_duplicates import PENDING_KEY, check_pending_serial_index
    pending_flag([{'caref': 'ca-a', 'serial_number': '11', 'count': 2}])
    with caplog.at_level(logging.WARNING):
        check_pending_serial_index(app)
    warning = next(r.getMessage() for r in caplog.records if PENDING_KEY in r.getMessage())
    assert '1 serial' in warning and 'CA ca-a serial 11' in warning
    _states_the_procedure(warning)
    assert client.get('/health').get_json()['serial_unique_index_pending'] == 1


def test_the_start_warning_names_the_rows_and_still_reads_an_entry_stored_without_them(app, caplog, pending_flag):
    import logging
    from utils.serial_duplicates import PENDING_KEY, check_pending_serial_index
    pending_flag([{'caref': 'ca-a', 'serial_number': '11', 'count': 2,
                   'rows': [{'id': 41, 'stored': '11'}, {'id': 57, 'stored': 'b'}]},
                  {'caref': 'ca-z', 'serial_number': '7', 'count': 2}])
    with caplog.at_level(logging.WARNING):
        check_pending_serial_index(app)
    warning = next(r.getMessage() for r in caplog.records if PENDING_KEY in r.getMessage())
    assert "41 stored as '11'" in warning and "57 stored as 'b'" in warning
    assert 'CA ca-z serial 7 x2' in warning
    assert 'certificate ids and stored spellings shown with it' in warning


def test_every_start_checks_for_a_pending_serial_index(monkeypatch):
    from tests.fresh_app import fresh_app
    started = []
    monkeypatch.setattr('utils.serial_duplicates.check_pending_serial_index', started.append)
    with fresh_app() as application:
        assert started == [application]


def test_the_pending_flag_stays_on_the_database_it_describes(app, pending_flag):
    """A backup carries no schema state: a restore must not revive the flag on a target with the index."""
    from services.backup import installation
    from utils.serial_duplicates import PENDING_KEY
    assert PENDING_KEY in installation.LOCAL_SETTINGS
    pending_flag([])
    with app.app_context():
        assert PENDING_KEY not in _service()._export_configuration(True)['settings']


def test_a_row_held_behind_a_shared_serial_is_logged_with_what_it_waits_for(app, caplog, pending_flag):
    import logging
    from utils.serial_duplicates import PENDING_KEY, check_pending_serial_index
    pending_flag([{'caref': 'ca-x', 'serial_number': 'a', 'count': 1, 'waits_for': '16'}])
    with caplog.at_level(logging.WARNING):
        check_pending_serial_index(app)
    warning = next(r.getMessage() for r in caplog.records if PENDING_KEY in r.getMessage())
    assert 'CA ca-x serial a waits for 16' in warning and 'x1' not in warning
