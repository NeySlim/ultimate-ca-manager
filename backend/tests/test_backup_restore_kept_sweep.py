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
    kept.mkdir()
    (kept / 'previous_000000').write_bytes(b'x')
    live = dirs['private'] / 'live.key'
    live.write_bytes(b'live')

    assert files.sweep_kept_previous_contents() == [kept]
    assert live.read_bytes() == b'live'


def test_a_journal_names_nothing_outside_its_directory(dirs, tmp_path):
    outside = tmp_path / 'outside.key'
    outside.write_bytes(b'not ours')
    kept = dirs['private'] / '.ucm_restore_kept_forged'
    kept.mkdir()
    entries = [{'name': '../outside.key', 'previous': 'previous_000000', 'existed': False},
               {'name': 'x.key', 'previous': '../../outside.key', 'existed': True, 'mode': 0o600}]
    (kept / 'journal.json').write_text(json.dumps({'token': 'f' * 32, 'entries': entries}))

    assert files.sweep_kept_previous_contents() == [kept]
    assert outside.read_bytes() == b'not ours'


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
    kept.mkdir(exist_ok=True)
    (kept / 'previous_000000').write_bytes(b'OLD PLAINTEXT KEY')
    with fresh_app():
        assert not kept.exists()
