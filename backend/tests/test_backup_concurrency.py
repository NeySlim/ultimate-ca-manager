"""Two backup operations at once, in two processes.

The scheduled run, the run-now button and retention all write and delete in
the same directory, and the catalogue that vouches for the archives is a
single file. Nothing serialised them: two runs could produce the same name,
truncate each other's file, and both record a success.
"""
import multiprocessing
import time

import pytest

from services.backup import storage
from services.backup.locking import BackupBusyError, backup_operation_lock

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()


def _hold_the_lock(directory, ready, release):
    """Take the lock in another process and hold it until told to stop."""
    from config.settings import Config
    Config.BACKUP_DIR = directory
    with backup_operation_lock(purpose='the other process'):
        ready.set()
        release.wait(timeout=10)


@pytest.fixture
def backup_dir(tmp_path, monkeypatch):
    from config.settings import Config
    monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
    return tmp_path


class TestOnlyOneOperationAtATime:
    def test_a_second_process_cannot_create_while_one_holds_the_lock(
            self, backup_dir):
        context = multiprocessing.get_context('fork')
        ready, release = context.Event(), context.Event()
        holder = context.Process(target=_hold_the_lock,
                                 args=(backup_dir, ready, release))
        holder.start()
        try:
            assert ready.wait(timeout=10), 'the other process never took the lock'

            started = time.time()
            with pytest.raises(BackupBusyError):
                with backup_operation_lock(timeout=0.3, purpose='creating a backup'):
                    pytest.fail('two processes held the backup lock at once')
            assert time.time() - started < 5
        finally:
            release.set()
            holder.join(timeout=10)

    def test_the_lock_is_released_when_the_other_process_ends(self, backup_dir):
        context = multiprocessing.get_context('fork')
        ready, release = context.Event(), context.Event()
        holder = context.Process(target=_hold_the_lock,
                                 args=(backup_dir, ready, release))
        holder.start()
        assert ready.wait(timeout=10)
        release.set()
        holder.join(timeout=10)

        with backup_operation_lock(timeout=5, purpose='creating a backup'):
            pass


class TestConcurrentCreationsDoNotCollide:
    def test_every_archive_gets_its_own_name_and_record(self, app, backup_dir):
        """Twenty creations in a row: each is its own file, each is recorded."""
        with app.app_context():
            names = set()
            for index in range(20):
                _path, name = storage.create_archive(
                    b'UCMB' + bytes([3, 1, 2, 0]) + b'archive-%02d' % index)
                names.add(name)

            assert len(names) == 20, 'two archives were written under one name'
            files = {p.name for p in backup_dir.glob('ucm_backup_*.ucmbkp')}
            assert files == names
            recorded = set(storage.read_catalog(backup_dir))
            assert recorded == names, 'an archive was written without a record'

    def test_retention_does_not_run_while_a_backup_is_being_written(
            self, app, backup_dir):
        """Retention deletes; an archive being written is not yet recorded,
        and would look like one nothing vouches for."""
        from services.backup import schedule
        with app.app_context():
            with backup_operation_lock(purpose='a backup in flight'):
                # The scheduled pass gives up rather than delete underneath it
                assert schedule.run_backup_retention() == 0


class TestAFullDiskPublishesNothing:
    """The gate: a write that cannot complete leaves no archive behind, whole
    or partial, and nothing to clean up by hand."""

    def test_no_archive_and_no_temporary_file_survive(self, app, backup_dir,
                                                      monkeypatch):
        import errno
        import os as os_module

        with app.app_context():
            before = set(os_module.listdir(backup_dir))

            def no_space(fd):
                raise OSError(errno.ENOSPC, 'No space left on device')

            monkeypatch.setattr(os_module, 'fsync', no_space)

            with pytest.raises(OSError) as failure:
                storage.create_archive(b'UCMB' + bytes([3, 1, 2, 0]) + b'x' * 4096)
            assert failure.value.errno == errno.ENOSPC

        leftovers = set(os_module.listdir(backup_dir)) - before
        # The lock file is created on demand and kept on purpose; everything
        # else would be debris from a backup that never happened.
        assert leftovers <= {'.ucm_backup_operation.lock'}, sorted(leftovers)
        assert not list(backup_dir.glob('ucm_backup_*.ucmbkp'))

    def test_a_scheduled_run_that_cannot_write_says_so(self, app, backup_dir,
                                                       monkeypatch):
        """It fails, it is recorded as failed, and it does not pretend."""
        import errno
        import os as os_module
        from models import SystemConfig, db
        from services.backup import schedule

        with app.app_context():
            for key, value in (('auto_backup_enabled', 'true'),
                               ('backup_frequency', 'daily'),
                               ('backup_password', 'Correct-Horse-Battery-9')):
                row = SystemConfig.query.filter_by(key=key).first()
                if row:
                    row.value = value
                else:
                    db.session.add(SystemConfig(key=key, value=value))
            SystemConfig.query.filter_by(key='backup.last_run').delete()
            db.session.commit()

            real_fsync = os_module.fsync
            archive_dir = str(backup_dir)

            def no_space(fd):
                # Only the archive being written, not every fsync in the
                # process: the run records its own outcome through the
                # database, and a commit that cannot sync would leave this
                # test asserting on an outcome nobody could write.
                try:
                    name = os_module.readlink(f'/proc/self/fd/{fd}')
                except OSError:
                    name = ''
                if name.startswith(archive_dir):
                    raise OSError(errno.ENOSPC, 'No space left on device')
                return real_fsync(fd)

            monkeypatch.setattr(os_module, 'fsync', no_space)
            try:
                with pytest.raises(OSError):
                    schedule.run_scheduled_backup()

                monkeypatch.undo()
                status = schedule.get_schedule()
                assert status['last_outcome'] == 'failed'
                assert status['last_outcome_reason']
                assert schedule._get('backup.last_run') is None, \
                    'a run that wrote nothing must be tried again'
            finally:
                row = SystemConfig.query.filter_by(key='auto_backup_enabled').first()
                if row:
                    row.value = 'false'
                SystemConfig.query.filter_by(key='backup_password').delete()
                db.session.commit()
