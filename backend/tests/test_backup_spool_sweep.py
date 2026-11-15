"""A backup killed mid-write leaves its spool behind; the next one removes it.

Every `.ucm_backup_*.tmp` is written under the backup lock, so one found while
the lock is really held belongs to no live backup. A held-by-someone-else or
taken-unprotected lock removes nothing.
"""
import errno
import threading

import pytest

from config.settings import Config
from services.backup import storage
from services.backup.locking import backup_operation_lock


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, 'BACKUP_DIR', str(tmp_path), raising=False)
    return tmp_path


def _leftover(directory, name='.ucm_backup_killed.tmp'):
    path = directory / name
    path.write_bytes(b'x' * 1024)
    return path


def test_a_leftover_spool_is_removed_and_nothing_else(backup_dir):
    leftover = _leftover(backup_dir)
    archive = backup_dir / 'ucm_backup_20260101_000000.ucmbkp'
    archive.write_bytes(b'archive')
    other = backup_dir / '.ucm_restore_x.tmp'
    other.write_bytes(b'not ours')

    assert storage.sweep_orphan_spools() == 1

    assert not leftover.exists()
    assert archive.exists() and other.exists()
    assert (backup_dir / '.ucm_backup_operation.lock').exists()


def test_a_spool_of_a_backup_in_progress_elsewhere_is_kept(backup_dir):
    leftover = _leftover(backup_dir)
    holding, release = threading.Event(), threading.Event()

    def hold():
        with backup_operation_lock(timeout=5):
            holding.set()
            release.wait(10)

    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert holding.wait(5)
        assert storage.sweep_orphan_spools() == 0
        assert leftover.exists()
    finally:
        release.set()
        worker.join()


def test_an_unprotected_lock_removes_nothing(backup_dir, monkeypatch):
    # flock unavailable: the outer backup runs fail-open, and a nested sweep
    # cannot know whether another process is writing its own spool.
    leftover = _leftover(backup_dir)
    import utils.process_lock as process_lock

    def no_flock(path):
        raise OSError(errno.ENOLCK, 'no locks')

    monkeypatch.setattr(process_lock, '_open_lock_file', no_flock)
    with backup_operation_lock(timeout=0):
        assert storage.sweep_orphan_spools() == 0
    assert storage.sweep_orphan_spools() == 0
    assert leftover.exists()


def test_the_next_backup_removes_the_leftover(backup_dir):
    leftover = _leftover(backup_dir)

    path, _filename = storage.create_archive(iter([b'new ', b'archive']))

    assert path.read_bytes() == b'new archive'
    assert not leftover.exists()
    assert not list(backup_dir.glob('.ucm_backup_*.tmp'))


def test_an_export_that_raises_leaves_no_spool(backup_dir):
    def broken():
        yield b'first part'
        raise RuntimeError('export failed')

    with pytest.raises(RuntimeError):
        storage.create_archive(broken())
    assert not list(backup_dir.glob('.ucm_backup_*.tmp'))
