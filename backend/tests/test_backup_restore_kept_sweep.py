"""A restore killed after publishing leaves its kept previous contents; the next start settles them.

Every `.ucm_restore_kept_*` directory is created under the backup lock, so one
found while that lock is really held belongs to no live restore. Its journal
names the restore; the restore's row in `system_config`, written in its
transaction, says whether it committed: committed, the kept contents go;
rolled back, the destinations get them back. A lock held elsewhere, taken
fail-open, or a database that cannot be read, settles nothing.
"""
import errno
import json
import logging
import os
import stat
import threading
from pathlib import Path

import pytest

from config.settings import Config
from models import SystemConfig, db
from services.backup.locking import backup_operation_lock
from services.backup.restore import files
from services.backup.restore.files import StagedFiles, record_publication


@pytest.fixture
def dirs(tmp_path, monkeypatch, app):
    paths = {name: tmp_path / name for name in ('ca', 'certs', 'private', 'https', 'backups')}
    for path in paths.values():
        path.mkdir()
    monkeypatch.setattr(Config, 'CA_DIR', paths['ca'], raising=False)
    monkeypatch.setattr(Config, 'CERT_DIR', paths['certs'], raising=False)
    monkeypatch.setattr(Config, 'PRIVATE_DIR', paths['private'], raising=False)
    monkeypatch.setattr(Config, 'HTTPS_CERT_PATH', paths['https'] / 'cert.pem', raising=False)
    monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', paths['https'] / 'key.pem', raising=False)
    monkeypatch.setattr(Config, 'BACKUP_DIR', str(paths['backups']), raising=False)
    with app.app_context():
        yield paths
        SystemConfig.query.filter(SystemConfig.key.startswith(files.PUBLICATION_PREFIX)).delete(
            synchronize_session=False)
        db.session.commit()


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _killed_after_publish(dirs, committed):
    """A restore's publication, its row committed or rolled back, and no discard."""
    key = dirs['private'] / 'cert_x.key'
    key.write_bytes(b'OLD PLAINTEXT KEY')
    os.chmod(key, 0o600)
    pem = dirs['https'] / 'cert.pem'
    pem.write_bytes(b'OLD HTTPS CERT')
    os.chmod(pem, 0o640)
    new = dirs['certs'] / 'new.crt'
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    staged.stage_removal(key)
    staged.stage(pem, b'NEW HTTPS CERT', mode=0o644)
    staged.stage(new, b'NEW CERT', mode=0o644)
    record_publication(staged.token)
    staged.publish()
    # The kill: the uncommitted transaction is lost with the connection
    db.session.commit() if committed else db.session.rollback()
    kept = sorted(p for d in dirs.values() for p in d.glob('.ucm_restore_kept_*'))
    assert len(kept) == 3 and not key.exists() and new.exists()
    return kept, key, pem, new


def _row_exists(token):
    return SystemConfig.query.filter_by(key=files.PUBLICATION_PREFIX + token).first() is not None


def test_a_restore_killed_before_its_commit_is_put_back(dirs, caplog):
    kept, key, pem, new = _killed_after_publish(dirs, committed=False)
    other = dirs['private'] / 'ca_y.key'
    other.write_bytes(b'live key')
    unrelated = dirs['certs'] / '.ucm_restore_x.tmp'
    unrelated.write_bytes(b'not a kept directory')

    with caplog.at_level(logging.WARNING, logger=files.__name__):
        removed = files.sweep_kept_previous_contents()

    assert sorted(removed) == kept
    assert not any(path.exists() for path in kept)
    assert key.read_bytes() == b'OLD PLAINTEXT KEY' and _mode(key) == 0o600
    assert pem.read_bytes() == b'OLD HTTPS CERT' and _mode(pem) == 0o640
    assert not new.exists()
    assert other.read_bytes() == b'live key' and unrelated.exists()
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any('Put back' in message for message in warnings)


def test_a_restore_killed_after_its_commit_keeps_what_it_published(dirs):
    kept, key, pem, new = _killed_after_publish(dirs, committed=True)
    token = json.loads((kept[0] / 'journal.json').read_text())['token']
    assert _row_exists(token)

    assert sorted(files.sweep_kept_previous_contents()) == kept

    assert not any(path.exists() for path in kept)
    assert not key.exists()
    assert pem.read_bytes() == b'NEW HTTPS CERT' and new.read_bytes() == b'NEW CERT'
    assert not _row_exists(token)


def test_a_restore_killed_halfway_through_publishing_is_put_back(dirs, monkeypatch):
    # Killed while replacing the second of three: the third was kept, never touched
    paths = [dirs['certs'] / f'c{index}.crt' for index in range(3)]
    for index, path in enumerate(paths):
        path.write_bytes(b'old %d' % index)
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    for path in paths:
        staged.stage(path, b'new', mode=0o644)
    record_publication(staged.token)
    real_publish, calls = StagedFiles._publish, []

    def publish(self, entry):
        calls.append(entry)
        if len(calls) == 2:
            raise KeyboardInterrupt()    # no handler of publish() runs, as in a kill
        return real_publish(self, entry)
    monkeypatch.setattr(StagedFiles, '_publish', publish)
    with pytest.raises(KeyboardInterrupt):
        staged.publish()
    db.session.rollback()
    assert paths[0].read_bytes() == b'new'

    assert len(files.sweep_kept_previous_contents()) == 1
    assert [path.read_bytes() for path in paths] == [b'old 0', b'old 1', b'old 2']
    assert not list(dirs['certs'].glob('.ucm_restore_kept_*'))


def test_an_unreadable_database_settles_nothing(dirs, monkeypatch):
    kept, key, pem, new = _killed_after_publish(dirs, committed=False)

    def unreadable(tokens):
        raise RuntimeError('database gone')
    monkeypatch.setattr(files, '_committed_tokens', unreadable)

    assert files.sweep_kept_previous_contents() == []
    assert all(path.exists() for path in kept)
    assert pem.read_bytes() == b'NEW HTTPS CERT' and new.exists()


def test_a_kept_directory_without_a_journal_is_removed(dirs):
    # Killed before the journal was written: nothing had been replaced yet
    kept = dirs['private'] / '.ucm_restore_kept_early'
    kept.mkdir(mode=0o700)
    (kept / 'previous_000000').write_bytes(b'x')
    live = dirs['private'] / 'live.key'
    live.write_bytes(b'live')

    assert files.sweep_kept_previous_contents() == [kept]
    assert live.read_bytes() == b'live'


def test_a_journal_names_nothing_outside_its_directory(dirs, tmp_path):
    outside = tmp_path / 'outside.key'
    outside.write_bytes(b'not ours')
    kept = dirs['private'] / '.ucm_restore_kept_forged'
    kept.mkdir(mode=0o700)
    entries = [{'name': '../outside.key', 'previous': 'previous_000000', 'existed': False},
               {'name': 'x.key', 'previous': '../../outside.key', 'existed': True, 'mode': 0o600}]
    (kept / 'journal.json').write_text(json.dumps({'token': 'f' * 32, 'entries': entries}))

    assert files.sweep_kept_previous_contents() == []
    assert outside.read_bytes() == b'not ours' and kept.exists()


def test_a_restore_in_progress_elsewhere_keeps_its_directories(dirs):
    kept, _key, pem, _new = _killed_after_publish(dirs, committed=False)
    holding, release = threading.Event(), threading.Event()

    def hold():
        with backup_operation_lock(timeout=5):
            holding.set()
            release.wait(10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert holding.wait(5)
        assert files.sweep_kept_previous_contents() == []
        assert all(path.exists() for path in kept)
        assert pem.read_bytes() == b'NEW HTTPS CERT'
    finally:
        release.set()
        worker.join()


def test_an_unprotected_lock_removes_nothing(dirs, monkeypatch):
    kept, _key, pem, _new = _killed_after_publish(dirs, committed=False)
    import utils.process_lock as process_lock

    def no_flock(path):
        raise OSError(errno.ENOLCK, 'no locks')

    monkeypatch.setattr(process_lock, '_open_lock_file', no_flock)
    with backup_operation_lock(timeout=0):
        assert files.sweep_kept_previous_contents() == []
    assert files.sweep_kept_previous_contents() == []
    assert all(path.exists() for path in kept)
    assert pem.read_bytes() == b'NEW HTTPS CERT'


def test_a_symlink_named_like_a_kept_directory_is_not_followed(dirs, tmp_path):
    # Followed, its journal would remove a live file of the directory holding the link
    live = dirs['private'] / 'ca_live.key'
    live.write_bytes(b'live key')
    target = tmp_path / 'elsewhere'
    target.mkdir()
    (target / 'keep').write_bytes(b'x')
    journal = {'token': 'e' * 32, 'entries': [
        {'name': 'ca_live.key', 'previous': 'previous_000000', 'existed': False}]}
    (target / 'journal.json').write_text(json.dumps(journal))
    (dirs['private'] / '.ucm_restore_kept_link').symlink_to(target)

    assert files.sweep_kept_previous_contents() == []
    assert live.read_bytes() == b'live key'
    assert (target / 'keep').exists()


def test_a_committed_directory_left_on_disk_keeps_its_row(dirs, monkeypatch):
    # Its row erased, the next start would read the journal as uncommitted and put the old files back
    kept, key, pem, new = _killed_after_publish(dirs, committed=True)
    token = json.loads((kept[0] / 'journal.json').read_text())['token']
    with monkeypatch.context() as patched:
        patched.setattr(files.shutil, 'rmtree', lambda *args, **kwargs: None)
        assert files.sweep_kept_previous_contents() == []
    assert all(path.exists() for path in kept) and _row_exists(token)

    assert sorted(files.sweep_kept_previous_contents()) == kept
    assert pem.read_bytes() == b'NEW HTTPS CERT' and new.read_bytes() == b'NEW CERT'
    assert not key.exists() and not _row_exists(token)


def test_a_directory_that_cannot_be_put_back_does_not_stop_the_others(dirs, monkeypatch, caplog):
    kept, key, pem, new = _killed_after_publish(dirs, committed=False)
    # The first directory scanned: before it was caught, the others were never reached
    failing = next(path for path in kept if path.parent == dirs['certs'])
    real = files._put_back_journal

    def put_back(kept_dir, journal):
        if kept_dir == str(failing):
            raise OSError(errno.EIO, 'I/O error')
        return real(kept_dir, journal)
    with monkeypatch.context() as patched, caplog.at_level(logging.WARNING, logger=files.__name__):
        patched.setattr(files, '_put_back_journal', put_back)
        removed = files.sweep_kept_previous_contents()

    assert sorted(removed) == sorted(path for path in kept if path != failing)
    assert key.read_bytes() == b'OLD PLAINTEXT KEY' and pem.read_bytes() == b'OLD HTTPS CERT'
    assert failing.exists() and new.exists()
    assert any(str(failing) in record.getMessage() and record.levelno == logging.WARNING
               for record in caplog.records)

    assert files.sweep_kept_previous_contents() == [failing]
    assert not new.exists()


def test_a_publication_row_left_by_a_kill_after_discard_is_removed(dirs):
    record_publication('d' * 32)
    db.session.commit()
    assert files.sweep_kept_previous_contents() == []
    assert not _row_exists('d' * 32)


def test_the_publication_row_is_never_exported():
    from services.backup import installation
    assert installation.is_local_setting(files.PUBLICATION_PREFIX + 'a' * 32)


def test_app_startup_sweeps_the_key_directories():
    from tests.fresh_app import fresh_app
    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    kept = Config.PRIVATE_DIR / '.ucm_restore_kept_from_a_killed_worker'
    kept.mkdir(mode=0o700, exist_ok=True)
    os.chmod(kept, 0o700)
    (kept / 'previous_000000').write_bytes(b'OLD PLAINTEXT KEY')
    with fresh_app():
        assert not kept.exists()


def test_the_first_start_on_an_empty_database_reads_no_missing_table(caplog):
    # The sweep runs before the schema exists: SQLite in memory, a schema of its own on PostgreSQL
    from tests.fresh_app import fresh_app
    with caplog.at_level(logging.DEBUG, logger=files.__name__):
        with fresh_app():
            pass
    assert not [record.getMessage() for record in caplog.records
                if record.name == files.__name__ and record.levelno >= logging.INFO]


@pytest.fixture
def system_tmp(tmp_path, monkeypatch):
    root = tmp_path / 'system-tmp'
    root.mkdir()
    monkeypatch.setattr(files.tempfile, 'tempdir', str(root))
    return root


def _killed_staging(root, name='ucm_restore_files_killed'):
    staging = root / name
    staging.mkdir(mode=0o700)
    (staging / '0000_ca_x.key').write_bytes(b'PLAINTEXT KEY')
    return staging


def test_the_staging_of_a_killed_restore_is_removed(dirs, system_tmp):
    staging = _killed_staging(system_tmp)
    other = system_tmp / 'unrelated'
    other.mkdir()

    files.sweep_kept_previous_contents()
    assert not staging.exists() and other.exists()


def test_a_live_staging_is_kept(dirs, system_tmp):
    # A restore of another instance sharing this temporary directory holds its staging
    staged = StagedFiles()
    staged.stage(dirs['private'] / 'k.key', b'live')
    assert staged.staging_dir.parent == system_tmp
    try:
        files.sweep_kept_previous_contents()
        assert (staged.staging_dir / '0000_k.key').read_bytes() == b'live'
    finally:
        staged.discard()


def test_a_staging_is_swept_only_under_a_held_lock_and_never_through_a_link(
        dirs, system_tmp, tmp_path, monkeypatch):
    staging = _killed_staging(system_tmp)
    target = tmp_path / 'elsewhere'
    target.mkdir()
    (target / 'keep').write_bytes(b'x')
    (system_tmp / 'ucm_restore_files_link').symlink_to(target)
    import utils.process_lock as process_lock

    with monkeypatch.context() as patched:
        patched.setattr(process_lock, '_open_lock_file',
                        lambda path: (_ for _ in ()).throw(OSError(errno.ENOLCK, 'no locks')))
        files.sweep_kept_previous_contents()
        with backup_operation_lock(timeout=0):    # taken fail-open: held by nobody
            files.sweep_kept_previous_contents()
    assert staging.exists()

    files.sweep_kept_previous_contents()
    assert not staging.exists()
    assert (target / 'keep').exists() and (system_tmp / 'ucm_restore_files_link').is_symlink()


def test_a_staging_of_another_user_is_kept(dirs, system_tmp, monkeypatch):
    staging = _killed_staging(system_tmp)
    monkeypatch.setattr(files.os, 'geteuid', lambda: os.stat(staging).st_uid + 1)
    files.sweep_kept_previous_contents()
    assert staging.exists()


def test_a_staging_swept_before_its_lock_is_taken_is_made_again(system_tmp, monkeypatch):
    # Another instance's sweep may remove it between its creation and the flock
    real_flock, calls = files.fcntl.flock, []

    def flock(fd, operation):
        if not calls:
            os.rmdir(os.readlink(f'/proc/self/fd/{fd}'))
        calls.append(fd)
        return real_flock(fd, operation)
    monkeypatch.setattr(files.fcntl, 'flock', flock)
    staged = StagedFiles()
    try:
        staged.stage(system_tmp / 'k.key', b'live')
        assert len(calls) == 2 and staged.staging_dir.is_dir()
    finally:
        monkeypatch.undo()
        staged.discard()


def test_a_staging_that_cannot_be_locked_is_kept_without_its_lock(system_tmp, monkeypatch, caplog):
    # A filesystem without locks (ENOLCK) still restores: the staging names its owner instead
    real_flock = files.fcntl.flock

    def flock(fd, operation):
        raise OSError(errno.ENOLCK, 'no locks')
    monkeypatch.setattr(files.fcntl, 'flock', flock)
    staged = StagedFiles()
    try:
        with caplog.at_level(logging.WARNING, logger=files.__name__):
            staged.stage(system_tmp / 'k.key', b'secret')
        assert (staged.staging_dir / '0000_k.key').read_bytes() == b'secret'
        assert any(str(staged.staging_dir) in record.getMessage() for record in caplog.records)
        monkeypatch.setattr(files.fcntl, 'flock', real_flock)
        # Its lock free, but its owner alive: the sweep keeps it
        files._sweep_stale_stagings()
        assert staged.staging_dir.is_dir()
    finally:
        monkeypatch.setattr(files.fcntl, 'flock', real_flock)
        staged.discard()
    assert not list(system_tmp.glob('ucm_restore_files_*'))


def test_an_unlocked_staging_is_swept_only_once_its_owner_is_dead(system_tmp, monkeypatch):
    staging = _killed_staging(system_tmp)
    owner = files._owner_record()
    (staging / files._OWNER).write_text(json.dumps(owner))
    files._sweep_stale_stagings()
    assert staging.exists()    # this very process: alive

    (staging / files._OWNER).write_text(json.dumps(dict(owner, start='0')))
    files._sweep_stale_stagings()
    assert not staging.exists()    # its pid now names another process


@pytest.mark.parametrize('damage', ['other boot', 'other namespace', 'unreadable'])
def test_an_unlocked_staging_without_proof_of_death_is_kept(system_tmp, damage):
    staging = _killed_staging(system_tmp)
    owner = dict(files._owner_record(), start='0')
    if damage == 'other boot':
        owner['boot'] = 'another-boot'
    elif damage == 'other namespace':
        owner['pidns'] = 'pid:[1]'
    (staging / files._OWNER).write_text('{' if damage == 'unreadable' else json.dumps(owner))
    files._sweep_stale_stagings()
    assert staging.exists()


def test_a_committed_directory_left_on_disk_does_not_refuse_a_restore(dirs, monkeypatch):
    # Its journal is never replayed over newer files: a committed token only drops its kept copies
    kept, _key, pem, _new = _killed_after_publish(dirs, committed=True)
    monkeypatch.setattr(files.shutil, 'rmtree', lambda *args, **kwargs: None)
    files.settle_interrupted_restores()
    assert all(path.exists() for path in kept) and pem.read_bytes() == b'NEW HTTPS CERT'


def test_an_uncommitted_journal_left_on_disk_refuses_a_restore(dirs, monkeypatch):
    kept, _key, pem, _new = _killed_after_publish(dirs, committed=False)

    def put_back(kept_dir, journal):
        raise OSError(errno.EIO, 'I/O error')
    monkeypatch.setattr(files, '_put_back_journal', put_back)
    with pytest.raises(files.InterruptedRestorePending):
        files.settle_interrupted_restores()
    assert all(path.exists() for path in kept)


def test_a_journal_put_back_is_never_replayed_over_a_later_change(dirs, monkeypatch):
    # Its directory left on disk, the journal replayed at each start undid what came after
    kept, key, pem, new = _killed_after_publish(dirs, committed=False)
    with monkeypatch.context() as patched:
        patched.setattr(files.shutil, 'rmtree', lambda *args, **kwargs: None)
        files.sweep_kept_previous_contents()
    assert all(path.exists() and not (path / 'journal.json').exists() for path in kept)
    assert pem.read_bytes() == b'OLD HTTPS CERT' and not new.exists()
    new.write_bytes(b'ISSUED LATER')
    pem.write_bytes(b'RENEWED HTTPS CERT')

    assert sorted(files.sweep_kept_previous_contents()) == kept
    assert new.read_bytes() == b'ISSUED LATER' and pem.read_bytes() == b'RENEWED HTTPS CERT'


def test_a_compensation_that_failed_keeps_the_only_copy(dirs, monkeypatch):
    # A put back attempted is not a put back done: discard keeps its journal and previous content
    pem = dirs['https'] / 'key.pem'
    pem.write_bytes(b'UNBOUND HTTPS KEY')
    other = dirs['certs'] / 'c.crt'
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    staged.stage(pem, b'REPLACEMENT KEY')
    staged.stage(other, b'NEW CERT')
    staged.publish()
    staging = staged.staging_dir
    real_replace = os.replace

    def replace(source, target, *args, **kwargs):
        if 'previous_' in os.fspath(source):
            raise OSError(errno.EIO, 'I/O error')
        return real_replace(source, target, *args, **kwargs)
    with monkeypatch.context() as patched:
        patched.setattr(files.os, 'replace', replace)
        staged.unpublish()
    left = staged.discard()

    kept = list(dirs['https'].glob('.ucm_restore_kept_*'))
    assert left == kept and (kept[0] / 'journal.json').exists()
    assert not staging.exists() and not other.exists()
    assert not list(dirs['certs'].glob('.ucm_restore_kept_*'))
    assert pem.read_bytes() == b'REPLACEMENT KEY'

    assert files.sweep_kept_previous_contents() == kept    # no row: it never committed
    assert pem.read_bytes() == b'UNBOUND HTTPS KEY'


class _Kill(BaseException):
    """A process killed: no handler runs."""


def test_a_copy_cut_short_is_never_put_back_over_an_intact_original(dirs, monkeypatch):
    key = dirs['private'] / 'ca.key'
    key.write_bytes(b'INTACT ORIGINAL KEY' * 100)
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    staged.stage(key, b'REPLACEMENT')

    def no_link(*args, **kwargs):
        raise OSError(errno.EPERM, 'protected hardlinks')

    def copy_then_die(source, target, *args, **kwargs):
        target.write(source.read(5))
        target.flush()
        raise _Kill()
    with monkeypatch.context() as patched:
        patched.setattr(files.os, 'link', no_link)
        patched.setattr(files.shutil, 'copyfileobj', copy_then_die)
        with pytest.raises(_Kill):
            staged.publish()
    assert key.read_bytes() == b'INTACT ORIGINAL KEY' * 100
    kept = next(dirs['private'].glob('.ucm_restore_kept_*'))
    assert not (kept / 'previous_000000').exists()

    files.sweep_kept_previous_contents()
    assert key.read_bytes() == b'INTACT ORIGINAL KEY' * 100
    assert not kept.exists()


def _failing_parent_sync(monkeypatch, parents):
    real, synced = files._fsync_directory, []

    def fsync_directory(path):
        if Path(path) in parents:
            raise OSError(errno.EIO, 'I/O error')
        synced.append(Path(path))
        return real(path)
    monkeypatch.setattr(files, '_fsync_directory', fsync_directory)
    return synced


def test_a_removal_not_known_durable_keeps_the_row(dirs, monkeypatch):
    # The removal lost at a power cut, the journal would come back without its row
    kept, key, pem, new = _killed_after_publish(dirs, committed=True)
    token = json.loads((kept[0] / 'journal.json').read_text())['token']
    with monkeypatch.context() as patched:
        _failing_parent_sync(patched, {dirs['https']})
        files.sweep_kept_previous_contents()
    assert not any(path.exists() for path in kept) and _row_exists(token)

    files.sweep_kept_previous_contents()
    assert not _row_exists(token)


def test_each_removal_is_synced_before_the_row_goes(dirs, monkeypatch):
    kept, key, pem, new = _killed_after_publish(dirs, committed=True)
    token = json.loads((kept[0] / 'journal.json').read_text())['token']
    events, real_forget = [], files.forget_publication
    real_sync = files._fsync_directory
    monkeypatch.setattr(files, '_fsync_directory',
                        lambda path: events.append(Path(path)) or real_sync(path))
    monkeypatch.setattr(files, 'forget_publication',
                        lambda value: events.append(value) or real_forget(value))
    files.sweep_kept_previous_contents()
    assert {path.parent for path in kept} <= set(events[:events.index(token)])


def test_a_discard_not_known_durable_reports_its_directory(dirs, monkeypatch):
    pem = dirs['https'] / 'cert.pem'
    pem.write_bytes(b'OLD')
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    staged.stage(pem, b'NEW')
    staged.publish()
    kept = next(dirs['https'].glob('.ucm_restore_kept_*'))
    with monkeypatch.context() as patched:
        _failing_parent_sync(patched, {dirs['https']})
        assert staged.discard() == [kept]
    assert not kept.exists()


def test_a_lingering_row_stays_while_an_absence_is_not_durable(dirs, monkeypatch):
    record_publication('d' * 32)
    db.session.commit()
    with monkeypatch.context() as patched:
        _failing_parent_sync(patched, {dirs['private']})
        files.sweep_kept_previous_contents()
    assert _row_exists('d' * 32)
    files.sweep_kept_previous_contents()
    assert not _row_exists('d' * 32)


def _forged_kept_dir(parent, previous=None, mode=0o700, name='key.pem'):
    kept = parent / '.ucm_restore_kept_forged'
    kept.mkdir()
    os.chmod(kept, mode)
    entries = [{'name': name, 'previous': 'previous_000000', 'existed': True, 'mode': 0o666}]
    (kept / 'journal.json').write_text(json.dumps({'token': 'c' * 32, 'entries': entries}))
    if previous is not None:
        previous(kept / 'previous_000000')
    return kept


def test_a_kept_previous_content_that_is_a_link_is_refused(dirs, tmp_path, caplog):
    # Followed, the chmod after the rename opened a secret outside every restore root
    secret = tmp_path / 'secret'
    secret.write_bytes(b'unrelated secret')
    os.chmod(secret, 0o600)
    destination = dirs['https'] / 'key.pem'
    destination.write_bytes(b'live key')
    kept = _forged_kept_dir(dirs['https'], lambda path: path.symlink_to(secret))
    with caplog.at_level(logging.WARNING, logger=files.__name__):
        files.sweep_kept_previous_contents()
    assert _mode(secret) == 0o600 and secret.read_bytes() == b'unrelated secret'
    assert destination.read_bytes() == b'live key' and not destination.is_symlink()
    assert kept.exists() and any(str(kept) in record.getMessage() for record in caplog.records)


def test_a_kept_previous_content_that_is_not_a_file_is_refused(dirs):
    destination = dirs['https'] / 'key.pem'
    destination.write_bytes(b'live key')
    kept = _forged_kept_dir(dirs['https'], lambda path: os.mkfifo(path))
    files.sweep_kept_previous_contents()
    assert destination.read_bytes() == b'live key' and kept.exists()


@pytest.mark.parametrize('case', ['another owner', 'open to others'])
def test_a_kept_directory_not_private_to_the_service_is_left_alone(dirs, monkeypatch, caplog, case):
    destination = dirs['https'] / 'key.pem'
    destination.write_bytes(b'live key')
    kept = _forged_kept_dir(dirs['https'], lambda path: path.write_bytes(b'forged'),
                            mode=0o755 if case == 'open to others' else 0o700)
    if case == 'another owner':
        uid = os.stat(kept).st_uid
        monkeypatch.setattr(files.os, 'geteuid', lambda: uid + 1)
    with caplog.at_level(logging.WARNING, logger=files.__name__):
        files.sweep_kept_previous_contents()
    assert destination.read_bytes() == b'live key'
    assert (kept / 'previous_000000').read_bytes() == b'forged'
    assert any(str(kept) in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize('journal', [
    '{"token": "', '', '{"token": "' + 'b' * 32 + '", "entries": [42]}',
    json.dumps({'token': 'b' * 32, 'entries': [
        {'name': 'key.pem', 'previous': 'previous_000000', 'existed': True, 'mode': 0o600},
        {'name': '../x', 'previous': 'previous_000001', 'existed': False}]}),
    json.dumps({'token': 'b' * 32, 'entries': [
        {'name': 'key.pem', 'previous': 'previous_000000', 'existed': 'yes'}]})])
def test_a_damaged_journal_is_set_aside_and_refuses_a_restore(dirs, caplog, journal):
    # Read as absent, it let the sweep delete the only copy of what the restore replaced
    destination = dirs['https'] / 'key.pem'
    destination.write_bytes(b'uncommitted replacement')
    kept = dirs['https'] / '.ucm_restore_kept_damaged'
    kept.mkdir(mode=0o700)
    (kept / 'previous_000000').write_bytes(b'ORIGINAL KEY')
    (kept / 'journal.json').write_text(journal)
    with caplog.at_level(logging.WARNING, logger=files.__name__):
        assert files.sweep_kept_previous_contents() == []
    assert (kept / 'previous_000000').read_bytes() == b'ORIGINAL KEY'
    assert destination.read_bytes() == b'uncommitted replacement'
    assert any(str(kept) in record.getMessage() for record in caplog.records)
    with pytest.raises(files.InterruptedRestorePending):
        files.settle_interrupted_restores()
    assert kept.exists()


def test_a_damaged_journal_keeps_every_lingering_row(dirs):
    # Its token unknown, any row may be the one it would need once repaired
    record_publication('d' * 32)
    db.session.commit()
    kept = dirs['certs'] / '.ucm_restore_kept_damaged'
    kept.mkdir(mode=0o700)
    (kept / 'journal.json').write_text('{"tok')
    files.sweep_kept_previous_contents()
    assert _row_exists('d' * 32)
