"""The audit chain is sealed under a key the database does not hold.

Every entry used to be sealed with SHA-256 over its own fields, which anyone
able to write the table could recompute: edit an entry, rehash it and every
entry after it, and the verification reported an intact ledger. Entries are
now sealed with HMAC-SHA256 under a key derived from the master key, and the
verification says when it cannot vouch for an entry rather than passing it.

Each test runs on an empty ledger and puts the session's rows back after, so
the whole-table checks see only what the test wrote.
"""
import importlib.util
import os
import sqlite3
import uuid
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from models import AuditLog, SystemConfig, db
from services.audit.chain import GENESIS, KEYED_CHAIN, chain_key
from services.audit.staging import stage_audit_entry
from services.audit_service import AuditService
from services.retention_service import RetentionPolicy, cleanup_audit_logs
from utils.datetime_utils import utc_now


@pytest.fixture
def empty_ledger(app):
    table = AuditLog.__table__
    with app.app_context():
        saved = [dict(row._mapping) for row in db.session.execute(table.select())]
        db.session.execute(table.delete())
        db.session.commit()
    yield
    with app.app_context():
        db.session.rollback()
        db.session.execute(table.delete())
        if saved:
            db.session.execute(table.insert(), saved)
        SystemConfig.query.filter_by(key=RetentionPolicy.CONFIG_KEY).delete()
        db.session.commit()


def _log(action, **fields):
    entry = AuditService.log_action(action=action, resource_type='system',
                                    username='chain-test', **fields)
    assert entry is not None
    return entry.id


def _legacy(action):
    """An entry as every release before this one sealed it."""
    entry = AuditLog(timestamp=utc_now(), username='chain-test', action=action,
                     resource_type='system', success=True)
    db.session.add(entry)
    db.session.flush()
    previous = (AuditLog.query.filter(AuditLog.id < entry.id)
                .order_by(AuditLog.id.desc()).first())
    entry.prev_hash = previous.entry_hash if previous else GENESIS
    entry.entry_hash = entry.compute_hash(entry.prev_hash)
    db.session.commit()
    return entry.id


def _rewrite_from(row_id, details, version, stop=None):
    """Edit one entry and reseal it, and the entries after it up to `stop`,
    with SHA-256: all that someone holding the database and not the key can
    compute. `version` 'keep' leaves each entry's hash version as it was."""
    db.session.execute(text('UPDATE audit_logs SET details = :d WHERE id = :id'),
                       {'d': details, 'id': row_id})
    db.session.commit()
    db.session.expire_all()
    previous = db.session.execute(text(
        'SELECT entry_hash FROM audit_logs WHERE id < :id ORDER BY id DESC LIMIT 1'),
        {'id': row_id}).scalar() or GENESIS
    ids = [r for (r,) in db.session.execute(text(
        'SELECT id FROM audit_logs WHERE id >= :id ORDER BY id'), {'id': row_id})]
    for current in ids:
        entry = db.session.get(AuditLog, current)
        if stop is not None and current >= stop:
            entry.prev_hash = previous     # relinked, its seal left alone
            break
        entry.prev_hash = previous
        if version != 'keep':
            entry.hash_version, entry.hash_key_id = version, None
        entry.entry_hash = entry.compute_hash(previous)
        previous = entry.entry_hash
    db.session.commit()
    db.session.expire_all()


class TestSealedUnderTheMasterKey:
    def test_an_entry_is_sealed_with_a_key_the_database_does_not_hold(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            entry = db.session.get(AuditLog, _log('chain_keyed'))
            assert entry.hash_version == KEYED_CHAIN
            assert entry.hash_key_id == chain_key()[1]
            assert entry.entry_hash != entry.compute_hash(entry.prev_hash)

            report = AuditService.verify_integrity()
            assert report['status'] == 'intact', report
            assert report['protection']['protected'] == report['checked']

    def test_an_edited_entry_breaks_the_chain_at_that_entry(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            ids = [_log(f'chain_edit_{i}') for i in range(4)]
            # resource_name and ip_address were outside the SHA-256 seal
            db.session.execute(text(
                "UPDATE audit_logs SET resource_name = 'someone else' WHERE id = :id"),
                {'id': ids[2]})
            db.session.commit()
            db.session.expire_all()
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken'
            assert report['first_error_id'] == ids[2]

    def test_rehashing_the_chain_with_sha256_does_not_pass(
            self, app, encryption_enabled, empty_ledger):
        """The attack the SHA-256 chain could not see."""
        with app.app_context():
            ids = [_log(f'chain_attack_{i}', details='granted') for i in range(5)]
            _rewrite_from(ids[2], 'refused', version='keep')
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == ids[2]

    def test_rehashing_as_old_entries_is_not_reported_intact(
            self, app, encryption_enabled, empty_ledger):
        """Downgrading the forged entries to the SHA-256 version they verify
        under: entries after the first keyed one that the key does not seal
        are reported, so the ledger never reads as protected."""
        with app.app_context():
            ids = [_log(f'chain_downgrade_{i}', details='granted') for i in range(5)]
            _rewrite_from(ids[2], 'refused', version=1)
            report = AuditService.verify_integrity()
            assert report['status'] != 'intact', report
            assert ids[2] in report['protection']['unprotected_after_key']

            # The next entry the service seals does not launder them
            _log('chain_downgrade_after')
            report = AuditService.verify_integrity()
            assert report['status'] != 'intact', report
            assert ids[2] in report['protection']['unprotected_after_key']


class TestEntriesFromBeforeTheKey:
    def test_sha256_entries_still_verify_and_are_bound_by_the_first_keyed_one(
            self, app, empty_ledger, monkeypatch, tmp_path):
        from security import encryption as enc_mod
        with app.app_context():
            legacy = [_legacy(f'chain_legacy_{i}') for i in range(3)]
            report = AuditService.verify_integrity()
            assert report['valid'] and report['status'] == 'unprotected'

            monkeypatch.setattr(enc_mod, 'MASTER_KEY_PATH', tmp_path / 'master.key')
            monkeypatch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
            enc_mod.key_encryption.reload()
            try:
                keyed = [_log(f'chain_after_upgrade_{i}') for i in range(2)]
                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                assert report['protection']['protected'] == 5
                assert report['protection']['protected_from_id'] == legacy[0]

                # Rewriting the old entries now means resealing the first keyed one
                _rewrite_from(legacy[1], 'rewritten', version=None, stop=keyed[0])
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
                assert report['first_error_id'] == keyed[0]
            finally:
                monkeypatch.delenv('KEY_ENCRYPTION_KEY')
                enc_mod.key_encryption.reload()

    def test_old_entries_removed_after_the_key_took_over_are_seen(
            self, app, empty_ledger, monkeypatch, tmp_path):
        """A ledger may open on a SHA-256 entry naming a predecessor (an older
        purge); the first keyed entry records where it opened."""
        from security import encryption as enc_mod
        with app.app_context():
            legacy = [_legacy(f'chain_legacy_cut_{i}') for i in range(3)]
            monkeypatch.setattr(enc_mod, 'MASTER_KEY_PATH', tmp_path / 'master.key')
            monkeypatch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
            enc_mod.key_encryption.reload()
            try:
                _log('chain_after_upgrade')
                AuditLog.query.filter_by(id=legacy[0]).delete()
                db.session.commit()
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
                assert report['first_error_id'] == legacy[1]
            finally:
                monkeypatch.delenv('KEY_ENCRYPTION_KEY')
                enc_mod.key_encryption.reload()

    def test_without_a_master_key_the_ledger_says_it_is_unprotected(
            self, app, empty_ledger):
        with app.app_context():
            entry = db.session.get(AuditLog, _log('chain_no_key'))
            assert entry.hash_version == 1
            report = AuditService.verify_integrity()
            assert report['valid']
            assert report['status'] == 'unprotected'
            assert report['protection']['key_available'] is False


class TestPurge:
    def _ledger(self, old=3, recent=3):
        old_ids = []
        for i in range(old):
            entry = stage_audit_entry(action=f'chain_old_{i}', resource_type='system',
                                      username='chain-test',
                                      timestamp=utc_now() - timedelta(days=400))
            old_ids.append(entry.id)
        db.session.commit()
        return old_ids, [_log(f'chain_recent_{i}') for i in range(recent)]

    def test_the_chain_verifies_after_a_purge(self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            old, recent = self._ledger()
            RetentionPolicy.update_settings(retention_days=365)
            assert cleanup_audit_logs()['deleted'] == len(old)
            record = AuditLog.query.filter_by(action='audit_purge').one()
            assert record.chain_start == recent[0]
            assert record.hash_version == KEYED_CHAIN

            report = AuditService.verify_integrity()
            assert report['status'] == 'intact', report

    def test_the_manual_cleanup_leaves_the_same_record(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            old, recent = self._ledger()
            assert AuditService.cleanup_old_logs(retention_days=90) == len(old)
            assert AuditService.verify_integrity()['status'] == 'intact'

    def test_entries_removed_past_the_purge_are_seen(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            old, recent = self._ledger()
            RetentionPolicy.update_settings(retention_days=365)
            cleanup_audit_logs()
            AuditLog.query.filter_by(id=recent[0]).delete()
            db.session.commit()
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == recent[1]

    def test_a_prefix_removed_without_a_purge_is_seen(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            ids = [_log(f'chain_prefix_{i}') for i in range(4)]
            AuditLog.query.filter(AuditLog.id <= ids[1]).delete()
            db.session.commit()
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == ids[2]

    def test_the_purge_record_cannot_be_moved(self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            old, recent = self._ledger()
            RetentionPolicy.update_settings(retention_days=365)
            cleanup_audit_logs()
            record = AuditLog.query.filter_by(action='audit_purge').one().id
            db.session.execute(text(
                'UPDATE audit_logs SET chain_start = :s WHERE id = :id'),
                {'s': recent[-1], 'id': record})
            AuditLog.query.filter(AuditLog.id < recent[-1]).delete()
            db.session.commit()
            assert AuditService.verify_integrity()['status'] == 'broken'


class TestKeyRotation:
    def test_a_new_master_key_reanchors_the_chain(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        with app.app_context():
            before = [_log(f'chain_k1_{i}') for i in range(3)]
            with monkeypatch.context() as patch:
                patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
                encryption_enabled.key_encryption.reload()
                after = [_log(f'chain_k2_{i}') for i in range(2)]

                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                assert report['protection']['retired_key'] == len(before)
                assert report['protection']['protected_from_id'] == after[0]

                # The new key's first entry recorded where the ledger started
                AuditLog.query.filter_by(id=before[0]).delete()
                db.session.commit()
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
            encryption_enabled.key_encryption.reload()


def test_the_route_reports_the_status(auth_client):
    data = auth_client.get('/api/v2/audit/verify').get_json()['data']
    assert data['status'] in ('intact', 'broken', 'unprotected')
    assert 'key_available' in data['protection']


def test_the_derived_key_is_bound_to_the_master_key_and_its_label(
        encryption_enabled, monkeypatch):
    enc = encryption_enabled.key_encryption
    first = enc.derive_key(b'ucm audit chain v2')
    assert len(first) == 32
    assert first == enc.derive_key(b'ucm audit chain v2')
    assert first != enc.derive_key(b'another label')
    with monkeypatch.context() as patch:
        patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
        enc.reload()
        assert enc.derive_key(b'ucm audit chain v2') != first
    enc.reload()


def test_no_master_key_no_derived_key(app):
    from security.encryption import key_encryption
    assert key_encryption.derive_key(b'ucm audit chain v2') is None


def _migration():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        'migrations', '098_audit_chain_keyed.py')
    spec = importlib.util.spec_from_file_location('m098', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_adds_the_columns_and_is_idempotent():
    migration = _migration()
    assert migration.pg_compatible is True
    conn = sqlite3.connect(':memory:')
    migration.upgrade(conn)     # no table yet
    conn.execute('CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, entry_hash VARCHAR(64))')
    conn.execute("INSERT INTO audit_logs VALUES (1, 'x')")
    for _ in range(2):
        migration.upgrade(conn)
    cols = {row[1] for row in conn.execute('PRAGMA table_info(audit_logs)')}
    assert {'hash_version', 'hash_key_id', 'chain_start'} <= cols
    assert conn.execute('SELECT hash_version FROM audit_logs').fetchone() == (None,)


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_the_seal_survives_a_postgresql_round_trip():
    """Migration, then an entry sealed in memory and read back from PostgreSQL."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    schema = f"m098_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    engine = create_engine(os.environ['UCM_TEST_PG_URL'])
    migration = _migration()
    key = os.urandom(32)
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET search_path TO {schema}'))
            migration.upgrade(conn)     # no table yet
            conn.execute(text('CREATE TABLE audit_logs (id INTEGER PRIMARY KEY, '
                              'timestamp TIMESTAMP, username VARCHAR(80), '
                              'action VARCHAR(100) NOT NULL, resource_type VARCHAR(50), '
                              'resource_id VARCHAR(100), resource_name VARCHAR(255), '
                              'details TEXT, ip_address VARCHAR(45), user_agent VARCHAR(255), '
                              'success BOOLEAN, prev_hash VARCHAR(64), entry_hash VARCHAR(64))'))
            migration.upgrade(conn)
            migration.upgrade(conn)
        with engine.begin() as conn:
            conn.execute(text(f'SET search_path TO {schema}'))
            entry = AuditLog(id=7, timestamp=utc_now(), username='pg', action='pg_seal',
                             resource_type='system', resource_id='1', resource_name='é|x',
                             details='{"a": 1}', ip_address='::1', user_agent='ua',
                             success=False, hash_version=KEYED_CHAIN, hash_key_id='k' * 16,
                             chain_start=7, prev_hash=GENESIS)
            entry.entry_hash = entry.compute_hash(GENESIS, key)
            with Session(bind=conn) as session:
                session.add(entry)
                session.flush()
                session.expunge_all()
                stored = session.get(AuditLog, 7)
                assert stored.compute_hash(stored.prev_hash, key) == entry.entry_hash
    finally:
        with engine.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
