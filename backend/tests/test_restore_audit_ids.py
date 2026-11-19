"""A replacing restore gives every audit entry back under the id its seal covers.

The seal of an entry covers its id. A restore that wrote the archived entries
under ids of its own made every one of them read as tampered. Each case runs on
two installations of its own (source and target), on SQLite and on PostgreSQL,
the target's ids starting where a fresh installation's do.
"""
import os
import uuid
from contextlib import ExitStack, contextmanager

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import text

from models import AuditLog, db
from services.backup import manifest
from services.backup.restore import RestoreValidationError
from services.backup.restore.audit_ids import IMPORTED, OTHER_KEY, WITHOUT_IDS
from tests.test_backup_cross_installation import _bound_to
from tests.test_backup_hostile_corpus import _reseal
from tests.test_restore_reference_resolution_pg import _a_schema_of_our_own

_PG_URL = os.environ.get('UCM_TEST_PG_URL')
PASSWORD = 'Correct-Horse-Battery-9'
ENGINES = [
    'sqlite',
    pytest.param('postgresql', marks=[
        pytest.mark.postgres, pytest.mark.skipif(not _PG_URL, reason='UCM_TEST_PG_URL not set')]),
]


@contextmanager
def _keys(directory, master):
    """One installation's keys; `master` None: no master key at all."""
    from security import encryption as key_layer
    from utils import encryption as db_layer

    directory.mkdir(parents=True, exist_ok=True)
    patch = pytest.MonkeyPatch()
    try:
        # The audit key history lives beside the master key: one directory per installation
        patch.setattr(key_layer, 'MASTER_KEY_PATH', directory / 'master.key')
        patch.delenv('KEY_ENCRYPTION_KEY_FILE', raising=False)
        if master:
            patch.setenv('KEY_ENCRYPTION_KEY', master)
        else:
            patch.delenv('KEY_ENCRYPTION_KEY', raising=False)
        patch.setenv('UCM_DB_ENCRYPTION_KEY', Fernet.generate_key().decode('ascii'))
        db_layer.get_cipher.cache_clear()
        key_layer.key_encryption.reload()
        assert key_layer.key_encryption.is_enabled == bool(master)
        yield
    finally:
        patch.undo()
        db_layer.get_cipher.cache_clear()
        key_layer.key_encryption.reload()


class Installation:
    def __init__(self, app, url, is_postgresql, directory, master):
        self.app, self.url, self.is_postgresql = app, url, is_postgresql
        self.directory, self.master = directory, master
        self.created = False

    @contextmanager
    def on(self):
        with _keys(self.directory, self.master), \
                _bound_to(self.app, self.url, self.is_postgresql, create_schema=not self.created), \
                self.app.app_context():
            self.created = True
            try:
                yield
            finally:
                db.session.rollback()


@pytest.fixture(params=ENGINES)
def world(request, app, tmp_path):
    """`world(name, master key or None)`: an installation on a database of its own."""
    with ExitStack() as stack:
        def make(name, master=None):
            if request.param == 'sqlite':
                url = f"sqlite:///{tmp_path / name}.db"
            else:
                url = stack.enter_context(_a_schema_of_our_own(f'audit_ids_{name}_{uuid.uuid4().hex[:8]}'))
            return Installation(app, url, request.param == 'postgresql', tmp_path / name, master)
        yield make


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _log(action):
    from services.audit_service import AuditService
    entry = AuditService.log_action(action=action, resource_type='system', username='audit-ids')
    assert entry is not None, f'the entry {action} could not be written'
    return entry.id


def _entries(prefix, count):
    return [_log(f'{prefix}_{n}') for n in range(count)]


def _source_entries(count, first_id=100):
    """The source's ledger starts at `first_id`, as one a retention purge has cut does:
    a target that numbers the rows itself cannot land on the same ids by chance."""
    from services.audit.chain import append_entry
    from utils.datetime_utils import utc_now
    append_entry(AuditLog(id=first_id, timestamp=utc_now(), username='audit-ids',
                          action='source_first', resource_type='system', success=True))
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(text("SELECT setval(pg_get_serial_sequence('audit_logs', 'id'), :n)"),
                           {'n': first_id})
    db.session.commit()
    return [first_id] + _entries('source', count - 1)


def _ledger():
    return [(row.id, row.action, row.entry_hash)
            for row in AuditLog.query.order_by(AuditLog.id).all()]


def _backup():
    return _service().create_backup(
        PASSWORD, include={name: name == 'audit_logs' for name in manifest.SECTIONS})


def _restore(blob, mode='replace'):
    results = _service().restore_backup(blob, PASSWORD, mode=mode)
    db.session.expire_all()
    return results


def _verify():
    from services.audit_service import AuditService
    return AuditService.verify_integrity()


def _audit_warnings(results):
    return [w for w in results.get('warnings') or [] if 'audit log entr' in w]


def _forged(blob, mutate):
    _key, data = _service()._decrypt_framed(blob, PASSWORD)
    mutate(data['audit_logs'])
    return _reseal(blob, data)


def _without_ids(rows):
    for row in rows:
        row.pop('id', None)


def _codes(report):
    return {error['code'] for error in report['errors']}


class TestAReplacementGivesTheIdsBack:
    @pytest.mark.parametrize('keyed', [False, True], ids=['no-master-key', 'same-master-key'])
    def test_restored_entries_verify_and_later_ones_chain_on(self, world, keyed):
        master = Fernet.generate_key().decode('ascii') if keyed else None
        source, target = world('source', master), world('target', master)
        with source.on():
            _source_entries(3)
            archived = _ledger()
            blob = _backup()
        with target.on():
            # A fresh installation's own journal: its ids are the archive's ids
            _entries('target', 2)
            results = _restore(blob)

            assert _ledger() == archived
            report = _verify()
            assert report['error_count'] == 0, report['errors']
            assert _audit_warnings(results) == []

            # The counter is past the restored ids: the next entry is written and links on
            after = _log('after_restore')
            assert after > archived[-1][0]
            report = _verify()
            assert report['error_count'] == 0, report['errors']
            assert report['checked'] == len(archived) + 1
            assert report['status'] == ('intact' if keyed else 'unprotected')

    def test_a_row_here_sealed_like_an_archived_one_under_another_id_takes_its_id(self, world):
        source, target = world('source'), world('target')
        with source.on():
            _source_entries(3)
            archived = _ledger()
            blob = _backup()
            copied = {c.key: getattr(db.session.get(AuditLog, archived[1][0]), c.key)
                      for c in AuditLog.__table__.columns}
        with target.on():
            _entries('target', 4)
            db.session.add(AuditLog(**{**copied, 'id': 40}))
            db.session.commit()
            _restore(blob)

            assert _ledger() == archived
            assert _verify()['error_count'] == 0

    def test_an_unsealed_row_here_goes_even_under_an_archived_id(self, world):
        source, target = world('source'), world('target')
        with source.on():
            _source_entries(3)
            archived = _ledger()
            blob = _backup()
        with target.on():
            db.session.add(AuditLog(id=archived[1][0], action='unsealed_here'))
            db.session.add(AuditLog(id=7, action='unsealed_here'))
            db.session.commit()
            results = _restore(blob)

            assert _ledger() == archived
            assert any('without a complete entry_hash' in w for w in results['warnings'])

    def test_restoring_its_own_backup_in_place_keeps_the_ledger_verifiable(self, world):
        here = world('here')
        with here.on():
            _entries('before', 3)
            archived = _ledger()
            blob = _backup()
            _entries('since', 2)
            results = _restore(blob)

            assert _ledger() == archived
            assert _audit_warnings(results) == []
            _log('after_restore')
            assert _verify()['error_count'] == 0


class TestUnderAnotherMasterKey:
    def test_no_entry_reads_as_tampered_and_the_report_says_why_once(self, world):
        source = world('source', Fernet.generate_key().decode('ascii'))
        target = world('target', Fernet.generate_key().decode('ascii'))
        with source.on():
            _source_entries(3)
            archived = _ledger()
            blob = _backup()
        with target.on():
            _entries('target', 1)
            results = _restore(blob)

            assert _ledger() == archived
            report = _verify()
            assert report['error_count'] == 0 and report['status'] == 'unprotected', report
            assert report['protection']['retired_key'] == 3
            warnings = _audit_warnings(results)
            assert warnings == [OTHER_KEY.format(count=3)]

            # Once this server seals its own entries: one finding names the key, none the entries
            _log('after_restore')
            report = _verify()
            assert [error['code'] for error in report['errors']] == ['unattested_key'], report

    def test_a_keyless_archive_on_a_keyed_target_warns_nothing(self, world):
        source = world('source')
        target = world('target', Fernet.generate_key().decode('ascii'))
        with source.on():
            _source_entries(2)
            blob = _backup()
        with target.on():
            results = _restore(blob)
            assert _audit_warnings(results) == []
            assert 'tampered' not in _codes(_verify())


class TestAnArchiveWithoutIds:
    def test_restored_as_before_with_one_warning(self, world):
        source, target = world('source'), world('target')
        with source.on():
            _source_entries(3)
            actions = [action for _id, action, _hash in _ledger()]
            blob = _forged(_backup(), _without_ids)
        with target.on():
            _entries('target', 2)
            results = _restore(blob)

            assert [action for _id, action, _hash in _ledger()] == actions
            assert _audit_warnings(results) == [WITHOUT_IDS.format(count=3)]

    def test_entries_found_again_in_place_warn_nothing(self, world):
        here = world('here')
        with here.on():
            _entries('before', 3)
            archived = _ledger()
            blob = _forged(_backup(), _without_ids)
            results = _restore(blob)

            assert _ledger() == archived
            assert _audit_warnings(results) == []
            assert _verify()['error_count'] == 0


def _set_first(value):
    def mutate(rows):
        rows[0]['id'] = value
    return mutate


def _duplicate(rows):
    rows[1]['id'] = rows[0]['id']


def _one_without(rows):
    rows[1].pop('id')


HOSTILE = {
    'text': _set_first('7'),
    'float': _set_first(1.5),
    'boolean': _set_first(True),
    'negative': _set_first(-3),
    'zero': _set_first(0),
    'huge': _set_first(2 ** 31),
    'null': _set_first(None),
    'duplicate': _duplicate,
    'some-without': _one_without,
}


class TestAHostileIdIsRefused:
    def test_refused_before_anything_is_written(self, world):
        source, target = world('source'), world('target')
        with source.on():
            _source_entries(3)
            blob = _backup()
            forged = {name: _forged(blob, mutate) for name, mutate in HOSTILE.items()}
        with target.on():
            _entries('target', 2)
            before = _ledger()
            for name, archive in forged.items():
                for mode in ('replace', 'merge'):
                    with pytest.raises(RestoreValidationError, match='audit_logs'):
                        _restore(archive, mode)
                    db.session.rollback()
                    assert _ledger() == before, (name, mode)


class TestAMerge:
    def test_imported_entries_are_counted_in_one_warning(self, world):
        source, target = world('source'), world('target')
        with source.on():
            _source_entries(3)
            blob = _backup()
        with target.on():
            local = _entries('target', 2)
            results = _restore(blob, mode='merge')

            ledger = _ledger()
            assert [row[0] for row in ledger[:2]] == local
            assert len(ledger) == 5
            assert _audit_warnings(results) == [IMPORTED.format(count=3)]

    def test_a_merge_of_its_own_backup_warns_nothing_and_verifies(self, world):
        here = world('here')
        with here.on():
            _entries('before', 3)
            blob = _backup()
            _entries('since', 2)
            before = _ledger()
            results = _restore(blob, mode='merge')

            assert _ledger() == before
            assert _audit_warnings(results) == []
            assert _verify()['error_count'] == 0
