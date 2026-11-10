"""The sections of a v4 archive kept on disk: what the restore reads of them."""
import errno
import os
import stat

import pytest

from services.backup.section_store import SectionStore, section_kind, section_length


@pytest.fixture
def store(tmp_path):
    with SectionStore(str(tmp_path), capacity=1) as filled:
        filled.add_part('metadata', 0, {'schema_version': 3})
        filled.add_part('users', 0, [{'username': 'a'}, {'username': 'b'}])
        filled.add_part('users', 1, [{'username': 'c'}])
        filled.add_part('configuration', 0, {'k': 'v'})
        filled.add_part('certificates', 0, [])
        filled.seal()
        yield filled


def test_it_answers_like_the_payload_dict(store):
    assert list(store) == store.keys() == ['metadata', 'users', 'configuration', 'certificates']
    assert len(store) == 4
    assert store['users'] == [{'username': 'a'}, {'username': 'b'}, {'username': 'c'}]
    assert store.get('configuration') == {'k': 'v'}
    assert store.get('absent', 'default') == 'default'
    assert 'users' in store and 'absent' not in store
    with pytest.raises(KeyError):
        store['absent']
    assert dict(store.items()) == store.to_dict()


def test_shape_is_known_without_loading(store, monkeypatch):
    monkeypatch.setattr(SectionStore, '__getitem__',
                        lambda self, name: pytest.fail(f'{name} was loaded'))
    assert section_kind(store, 'users') == 'list'
    assert section_kind(store, 'configuration') == 'mapping'
    assert section_kind(store, 'absent') is None
    assert section_length(store, 'users') == 3
    assert section_length(store, 'certificates') == 0


def test_the_helpers_read_a_plain_dict_too():
    payload = {'users': [1, 2], 'configuration': {}, 'checksum': 'x'}
    assert section_kind(payload, 'users') == 'list'
    assert section_kind(payload, 'checksum') == 'other'
    assert section_length(payload, 'users') == 2
    assert section_length(payload, 'checksum') == 0


def test_files_are_private_and_removed_on_close(tmp_path):
    with SectionStore(str(tmp_path)) as store:
        store.add_part('users', 0, [{'username': 'a'}])
        store.seal()
        directory = store._dir
        files = os.listdir(directory)
        assert files == ['0.json']
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
        assert stat.S_IMODE(os.stat(os.path.join(directory, '0.json')).st_mode) == 0o600
    assert os.listdir(tmp_path) == []


def test_only_capacity_sections_stay_loaded(store):
    store['users']
    store['configuration']
    assert list(store._loaded) == ['configuration']


def test_a_change_made_before_eviction_survives_it(store):
    store['users'][0]['username'] = 'renamed'
    store['configuration']               # evicts users, written back
    assert 'users' not in store._loaded
    assert store['users'][0]['username'] == 'renamed'


def test_a_replaced_section_survives_eviction(store):
    store['users'] = [{'username': 'only'}]
    store['configuration']
    assert section_length(store, 'users') == 1
    assert store['users'] == [{'username': 'only'}]


def test_a_section_still_held_keeps_its_identity(store):
    """The restore plan keeps references and row ids: those must not be reloaded."""
    held = store['users']
    store['configuration']
    assert 'users' in store._loaded
    assert store['users'] is held
    held.append({'username': 'late'})
    assert section_length(store, 'users') == 4


def test_a_row_still_held_keeps_its_section_loaded(store):
    row = store['users'][1]
    store['configuration']
    assert 'users' in store._loaded
    row['username'] = 'changed after the section was dropped elsewhere'
    del row
    store['certificates']
    assert store['users'][1]['username'] == 'changed after the section was dropped elsewhere'


def test_a_value_json_cannot_hold_keeps_the_section_loaded(store):
    store['users'][0]['when'] = object()
    store['configuration']
    assert 'users' in store._loaded


def test_a_written_file_is_the_json_of_the_section(store):
    assert store._read_sealed(store._files['users']) == [
        {'username': 'a'}, {'username': 'b'}, {'username': 'c'}]


def test_a_section_cannot_arrive_twice(tmp_path):
    with SectionStore(str(tmp_path)) as store:
        store.add_part('users', 0, [])
        store.add_part('groups', 0, [])
        with pytest.raises(ValueError, match='twice'):
            store.add_part('users', 0, [])


SECRET = 'smtp-password-that-must-not-reach-the-disk'


def _disk_bytes(directory):
    found = b''
    for entry in os.listdir(directory):
        with open(os.path.join(directory, entry), 'rb') as handle:
            found += handle.read()
    return found


def test_no_section_is_written_in_clear(tmp_path):
    with SectionStore(str(tmp_path), capacity=1) as store:
        store.add_part('smtp_config', 0, [{'password': SECRET}])
        store.add_part('configuration', 0, {'token': SECRET})
        store.seal()
        assert SECRET.encode() not in _disk_bytes(store._dir)
        store['smtp_config'][0]['password'] += '-changed'
        store['configuration']             # evicts smtp_config, written back
        assert 'smtp_config' not in store._loaded
        assert SECRET.encode() not in _disk_bytes(store._dir)
        assert store['smtp_config'] == [{'password': SECRET + '-changed'}]


def test_a_store_cannot_read_another_stores_files(tmp_path):
    with SectionStore(str(tmp_path)) as first, SectionStore(str(tmp_path)) as second:
        first.add_part('users', 0, [{'username': 'a'}])
        first.seal()
        second._files['users'] = first._files['users']
        second._order.append('users')
        with pytest.raises(Exception):
            second['users']


def test_stale_stores_are_swept(tmp_path):
    from services.backup.section_store import STALE_AFTER_SECONDS, sweep_stale_stores
    stale = tmp_path / '.ucm_restore_dead'
    stale.mkdir()
    (stale / '0.json').write_bytes(b'x')
    old = os.stat(stale).st_mtime - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    live = tmp_path / '.ucm_restore_live'
    live.mkdir()
    other = tmp_path / 'unrelated'
    other.mkdir()
    os.utime(other, (old, old))

    sweep_stale_stores(str(tmp_path))

    assert sorted(os.listdir(tmp_path)) == ['.ucm_restore_live', 'unrelated']


def test_no_sweep_while_a_backup_operation_holds_the_lock(tmp_path, monkeypatch):
    from services.backup import section_store
    from services.backup.locking import BackupBusyError

    @__import__('contextlib').contextmanager
    def busy(**_kwargs):
        raise BackupBusyError('busy')
        yield

    monkeypatch.setattr('services.backup.locking.backup_operation_lock', busy)
    stale = tmp_path / '.ucm_restore_dead'
    stale.mkdir()
    old = os.stat(stale).st_mtime - section_store.STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))

    section_store.sweep_stale_stores(str(tmp_path))

    assert stale.exists()


def test_app_startup_sweeps_the_spool_dir():
    from pathlib import Path

    from config.settings import Config
    from services.backup.section_store import STALE_AFTER_SECONDS
    from tests.fresh_app import fresh_app
    # create_app sweeps Config.DATA_DIR/tmp, which the session sandbox may have moved.
    spool = Path(Config.DATA_DIR) / 'tmp'
    spool.mkdir(parents=True, exist_ok=True)
    stale = spool / '.ucm_restore_from_a_killed_worker'
    stale.mkdir(exist_ok=True)
    old = os.stat(stale).st_mtime - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    with fresh_app():
        assert not stale.exists()


@pytest.mark.parametrize('shift', [-2, -1, 0, 1])
def test_eviction_does_not_depend_on_the_interpreters_reference_counts(
        store, monkeypatch, shift):
    """CPython 3.14 reports one reference fewer than 3.13 for the same code."""
    import sys

    from services.backup import section_store
    real = sys.getrefcount
    monkeypatch.setattr(section_store, 'getrefcount', lambda value: real(value) + shift)
    monkeypatch.setattr(section_store, '_BASELINE', section_store._baseline())

    held = {'users': store['users']}     # the way RestorePlan.rows holds sections
    store['configuration']
    store['certificates']
    assert store['users'] is held['users']
    del held
    store['configuration']
    store['certificates']
    assert 'users' not in store._loaded


def test_startup_sweeps_the_fallback_directory_when_no_spool_dir(tmp_path, monkeypatch):
    import tempfile
    from pathlib import Path

    from services.backup.section_store import STALE_AFTER_SECONDS
    from tests.fresh_app import fresh_app
    monkeypatch.setattr('utils.upload_spool.prepare_spool_dir', lambda _d: None)
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    from services.backup.section_store import fallback_directory
    stale = Path(fallback_directory()) / '.ucm_restore_from_a_killed_worker'
    stale.mkdir()
    old = os.stat(stale).st_mtime - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    with fresh_app():
        assert not stale.exists()


def test_store_directory_is_none_when_the_spool_probe_fails(monkeypatch):
    from services.backup import section_store
    monkeypatch.setattr('utils.upload_spool.prepare_spool_dir', lambda _d: None)
    assert section_store.store_directory() is None


def test_an_unwritable_data_tmp_is_not_a_store_directory(tmp_path, monkeypatch):
    from config.settings import Config
    from services.backup import section_store
    spool = tmp_path / 'tmp'
    spool.mkdir()
    spool.chmod(0o500)
    try:
        if os.access(spool, os.W_OK):
            pytest.skip('this process writes into a 0500 directory (root)')
        monkeypatch.setattr(Config, 'DATA_DIR', tmp_path)
        assert section_store.store_directory() is None
    finally:
        spool.chmod(0o700)


def test_no_sweep_when_the_lock_cannot_be_taken(tmp_path, monkeypatch, caplog):
    import logging

    from services.backup import section_store
    caplog.set_level(logging.DEBUG)

    def no_flock(_path):
        raise OSError(errno.ENOLCK, 'no locks available')

    monkeypatch.setattr('utils.process_lock._open_lock_file', no_flock)
    stale = tmp_path / '.ucm_restore_dead'
    stale.mkdir()
    old = os.stat(stale).st_mtime - section_store.STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))

    section_store.sweep_stale_stores(str(tmp_path))

    assert stale.exists()
    assert len([r for r in caplog.records if r.levelno >= logging.INFO]) == 1


def test_a_busy_lock_logs_one_line(tmp_path, caplog):
    import fcntl
    import logging

    from services.backup import section_store
    from services.backup.locking import operation_lock_path
    caplog.set_level(logging.DEBUG)
    stale = _stale_store(str(tmp_path))
    path = operation_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    # flock conflicts between two descriptors even within one process
    with open(path, 'a') as holder:
        fcntl.flock(holder, fcntl.LOCK_EX)
        section_store.sweep_stale_stores(str(tmp_path))

    assert os.path.exists(stale)
    assert len([r for r in caplog.records if r.levelno >= logging.INFO]) == 1


def _stale_store(directory, name='.ucm_restore_dead'):
    from services.backup.section_store import STALE_AFTER_SECONDS
    stale = os.path.join(directory, name)
    os.mkdir(stale)
    old = os.stat(stale).st_mtime - STALE_AFTER_SECONDS - 60
    os.utime(stale, (old, old))
    return stale


def test_each_instance_sweeps_only_its_own_fallback_directory(tmp_path, monkeypatch):
    import tempfile

    from config.settings import Config
    from services.backup import section_store
    monkeypatch.setattr('utils.upload_spool.prepare_spool_dir', lambda _d: None)
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    monkeypatch.setattr(Config, 'DATA_DIR', tmp_path / 'other')
    theirs = _stale_store(section_store.fallback_directory(), '.ucm_restore_theirs')
    shared = _stale_store(str(tmp_path), '.ucm_restore_shared')
    monkeypatch.setattr(Config, 'DATA_DIR', tmp_path / 'mine')
    directory = section_store.fallback_directory()
    mine = _stale_store(directory)

    section_store.sweep_stale_stores()

    assert not os.path.exists(mine)
    assert os.path.exists(theirs) and os.path.exists(shared)
    assert os.path.dirname(directory) == str(tmp_path)
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
    with SectionStore() as store:
        assert os.path.dirname(store._dir) == directory


def test_a_loosened_fallback_directory_is_closed_again(tmp_path, monkeypatch):
    import tempfile

    from config.settings import Config
    from services.backup import section_store
    monkeypatch.setattr('utils.upload_spool.prepare_spool_dir', lambda _d: None)
    monkeypatch.setattr(tempfile, 'tempdir', str(tmp_path))
    monkeypatch.setattr(Config, 'DATA_DIR', tmp_path / 'mine')
    directory = section_store.fallback_directory()
    os.chmod(directory, 0o777)

    assert section_store.fallback_directory() == directory
    assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700
