"""A restore killed between publishing its files and the end: the next start matches the database.

Killed before the commit, the database rolls back while the published files
stay. The startup regeneration writes only missing files, so it leaves them
describing the restore that did not happen; the sweep puts the previous
contents back. Killed after the commit, the published files are the database's
and stay. A kill is simulated by an exception no handler catches, with the
cleanup a dead process never runs disabled.
"""
import base64
import tempfile
from pathlib import Path

import pytest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Killed-Restore-Pass-53'


class Killed(BaseException):
    """What `kill -9` looks like from inside: nothing after this point runs."""


@pytest.fixture
def diverged(app, create_ca, create_cert, tmp_path):
    """An archive, then the database moved on: C1 holds another certificate, its file too."""
    from models import Certificate, db
    from services.backup_service import BackupService
    from utils.file_naming import cert_cert_path
    ca = create_ca(cn='Killed Restore CA')
    first = create_cert(cn='killed-restore-1.example.com', ca_id=ca['id'])
    other = create_cert(cn='killed-restore-2.example.com', ca_id=ca['id'])
    with app.app_context():
        archive = tmp_path / 'archive.ucmbkp'
        archive.write_bytes(b''.join(BackupService().iter_backup(PASSWORD, kdf='pbkdf2')))
        row = db.session.get(Certificate, first['id'])
        archived_pem = base64.b64decode(row.crt)
        row.crt = db.session.get(Certificate, other['id']).crt
        db.session.commit()
        path = cert_cert_path(row)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(row.crt))
        return archive, row.refid, path, archived_pem


def _database_pem(refid):
    from models import Certificate
    return base64.b64decode(Certificate.query.filter_by(refid=refid).one().crt)


def _restore_killed(monkeypatch, archive, when):
    from models import db
    from services.backup.restore import files
    from services.backup_service import BackupService
    real_publish = files.StagedFiles.publish

    def publish_then_die(self):
        real_publish(self)
        raise Killed()

    def die(self):
        raise Killed()

    if when == 'before commit':
        monkeypatch.setattr(files.StagedFiles, 'publish', publish_then_die)
        monkeypatch.setattr(files.StagedFiles, 'discard', lambda self: None)
    else:
        monkeypatch.setattr(files.StagedFiles, 'discard', die)
    with pytest.raises(Killed):
        BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
    db.session.rollback()    # the connection dies with the process: what was not committed is gone
    monkeypatch.undo()


def test_killed_before_the_commit_the_files_come_back(app, diverged, monkeypatch):
    from services.backup.restore.files import sweep_kept_previous_contents
    from services.file_regen_service import regenerate_all_files
    archive, refid, path, archived_pem = diverged
    with app.app_context():
        before = _database_pem(refid)
        _restore_killed(monkeypatch, archive, 'before commit')
        assert _database_pem(refid) == before != archived_pem
        assert path.read_bytes() == archived_pem    # the restore's file, not the database's

        regenerate_all_files()
        assert path.read_bytes() == archived_pem, 'the regeneration repairs only missing files'

        assert sweep_kept_previous_contents()
        assert path.read_bytes() == before == _database_pem(refid)
        assert not list(path.parent.glob('.ucm_restore_kept_*'))


def test_killed_after_the_commit_the_files_stay(app, diverged, monkeypatch):
    from models import SystemConfig
    from services.backup.restore.files import PUBLICATION_PREFIX, sweep_kept_previous_contents
    archive, refid, path, archived_pem = diverged
    with app.app_context():
        _restore_killed(monkeypatch, archive, 'after commit')
        assert _database_pem(refid) == archived_pem == path.read_bytes()
        assert list(path.parent.glob('.ucm_restore_kept_*'))

        assert sweep_kept_previous_contents()
        assert path.read_bytes() == archived_pem == _database_pem(refid)
        assert not list(path.parent.glob('.ucm_restore_kept_*'))
        assert not SystemConfig.query.filter(SystemConfig.key.startswith(PUBLICATION_PREFIX)).all()


def test_a_kept_directory_discard_cannot_remove_keeps_the_row(app, diverged, monkeypatch):
    # Forgotten anyway, the next start would read the journal as uncommitted and undo the restore
    import errno
    import shutil
    from services.backup.restore import files
    from services.backup_service import BackupService
    archive, refid, path, archived_pem = diverged
    real_rmtree = shutil.rmtree

    def rmtree(directory, *args, **kwargs):
        if str(directory).rsplit('/', 1)[-1].startswith('.ucm_restore_kept_'):
            raise OSError(errno.EIO, 'I/O error')
        return real_rmtree(directory, *args, **kwargs)

    with app.app_context():
        with monkeypatch.context() as patched:
            patched.setattr(files.shutil, 'rmtree', rmtree)
            BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
        assert list(path.parent.glob('.ucm_restore_kept_*'))
        assert path.read_bytes() == archived_pem

        assert files.sweep_kept_previous_contents()
        assert path.read_bytes() == archived_pem == _database_pem(refid)
        assert not list(path.parent.glob('.ucm_restore_kept_*'))


def _stale_journal(directory, name):
    """A journal of a restore rolled back whose settling never finished: it would remove `name`."""
    import json
    kept = Path(tempfile.mkdtemp(prefix='.ucm_restore_kept_', dir=directory))
    entries = [{'name': name, 'previous': 'previous_000000', 'existed': False, 'mode': None}]
    (kept / 'journal.json').write_text(json.dumps({'token': 'a' * 32, 'entries': entries}))
    return kept


def test_an_older_journal_is_settled_before_a_restore_publishes(app, diverged):
    from services.backup.restore.files import sweep_kept_previous_contents
    from services.backup_service import BackupService
    archive, refid, path, archived_pem = diverged
    with app.app_context():
        kept = _stale_journal(path.parent, path.name)
        BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
        assert path.read_bytes() == archived_pem

        sweep_kept_previous_contents()    # the next start
        assert path.read_bytes() == archived_pem == _database_pem(refid)
        assert not kept.exists()


def test_a_restore_is_refused_while_an_older_journal_remains(app, diverged, monkeypatch):
    from services.backup.restore import files
    from services.backup_service import BackupService
    archive, refid, path, archived_pem = diverged
    with app.app_context():
        before = _database_pem(refid)
        kept = _stale_journal(path.parent, 'never-published.crt')
        with monkeypatch.context() as patched:
            patched.setattr(files, '_put_back_journal', lambda *args: (_ for _ in ()).throw(
                OSError('read-only filesystem')))
            with pytest.raises(files.InterruptedRestorePending):
                BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
        assert kept.exists()
        assert _database_pem(refid) == before == path.read_bytes()
        files.sweep_kept_previous_contents()
        assert not kept.exists()


def test_a_restore_that_ends_leaves_no_publication_row(app, diverged):
    from models import SystemConfig
    from services.backup.restore.files import PUBLICATION_PREFIX
    from services.backup_service import BackupService
    archive, refid, path, archived_pem = diverged
    with app.app_context():
        BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
        assert path.read_bytes() == archived_pem
        assert not SystemConfig.query.filter(SystemConfig.key.startswith(PUBLICATION_PREFIX)).all()
        assert not list(path.parent.glob('.ucm_restore_kept_*'))


def test_a_commit_that_fails_puts_the_files_back(app, diverged, monkeypatch):
    # The restore's own commit raises, its files already published: they come back
    from models import SystemConfig, db
    from services.backup.restore.files import PUBLICATION_PREFIX
    from services.backup_service import BackupService
    archive, refid, path, archived_pem = diverged
    failed = []

    def commit(self):
        pending = self.query(SystemConfig).filter(
            SystemConfig.key.startswith(PUBLICATION_PREFIX)).count()
        if pending and not failed:
            failed.append(path.read_bytes())
            raise RuntimeError('the commit failed')
        return real_commit(self)

    with app.app_context():
        before = _database_pem(refid)
        session_class = type(db.session())
        real_commit = session_class.commit
        with monkeypatch.context() as patched:
            patched.setattr(session_class, 'commit', commit)
            with pytest.raises(RuntimeError, match='the commit failed'):
                BackupService().restore_backup_from_path(archive, PASSWORD, mode='replace')
        assert failed == [archived_pem], 'the files were published when the commit ran'
        assert path.read_bytes() == before == _database_pem(refid)
        assert not list(path.parent.glob('.ucm_restore_kept_*'))
        assert not SystemConfig.query.filter(SystemConfig.key.startswith(PUBLICATION_PREFIX)).all()
