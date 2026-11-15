"""A restore killed after publishing leaves its kept previous contents; the next start removes them.

Every `.ucm_restore_kept_*` directory is created under the backup lock, so one
found while that lock is really held belongs to no live restore. A lock held
elsewhere, or taken fail-open, removes nothing.
"""
import errno
import logging
import threading

import pytest

from config.settings import Config
from services.backup.locking import backup_operation_lock
from services.backup.restore import files
from services.backup.restore.files import StagedFiles


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    paths = {name: tmp_path / name for name in ('ca', 'certs', 'private', 'https', 'backups')}
    for path in paths.values():
        path.mkdir()
    monkeypatch.setattr(Config, 'CA_DIR', paths['ca'], raising=False)
    monkeypatch.setattr(Config, 'CERT_DIR', paths['certs'], raising=False)
    monkeypatch.setattr(Config, 'PRIVATE_DIR', paths['private'], raising=False)
    monkeypatch.setattr(Config, 'HTTPS_CERT_PATH', paths['https'] / 'cert.pem', raising=False)
    monkeypatch.setattr(Config, 'HTTPS_KEY_PATH', paths['https'] / 'key.pem', raising=False)
    monkeypatch.setattr(Config, 'BACKUP_DIR', str(paths['backups']), raising=False)
    return paths


def _killed_after_publish(dirs):
    """stage_removal + publish, then no discard: what a worker killed mid-restore leaves."""
    key = dirs['private'] / 'cert_x.key'
    key.write_bytes(b'OLD PLAINTEXT KEY')
    pem = dirs['https'] / 'cert.pem'
    pem.write_bytes(b'OLD HTTPS CERT')
    staged = StagedFiles(base_dir=dirs['backups'].parent / 'staging')
    staged.stage_removal(key)
    staged.stage(pem, b'NEW HTTPS CERT', mode=0o644)
    staged.publish()
    kept = sorted(p for d in dirs.values() for p in d.glob('.ucm_restore_kept_*'))
    assert len(kept) == 2 and not key.exists()
    return kept


def test_the_next_start_removes_what_a_killed_restore_kept(dirs, caplog):
    kept = _killed_after_publish(dirs)
    other = dirs['private'] / 'ca_y.key'
    other.write_bytes(b'live key')
    unrelated = dirs['certs'] / '.ucm_restore_x.tmp'
    unrelated.write_bytes(b'not a kept directory')

    with caplog.at_level(logging.WARNING, logger=files.__name__):
        removed = files.sweep_kept_previous_contents()

    assert sorted(removed) == kept
    assert not any(path.exists() for path in kept)
    assert other.read_bytes() == b'live key' and unrelated.exists()
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert all(str(path) in warnings[0] for path in kept)


def test_a_restore_in_progress_elsewhere_keeps_its_directories(dirs):
    kept = _killed_after_publish(dirs)
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
    finally:
        release.set()
        worker.join()


def test_an_unprotected_lock_removes_nothing(dirs, monkeypatch):
    kept = _killed_after_publish(dirs)
    import utils.process_lock as process_lock

    def no_flock(path):
        raise OSError(errno.ENOLCK, 'no locks')

    monkeypatch.setattr(process_lock, '_open_lock_file', no_flock)
    with backup_operation_lock(timeout=0):
        assert files.sweep_kept_previous_contents() == []
    assert files.sweep_kept_previous_contents() == []
    assert all(path.exists() for path in kept)


def test_a_symlink_named_like_a_kept_directory_is_left(dirs, tmp_path):
    target = tmp_path / 'elsewhere'
    target.mkdir()
    (target / 'keep').write_bytes(b'x')
    (dirs['private'] / '.ucm_restore_kept_link').symlink_to(target)

    assert files.sweep_kept_previous_contents() == []
    assert (target / 'keep').exists()


def test_app_startup_sweeps_the_key_directories():
    from tests.fresh_app import fresh_app
    Config.PRIVATE_DIR.mkdir(parents=True, exist_ok=True)
    kept = Config.PRIVATE_DIR / '.ucm_restore_kept_from_a_killed_worker'
    kept.mkdir(exist_ok=True)
    (kept / 'previous_000000').write_bytes(b'OLD PLAINTEXT KEY')
    with fresh_app():
        assert not kept.exists()
