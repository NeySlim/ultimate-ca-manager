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
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from models import AuditLog, SystemConfig, db
from services.audit.chain import GENESIS, KEYED_CHAIN, append_entry, chain_key
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

    def test_rehashing_as_old_entries_breaks_the_chain(
            self, app, encryption_enabled, empty_ledger):
        """Downgrading the forged entries to the SHA-256 version they verify
        under: with the key available, an entry after the first keyed one that
        the key does not seal is a break."""
        with app.app_context():
            ids = [_log(f'chain_downgrade_{i}', details='granted') for i in range(5)]
            _rewrite_from(ids[2], 'refused', version=1)
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == ids[2]
            assert report['first_error_code'] == 'not_sealed_by_key'

            # The next entry the service seals does not launder them
            _log('chain_downgrade_after')
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == ids[2]

    @pytest.mark.parametrize('where', ['prefix', 'middle'])
    def test_relabelling_entries_as_another_key_breaks_the_chain(
            self, app, encryption_enabled, empty_ledger, where):
        """Claiming an unknown key for an entry, seal left as it was, used to
        read as `sealed under a retired key` and pass."""
        with app.app_context():
            ids = [_log(f'chain_relabel_{i}', details='granted') for i in range(5)]
            forged = ids[:2] if where == 'prefix' else ids[2:3]
            _relabel(forged)
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == forged[0]


def _relabel(ids, key_id='deadbeefdeadbeef'):
    for row_id in ids:
        db.session.execute(text(
            "UPDATE audit_logs SET details = 'refused', hash_version = 2, hash_key_id = :k "
            "WHERE id = :id"),
            {'k': key_id, 'id': row_id})
    db.session.commit()
    db.session.expire_all()


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
            record = AuditLog.query.filter_by(action='audit_cleanup').one()
            assert record.chain_start == recent[0]
            assert record.hash_version == KEYED_CHAIN

            report = AuditService.verify_integrity()
            assert report['status'] == 'intact', report

    def test_the_manual_cleanup_leaves_one_sealed_record(
            self, app, encryption_enabled, empty_ledger, auth_client):
        with app.app_context():
            old, recent = self._ledger()
        r = auth_client.post('/api/v2/audit/cleanup', json={'retention_days': 90})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()['data']['deleted'] == len(old)
        with app.app_context():
            assert AuditLog.query.filter_by(action='audit_cleanup').count() == 1
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

    def test_kept_entries_relabelled_after_a_purge_are_seen(
            self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            old, recent = self._ledger()
            RetentionPolicy.update_settings(retention_days=365)
            cleanup_audit_logs()
            _relabel(recent[:2])
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == recent[0]

    def test_a_row_added_before_the_first_is_seen(self, app, encryption_enabled, empty_ledger):
        with app.app_context():
            ids = [_log(f'chain_before_{i}') for i in range(2)]
            db.session.execute(text(
                "INSERT INTO audit_logs (id, action, username, success) "
                "VALUES (:id, 'forged', 'someone', 1)"), {'id': ids[0] - 100})
            db.session.commit()
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert (report['first_error_id'], report['first_error_code']) == (
                ids[0] - 100, 'before_start')

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
            record = AuditLog.query.filter_by(action='audit_cleanup').one().id
            db.session.execute(text(
                'UPDATE audit_logs SET chain_start = :s WHERE id = :id'),
                {'s': recent[-1], 'id': record})
            AuditLog.query.filter(AuditLog.id < recent[-1]).delete()
            db.session.commit()
            assert AuditService.verify_integrity()['status'] == 'broken'


class TestKeyRotation:
    def _rotate(self, encryption_enabled, patch, gap=0):
        """Disable then enable encryption: entries in between carry no key."""
        if gap:
            patch.delenv('KEY_ENCRYPTION_KEY')
            encryption_enabled.key_encryption.reload()
            gap_ids = [_log(f'chain_gap_{i}') for i in range(gap)]
        else:
            gap_ids = []
        patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
        encryption_enabled.key_encryption.reload()
        return gap_ids

    @pytest.mark.parametrize('gap', [0, 2])
    def test_a_new_master_key_reanchors_the_chain(
            self, app, encryption_enabled, empty_ledger, monkeypatch, gap):
        with app.app_context():
            before = [_log(f'chain_k1_{i}') for i in range(3)]
            with monkeypatch.context() as patch:
                gap_ids = self._rotate(encryption_enabled, patch, gap)
                after = [_log(f'chain_k2_{i}') for i in range(2)]

                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                protection = report['protection']
                assert protection['retired_key'] == len(before)
                assert protection['key_rotation_id'] == after[0]
                # Entries written without a key just before the new one are bound by it
                assert protection['protected_from_id'] == (gap_ids or after)[0]
                assert protection['not_attested'] == len(before)
                assert protection['rotation_attested'] is True
                marker = db.session.get(AuditLog, after[0])
                old_key = db.session.get(AuditLog, before[0]).hash_key_id
                assert json.loads(marker.retired_keys) == {
                    'attested': True, 'keys': {old_key: before[-1]}}

                # The new key's first entry recorded where the ledger started
                AuditLog.query.filter_by(id=before[0]).delete()
                db.session.commit()
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
            encryption_enabled.key_encryption.reload()

    @pytest.mark.parametrize('label', ['unknown', 'retired'])
    def test_relabelling_the_whole_ledger_is_not_taken_for_a_rotation(
            self, app, encryption_enabled, empty_ledger, monkeypatch, label):
        """Every entry moved to another key, then the server writes: it knows,
        outside the database, that its key did not change, so it attests nothing."""
        with app.app_context():
            if label == 'retired':
                old = [_log(f'chain_k1_{i}') for i in range(2)]
                key_id = db.session.get(AuditLog, old[0]).hash_key_id
            else:
                key_id = 'deadbeefdeadbeef'
            with monkeypatch.context() as patch:
                if label == 'retired':
                    self._rotate(encryption_enabled, patch)
                ids = [_log(f'chain_total_{i}') for i in range(3)]
                _relabel([i for (i,) in db.session.query(AuditLog.id)], key_id=key_id)
                _log('chain_total_after')
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
                assert report['first_error_code'] in ('unattested_key', 'not_sealed_by_key')
                assert report['first_error_id'] <= ids[0]
            encryption_enabled.key_encryption.reload()

    def test_without_the_key_history_a_rotation_is_not_attested(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        """A restore on another host: the other keys are reported, not passed."""
        from services.audit.chain import keyring_path
        with app.app_context():
            before = [_log(f'chain_k1_{i}') for i in range(2)]
            keyring_path().unlink()
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                after = _log('chain_k2')
                report = AuditService.verify_integrity()
                assert report['valid'], report
                assert report['status'] == 'unprotected'
                assert report['protection']['key_rotation_id'] == after
                assert report['protection']['rotation_attested'] is False
                assert report['protection']['not_attested'] == len(before)
            encryption_enabled.key_encryption.reload()

    def test_a_rolled_back_rotation_does_not_move_the_key_history(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        with app.app_context():
            [_log(f'chain_k1_{i}') for i in range(2)]
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                stage_audit_entry(action='chain_rolled_back', resource_type='system',
                                  username='chain-test')
                db.session.rollback()
                _log('chain_k2')
                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                assert report['protection']['rotation_attested'] is True
            encryption_enabled.key_encryption.reload()

    def test_a_missing_key_history_is_rebuilt_by_the_next_entry(
            self, app, encryption_enabled, empty_ledger):
        """Entries under the key, no history (older build, recreated volume):
        the next entry writes it, so relabelling the ledger is still a break."""
        from services.audit.chain import keyring_path, read_keyring
        with app.app_context():
            [_log(f'chain_k_{i}') for i in range(2)]
            keyring_path().unlink()
            _log('chain_k_next')
            assert read_keyring() == {'current': chain_key()[1], 'history': [chain_key()[1]]}
            _relabel([i for (i,) in db.session.query(AuditLog.id)])
            _log('chain_k_after')
            assert AuditService.verify_integrity()['status'] == 'broken'

    def test_a_stale_key_history_is_brought_up_to_date(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        """A history naming another key (restored file, copied master key):
        the next entry records the key in use, and its rotation is attested."""
        from services.audit.chain import keyring_path, read_keyring
        with app.app_context():
            _log('chain_k1')
            keyring_path().write_text(json.dumps({'current': 'a' * 16, 'history': ['a' * 16]}))
            _log('chain_k1_next')
            key_id = chain_key()[1]
            assert read_keyring() == {'current': key_id, 'history': ['a' * 16, key_id]}
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                _log('chain_k2')
                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                assert report['protection']['rotation_attested'] is True
                assert report['protection']['retired_key'] == 2
            encryption_enabled.key_encryption.reload()

    def test_a_ledger_restored_on_a_host_with_its_own_key_breaks_until_the_key_changes(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        from services.audit.chain import keyring_path
        with app.app_context():
            [_log(f'chain_restored_{i}') for i in range(2)]
            with monkeypatch.context() as patch:
                # The other host: its own key, and a history that names only it
                patch.setenv('KEY_ENCRYPTION_KEY', Fernet.generate_key().decode())
                encryption_enabled.key_encryption.reload()
                own = chain_key()[1]
                keyring_path().write_text(json.dumps({'current': own, 'history': [own]}))
                _log('chain_restored_host')
                assert AuditService.verify_integrity()['status'] == 'broken'

                keyring_path().unlink()
                self._rotate(encryption_enabled, patch)
                _log('chain_restored_new_key')
                assert AuditService.verify_integrity()['status'] == 'unprotected'
            encryption_enabled.key_encryption.reload()

    def test_a_backup_from_before_a_rotation_breaks_until_the_key_changes(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        from services.audit.chain import keyring_path, read_keyring
        with app.app_context():
            [_log(f'chain_backup_{i}') for i in range(2)]
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                # The database came back from before the rotation; the history did not
                k1 = read_keyring()['current']
                keyring_path().write_text(json.dumps(
                    {'current': chain_key()[1], 'history': [k1, chain_key()[1]]}))
                _log('chain_backup_k2')
                assert AuditService.verify_integrity()['status'] == 'broken'

                self._rotate(encryption_enabled, patch)
                _log('chain_backup_k3')
                report = AuditService.verify_integrity()
                assert report['status'] == 'intact', report
                assert report['protection']['rotation_attested'] is True
            encryption_enabled.key_encryption.reload()

    def test_the_key_history_is_kept_beside_the_master_key(
            self, app, encryption_enabled, empty_ledger):
        from services.audit.chain import keyring_path, read_keyring
        with app.app_context():
            _log('chain_ring')
            path = keyring_path()
            assert path.parent == encryption_enabled.MASTER_KEY_PATH.parent
            assert path.stat().st_mode & 0o777 == 0o600
            assert read_keyring() == {'current': chain_key()[1], 'history': [chain_key()[1]]}

    def test_the_rotation_record_is_sealed(self, app, encryption_enabled, empty_ledger,
                                           monkeypatch):
        with app.app_context():
            before = [_log(f'chain_k1_{i}') for i in range(2)]
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                marker = _log('chain_k2')
                _log('chain_k2_next')
                old_key = db.session.get(AuditLog, before[0]).hash_key_id
                db.session.execute(text('UPDATE audit_logs SET retired_keys = :r WHERE id = :id'),
                                   {'r': json.dumps({'attested': True, 'keys': {old_key: 999}}),
                                    'id': marker})
                db.session.commit()
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken'
                assert (report['first_error_id'], report['first_error_code']) == (marker, 'tampered')
            encryption_enabled.key_encryption.reload()

    def test_a_deleted_rotation_record_is_named_rather_than_the_entries_behind_it(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        with app.app_context():
            [_log(f'chain_k1_{i}') for i in range(2)]
            with monkeypatch.context() as patch:
                self._rotate(encryption_enabled, patch)
                marker = _log('chain_k2')
                following = _log('chain_k2_next')
                AuditLog.query.filter_by(id=marker).delete()
                db.session.commit()
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken'
                assert (report['first_error_id'], report['first_error_code']) == (following, 'link')
            encryption_enabled.key_encryption.reload()

    def test_an_entry_relabelled_with_the_retired_key_past_its_last_entry_is_seen(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        with app.app_context():
            before = [_log(f'chain_k1_{i}') for i in range(3)]
            old_key = db.session.get(AuditLog, before[0]).hash_key_id
            with monkeypatch.context() as patch:
                gap_ids = self._rotate(encryption_enabled, patch, gap=2)
                _log('chain_k2')
                _relabel(gap_ids[1:], key_id=old_key)
                report = AuditService.verify_integrity()
                assert report['status'] == 'broken', report
                assert report['first_error_id'] == gap_ids[1]
                assert report['first_error_code'] == 'unattested_key'
            encryption_enabled.key_encryption.reload()

    def test_an_entry_written_without_the_key_after_it_took_over_is_a_break(
            self, app, encryption_enabled, empty_ledger, monkeypatch):
        with app.app_context():
            _log('chain_keyed')
            with monkeypatch.context() as patch:
                patch.delenv('KEY_ENCRYPTION_KEY')
                encryption_enabled.key_encryption.reload()
                unsealed = _log('chain_without_key')
            encryption_enabled.key_encryption.reload()
            _log('chain_keyed_again')
            report = AuditService.verify_integrity()
            assert report['status'] == 'broken', report
            assert report['first_error_id'] == unsealed
            assert report['first_error_code'] == 'not_sealed_by_key'


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
                             chain_start=7, retired_keys='{"a": 3}', prev_hash=GENESIS)
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


@contextmanager
def _pg_ledger():
    """An engine on a schema of its own on the PostgreSQL bench, holding an audit_logs table."""
    from sqlalchemy import create_engine
    schema = f"chain_{os.getenv('PYTEST_XDIST_WORKER', 'main')}_{uuid.uuid4().hex[:6]}"
    admin = create_engine(os.environ['UCM_TEST_PG_URL'])
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(os.environ['UCM_TEST_PG_URL'],
                           connect_args={'options': f'-csearch_path={schema}'})
    try:
        AuditLog.__table__.create(engine)
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        admin.dispose()


def _pg_entry(action):
    return AuditLog(timestamp=utc_now(), username='pg', action=action,
                    resource_type='system', success=True)


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_two_concurrent_appends_on_postgresql_do_not_fork():
    """The second writer waits for the first to commit, then seals on top of it."""
    from sqlalchemy.orm import Session
    with _pg_ledger() as engine:
        with Session(engine) as session:
            append_entry(_pg_entry('pg_first'), session=session)
            session.commit()
        sealed, failures = threading.Event(), []

        def writer(action, wait_for=None, hold=0.0):
            try:
                if wait_for is not None:
                    wait_for.wait(5)
                with Session(engine) as session:
                    append_entry(_pg_entry(action), session=session)
                    if wait_for is None:
                        sealed.set()
                    time.sleep(hold)
                    session.commit()
            except Exception as e:      # surfaced below
                failures.append(e)

        first = threading.Thread(target=writer, args=('pg_slow',), kwargs={'hold': 0.5})
        second = threading.Thread(target=writer, args=('pg_fast', sealed))
        first.start()
        second.start()
        first.join(10)
        second.join(10)
        assert not failures, failures
        with Session(engine) as session:
            rows = session.query(AuditLog).order_by(AuditLog.id).all()
            assert [r.action for r in rows] == ['pg_first', 'pg_slow', 'pg_fast']
            for before, after in zip(rows, rows[1:]):
                assert after.prev_hash == before.entry_hash, (
                    f'#{after.id} seals on {after.prev_hash[:12]}, not on #{before.id}')


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_a_purge_record_past_a_sequence_gap_names_itself_as_the_start():
    """Everything purged: the first id kept is the record's, wherever the sequence put it."""
    from sqlalchemy.orm import Session
    with _pg_ledger() as engine:
        with Session(engine) as session:
            for i in range(3):
                append_entry(_pg_entry(f'pg_old_{i}'), session=session)
            session.commit()
            boundary = session.query(db.func.max(AuditLog.id)).scalar() + 1
            session.scalar(text("SELECT setval(pg_get_serial_sequence('audit_logs', 'id'), 40)"))
            record = append_entry(_pg_entry('audit_cleanup'), session=session,
                                  purge_from=boundary)
            session.commit()
            assert record.id > boundary
            assert record.chain_start == record.id
