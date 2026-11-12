"""A fault at every point a backup or a restore can fail, and what stays true.

The other backup tests each pin one mechanism: the transaction, the staged
files, the retention rules, the scheduler's retry guard. This file breaks the
seams *between* them and asks the only question an administrator cares about
afterwards -- what is on this machine now, and does what it is told match it.

So each test injects one failure at one precise point (never a stand-in for
the function under test, which would only prove the stand-in), and then reads
the instance back: it counts the rows, re-reads the files byte for byte with
their mode, looks at what was left in the temporary directories, and checks
what the route or the task reported.

Three properties are the reason the file exists:

- The database is either entirely as it was or entirely the archive's, and
  no file on disk describes a restore that did not happen. The window is the
  commit, and the files are published just before it, so a commit that fails
  has to take the files back with it.
- A failure in what *reports* the work -- the audit trail, the outcome row --
  never changes the verdict on the work itself, in either direction.
- A failure in what *finishes* the work -- retention, the restart signal --
  is told to the operator without pretending the work did not happen.

Every archive here carries only the sections under test (`_only`, the pattern
of test_backup_restore_symmetry): the session database is shared by the whole
file-level worker with no per-test rollback, and a full archive restored into
it would rewrite rows the rest of the suite is looking at. Each test puts the
rows and the files it touched back before it returns.
"""
import errno
import io
import json
import os
import stat
import tempfile
import time
from pathlib import Path

import pytest

from config.settings import Config
from models import db, SystemConfig
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'
GROUP_NAME = 'fault-injection-group'

ARCHIVE_CERT = b'-----BEGIN CERTIFICATE-----\nthe pair the archive carries\n'
ARCHIVE_KEY = b'-----BEGIN PRIVATE KEY-----\nthe key the archive carries\n'
LIVE_CERT = b'-----BEGIN CERTIFICATE-----\nthe pair the server is using\n'
LIVE_KEY = b'-----BEGIN PRIVATE KEY-----\nthe key the server is using\n'

# A mode the restore would not produce on its own (it stages the certificate
# at 0o644), so a compensated file proves the mode came back and was not just
# re-created with the staged one.
LIVE_CERT_MODE = 0o640

_SETTINGS_KEYS = (
    'auto_backup_enabled', 'backup_frequency', 'backup_password',
    'backup_retention_days', 'backup_min_keep', 'backup_max_total_mb',
    'backup.last_run', 'backup.last_outcome', 'backup.last_reason',
    'backup.last_outcome_at', 'backup.concluded_run',
)
_OUTCOME_KEYS = ('backup.last_outcome', 'backup.last_reason',
                 'backup.last_outcome_at')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map that carries just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def _group_names():
    from models.group import Group
    return {group.name for group in Group.query.all()}


def _drop_group():
    from models.group import Group
    Group.query.filter_by(name=GROUP_NAME).delete()
    db.session.commit()


def _tree(root):
    """Every file under ``root``, with its content and its mode.

    The unit of the "nothing moved" assertions: a restore that failed must
    leave the data directory holding the same bytes, not merely the same
    names.
    """
    root = Path(root)
    if not root.is_dir():
        return {}
    snapshot = {}
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            snapshot[str(path.relative_to(root))] = (path.read_bytes(),
                                                     _mode(path))
    return snapshot


#: Resolved once, before any test redirects the temporary root.
_SYSTEM_TEMP = Path(tempfile.gettempdir()).resolve()


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


@pytest.fixture(autouse=True)
def sandboxed_write_targets(app):
    """Refuse to run if the suite's write targets are not a sandbox.

    This file publishes the HTTPS pair, writes the authority files and
    deletes archives, and the suite runs as root on a machine that hosts a
    UCM instance. The `app` fixture redirects these paths; checking it here
    means a test that publishes files cannot silently land on the running
    service's own `/etc/ucm` or `/opt/ucm` because a fixture changed.
    """
    for name in ('HTTPS_CERT_PATH', 'HTTPS_KEY_PATH', 'DATA_DIR', 'BACKUP_DIR',
                 'CA_DIR', 'CERT_DIR', 'PRIVATE_DIR'):
        path = Path(getattr(Config, name)).resolve()
        assert path.is_relative_to(_SYSTEM_TEMP), \
            f'{name} points at {path}, outside the test sandbox'


@pytest.fixture
def private_staging_root(tmp_path, monkeypatch):
    """Give the restore's staging a temporary root of this test's own.

    `StagedFiles` creates its directory in the system temporary directory,
    which every xdist worker shares: what is in there at any moment is partly
    another worker's, so counting it would be asserting on somebody else's
    work. Redirected here, the directory is this test's alone and "the
    staging did not survive" means exactly that.
    """
    root = tmp_path / 'temporary-root'
    root.mkdir()
    monkeypatch.setattr(tempfile, 'tempdir', str(root))
    return root


@pytest.fixture
def without_the_https_pair(app):
    """Run with no HTTPS pair on disk, and put back whatever was there.

    The pair is exported whatever the include map says, so a file another
    test left behind would make an archive of the groups alone publish files
    too -- and the assertions about what a failed restore did not write would
    be about the wrong thing.
    """
    saved = {}
    for path in (Config.HTTPS_CERT_PATH, Config.HTTPS_KEY_PATH):
        path = Path(path)
        if path.exists():
            saved[path] = (path.read_bytes(), _mode(path))
            path.unlink()
    yield
    for path, (data, mode) in saved.items():
        path.write_bytes(data)
        os.chmod(path, mode)


@pytest.fixture
def groups_archive(app, without_the_https_pair):
    """An archive of the groups alone, and an instance that has lost one.

    Yields ``(blob, names)``: restoring the archive puts the group back, and
    anything short of a complete restore must leave ``names`` as it is.
    """
    with app.app_context():
        _drop_group()
        from models.group import Group
        db.session.add(Group(name=GROUP_NAME))
        db.session.commit()

        blob = _service().create_backup(PASSWORD, include=_only('groups'))

        _drop_group()
        yield blob, _group_names()
        _drop_group()


@pytest.fixture
def archive_with_the_https_pair(app):
    """An archive holding one group and an HTTPS pair the server no longer has.

    The pair on disk afterwards is deliberately different from the archive's,
    with a mode the restore would not write: publishing is then visible, and
    so is putting it back.
    """
    with app.app_context():
        Path(Config.HTTPS_CERT_PATH).write_bytes(ARCHIVE_CERT)
        Path(Config.HTTPS_KEY_PATH).write_bytes(ARCHIVE_KEY)
        _drop_group()
        from models.group import Group
        db.session.add(Group(name=GROUP_NAME))
        db.session.commit()

        blob = _service().create_backup(PASSWORD, include=_only('groups'))

        _drop_group()
        Path(Config.HTTPS_CERT_PATH).write_bytes(LIVE_CERT)
        os.chmod(Config.HTTPS_CERT_PATH, LIVE_CERT_MODE)
        Path(Config.HTTPS_KEY_PATH).write_bytes(LIVE_KEY)
        os.chmod(Config.HTTPS_KEY_PATH, 0o600)

        yield blob, _group_names()

        _drop_group()
        Path(Config.HTTPS_CERT_PATH).unlink(missing_ok=True)
        Path(Config.HTTPS_KEY_PATH).unlink(missing_ok=True)


@pytest.fixture
def backup_settings_sandbox(app, tmp_path, monkeypatch):
    """A private archive directory, and the backup settings put back after.

    The schedule keys live in the shared `system_config` table: a test that
    leaves `auto_backup_enabled` on, or a stale `backup.last_run`, changes
    what the next test file on this worker reads.
    """
    with app.app_context():
        saved = {}
        for key in _SETTINGS_KEYS:
            row = SystemConfig.query.filter_by(key=key).first()
            saved[key] = row.value if row else None
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)

        yield tmp_path

        for key, value in saved.items():
            SystemConfig.query.filter_by(key=key).delete()
            if value is not None:
                db.session.add(SystemConfig(key=key, value=value))
        db.session.commit()


def _enable_unattended_backups():
    """Turn the unattended run on and make it due right now."""
    _set('auto_backup_enabled', 'true')
    _set('backup_frequency', 'daily')
    _set('backup_password', PASSWORD)
    SystemConfig.query.filter_by(key='backup.last_run').delete()
    db.session.commit()


def _audit_spy(monkeypatch):
    """Record what the audit trail was asked to write, without writing it."""
    from services.audit_service import AuditService
    calls = []
    monkeypatch.setattr(AuditService, 'log_action',
                        staticmethod(lambda **kwargs: calls.append(kwargs)))
    return calls


def _audit_is_down(monkeypatch):
    from services.audit_service import AuditService
    monkeypatch.setattr(
        AuditService, 'log_action',
        staticmethod(lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError('the audit store is unreachable'))))


def _no_real_restart(monkeypatch):
    """Keep the restart signal file out of the way of a route test."""
    from utils import service_manager
    monkeypatch.setattr(service_manager, 'restart_service',
                        lambda: (True, 'restart requested'))


def _restore_through_the_route(auth_client, blob):
    return auth_client.post(
        '/api/v2/system/restore',
        data={'password': PASSWORD, 'file': (io.BytesIO(blob), 'backup.ucmbkp')},
        content_type='multipart/form-data')


def _write_archive(directory, name, payload, age_days, *, record=True):
    """An archive on disk the way the service writes one, with its record."""
    from services.backup import storage
    path = storage.write_archive_atomically(directory, name, payload)
    if record:
        storage.validate_and_record(path, payload)
    stamp = time.time() - age_days * 86400
    os.utime(path, (stamp, stamp))
    return path


class TestNothingMovesBeforeTheFirstWrite:
    """Everything the payload claims about itself is checked before the first
    write. A failure between those checks and the first row must therefore be
    indistinguishable, from outside, from an archive that was never offered."""

    def test_a_failure_after_the_checks_writes_no_row_and_no_file(
            self, app, groups_archive, private_staging_root, monkeypatch):
        """The plan is built after the payload has been validated and before
        `_apply_all` touches anything: the last moment at which a restore can
        still cost nothing.

        The whole data directory is compared here, content and mode, which is
        only a fair question at this seam: nothing of the restore has run, so
        not one byte of it may have moved.
        """
        from services.backup.restore.plan import RestorePlan
        blob, before = groups_archive

        with app.app_context():
            tree_before = _tree(Config.DATA_DIR)

            monkeypatch.setattr(
                RestorePlan, '_index_target_rows',
                lambda self, data: (_ for _ in ()).throw(
                    RuntimeError('the plan could not be built')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _group_names() == before
            assert _tree(Config.DATA_DIR) == tree_before, \
                'a restore that never started wrote to the data directory'
            assert list(private_staging_root.iterdir()) == [], \
                'a staging directory outlived a restore that staged nothing'


class TestAFailureMidwayTakesBackWhatWasApplied:
    """The sections are applied in one transaction, but that only holds if
    every step between them is inside it too. These are the steps that are
    neither a restorer nor the commit."""

    def test_a_step_between_two_sections_undoes_the_sections_before_it(
            self, app, groups_archive, private_staging_root, monkeypatch):
        """The ACME profile bindings are remapped between the templates and
        the truststore, with the groups already applied. It is a plain call in
        the middle of `_apply_all`, and a failure there must not leave the
        instance holding the first half of an archive.

        What is claimed here is the rows and the destinations the restore
        publishes, not the whole data directory: `_regenerate_files` has
        already run by this point, and it rewrites the authority and
        certificate files of *every* row in the database, not only the
        archive's. Those writes are not staged and not undone -- for rows the
        restore did not change they put back the bytes the database already
        held, which is why the failure is still invisible from outside.
        """
        from services.acme import profiles as acme_profiles
        blob, before = groups_archive

        with app.app_context():
            monkeypatch.setattr(
                acme_profiles, 'remap_template_bindings',
                lambda: (_ for _ in ()).throw(
                    RuntimeError('the bindings could not be remapped')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _group_names() == before, \
                'the section applied before the failure survived it'
            assert not Path(Config.HTTPS_CERT_PATH).exists()
            assert not Path(Config.HTTPS_KEY_PATH).exists()
            assert list(private_staging_root.iterdir()) == [], \
                'the staging of a restore that failed was kept'


class TestTheFilesAndTheDatabaseAgreeAboutTheCommit:
    """The one window the transaction cannot cover on its own.

    The files are published *before* the commit, not after it: they are part
    of the restore, and a file that cannot be placed has to be able to take
    the database back with it. That leaves the commit itself as the last
    thing that can fail, with the files already in place -- which is what
    `unpublish()` exists for.
    """

    def test_the_pair_is_published_before_the_commit_and_taken_back_with_it(
            self, app, archive_with_the_https_pair, private_staging_root,
            monkeypatch):
        """Both halves in one test, because they are one property: the commit
        reads the destinations and finds the archive's pair there (so the
        publication really did precede it), and once it has failed the
        destinations hold what the server was using, byte for byte and with
        their own mode."""
        from sqlalchemy.orm.session import Session
        blob, before = archive_with_the_https_pair
        at_commit = {}

        with app.app_context():
            def failing_commit(self, *args, **kwargs):
                at_commit['cert'] = Path(Config.HTTPS_CERT_PATH).read_bytes()
                at_commit['key'] = Path(Config.HTTPS_KEY_PATH).read_bytes()
                raise RuntimeError('the transaction could not be committed')

            with monkeypatch.context() as injected:
                injected.setattr(Session, 'commit', failing_commit)
                with pytest.raises(RuntimeError):
                    _service().restore_backup(blob, PASSWORD)
            db.session.rollback()

            assert at_commit == {'cert': ARCHIVE_CERT, 'key': ARCHIVE_KEY}, \
                'the files were not published before the commit was attempted'

            assert Path(Config.HTTPS_CERT_PATH).read_bytes() == LIVE_CERT
            assert Path(Config.HTTPS_KEY_PATH).read_bytes() == LIVE_KEY
            assert _mode(Config.HTTPS_CERT_PATH) == LIVE_CERT_MODE, \
                'the certificate came back with the mode the restore stages, ' \
                'not the one it found'
            assert _mode(Config.HTTPS_KEY_PATH) == 0o600

            assert _group_names() == before, \
                'the database kept a restore whose commit failed'
            assert sorted(p.name for p in Path(Config.HTTPS_CERT_PATH).parent
                          .iterdir()) == ['https_cert.pem', 'https_key.pem'], \
                'a temporary file of the publication was left behind'
            assert list(private_staging_root.iterdir()) == []

    def test_a_committed_restore_is_not_undone_because_the_sessions_survived(
            self, app, auth_client, groups_archive, monkeypatch, tmp_path):
        """The last seam: the data is in and the caches are not yet dropped.

        Revoking the sessions is the one part of the aftermath that is a
        security outcome rather than a degraded one, so it refuses to be
        reported as clean -- but the restore itself has committed, and the
        answer must say so and tell the operator to restart, not imply that
        nothing happened.
        """
        from models.group import Group
        from services.backup.restore import invalidate
        blob, _before = groups_archive

        store = tmp_path / 'sessions'
        store.mkdir()
        monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(store))
        monkeypatch.setattr(
            invalidate, '_revoke_database_sessions',
            lambda: (_ for _ in ()).throw(
                RuntimeError('the session table is unreachable')))

        response = _restore_through_the_route(auth_client, blob)

        assert response.status_code == 500
        message = json.loads(response.data)['message']
        assert 'restored' in message.lower() and 'restart' in message.lower(), \
            f'the answer does not say the data is in: {message}'

        with app.app_context():
            assert Group.query.filter_by(name=GROUP_NAME).first() is not None, \
                'a failure after the commit was reported as a restore that ' \
                'did not happen'


class TestFilesThatCannotBeWritten:
    """A full disk and a refused permission, at the two moments a restore
    writes: while it stages, and while it publishes. What was there before
    has to come back exactly, and nothing of the attempt may survive."""

    def test_a_full_disk_while_staging_publishes_nothing_at_all(
            self, app, archive_with_the_https_pair, private_staging_root,
            monkeypatch):
        """Staging happens while the transaction can still roll back, so the
        destinations must not even have been opened."""
        from services.backup.restore.files import _STAGING_PREFIX
        blob, before = archive_with_the_https_pair

        with app.app_context():
            real_open = os.open

            def out_of_space(path, flags, *args, **kwargs):
                # Only the staged content itself: the directory operations
                # (creating it, and removing it afterwards) go through the
                # same call and must keep working, or the leftover would be
                # the injection's rather than the code's.
                if _STAGING_PREFIX in str(path) and flags & os.O_CREAT:
                    raise OSError(errno.ENOSPC, 'No space left on device')
                return real_open(path, flags, *args, **kwargs)

            with monkeypatch.context() as injected:
                injected.setattr(os, 'open', out_of_space)
                with pytest.raises(OSError) as failure:
                    _service().restore_backup(blob, PASSWORD)
            db.session.rollback()

            assert failure.value.errno == errno.ENOSPC
            assert Path(Config.HTTPS_CERT_PATH).read_bytes() == LIVE_CERT
            assert Path(Config.HTTPS_KEY_PATH).read_bytes() == LIVE_KEY
            assert _mode(Config.HTTPS_CERT_PATH) == LIVE_CERT_MODE
            assert _group_names() == before
            assert list(private_staging_root.iterdir()) == [], \
                'the staging of a restore that ran out of space was kept'

    def test_a_refused_publication_puts_back_the_file_it_had_replaced(
            self, app, archive_with_the_https_pair, monkeypatch):
        """The pair is two files and one state: publishing the certificate and
        failing on the key would leave the server with a certificate from the
        archive and the key it was already using -- a pair that matches
        nothing. The first file goes back."""
        blob, before = archive_with_the_https_pair

        with app.app_context():
            key_path = Path(Config.HTTPS_KEY_PATH)
            real_replace = os.replace

            def refused(src, dst, *args, **kwargs):
                if Path(dst) == key_path:
                    raise PermissionError(errno.EACCES, 'Permission denied')
                return real_replace(src, dst, *args, **kwargs)

            with monkeypatch.context() as injected:
                injected.setattr(os, 'replace', refused)
                with pytest.raises(PermissionError):
                    _service().restore_backup(blob, PASSWORD)
            db.session.rollback()

            assert Path(Config.HTTPS_CERT_PATH).read_bytes() == LIVE_CERT, \
                'the certificate published before the failure was kept'
            assert _mode(Config.HTTPS_CERT_PATH) == LIVE_CERT_MODE
            assert key_path.read_bytes() == LIVE_KEY
            assert _group_names() == before
            assert sorted(p.name for p in key_path.parent.iterdir()) == \
                ['https_cert.pem', 'https_key.pem'], \
                'the temporary file of the refused replace survived'

    def test_a_refused_authority_file_stops_the_restore(
            self, app, auth_client, create_ca, groups_archive, monkeypatch):
        """The authority files are staged with the rest and published once
        the transaction has committed, so a publication that is refused puts
        back what it replaced and the restore raises: the rows go back with
        it and the file on disk is the one that was there.

        Written in place, as they were, a restore that failed afterwards left
        every authority file holding the archive's content while the rows had
        gone back. And before that, every failure here was `pass`: a restore
        that could not write a single file still reported success.
        """
        from models import CA
        from utils.file_naming import ca_cert_path
        blob, before = groups_archive
        created = create_ca(cn='Fault Injection File CA')

        try:
            with app.app_context():
                target = ca_cert_path(db.session.get(CA, created['id']))
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b'the authority file already on disk')
                real_replace = os.replace

                def refused(src, dst, *args, **kwargs):
                    if Path(dst) == target:
                        raise PermissionError(errno.EACCES, 'Permission denied')
                    return real_replace(src, dst, *args, **kwargs)

                with monkeypatch.context() as injected:
                    injected.setattr(os, 'replace', refused)
                    with pytest.raises(PermissionError):
                        _service().restore_backup(blob, PASSWORD)
                db.session.rollback()

                assert target.read_bytes() == b'the authority file already on disk'
                assert _group_names() == before, \
                    'a file that could not be written left the rows applied'
                assert not [p for p in target.parent.iterdir()
                            if p.name.startswith('.ucm_restore_')], \
                    'the temporary file of the refused replace survived'
        finally:
            auth_client.delete(f"/api/v2/cas/{created['id']}")


class TestAnAuditFailureChangesNoVerdict:
    """The audit trail records what happened; it is not what happened.

    Both directions matter, and they are not symmetric. A write that fails
    must not turn a completed operation into a reported failure -- the
    administrator would restore again over an instance that is already
    restored. And an audit that works must not be the thing that makes a
    failed operation look done: the success entry is written after the work,
    never before it.
    """

    def test_a_restore_that_worked_is_not_failed_by_the_audit(
            self, app, auth_client, groups_archive, monkeypatch, tmp_path):
        from models.group import Group
        blob, _before = groups_archive

        store = tmp_path / 'sessions'
        store.mkdir()
        monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(store))
        _no_real_restart(monkeypatch)
        _audit_is_down(monkeypatch)

        response = _restore_through_the_route(auth_client, blob)

        assert response.status_code == 200, response.data
        with app.app_context():
            assert Group.query.filter_by(name=GROUP_NAME).first() is not None

    def test_a_restore_that_failed_is_never_audited_as_a_success(
            self, app, auth_client, groups_archive, monkeypatch):
        """The archive is damaged after it was sealed, so the restore is
        refused before its first write; nothing may claim otherwise."""
        blob, before = groups_archive
        damaged = bytearray(blob)
        damaged[-1] ^= 0xFF

        calls = _audit_spy(monkeypatch)
        response = _restore_through_the_route(auth_client, bytes(damaged))

        assert response.status_code == 400
        assert not [call for call in calls
                    if call.get('action') == 'system_restore'
                    and call.get('success')], \
            'a refused restore was recorded as a successful one'
        with app.app_context():
            assert _group_names() == before

    def test_a_scheduled_backup_that_worked_survives_an_audit_that_is_down(
            self, app, backup_settings_sandbox, monkeypatch):
        from services.backup import schedule
        with app.app_context():
            _enable_unattended_backups()
            monkeypatch.setattr(
                'services.backup.schedule.BackupService.iter_backup',
                lambda self, password, **kwargs: b'the archive bytes')
            _audit_is_down(monkeypatch)

            result = schedule.run_scheduled_backup()

            assert result['status'] == 'ok'
            assert len(list(backup_settings_sandbox.glob(
                'ucm_backup_*.ucmbkp'))) == 1
            assert schedule.get_schedule()['last_outcome'] == 'ok'

    def test_an_audit_that_is_down_does_not_mask_the_failure_it_records(
            self, app, backup_settings_sandbox, monkeypatch):
        """The failure path audits too. If that write raised and replaced the
        exception, the scheduler would be told the audit was unreachable and
        never that the backup did not happen."""
        from services.backup import schedule
        with app.app_context():
            _enable_unattended_backups()
            monkeypatch.setattr(
                'services.backup.schedule.BackupService.iter_backup',
                lambda self, password, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('the export could not be produced')))
            _audit_is_down(monkeypatch)

            with pytest.raises(RuntimeError) as failure:
                schedule.run_scheduled_backup()

            assert 'export' in str(failure.value), \
                'the audit failure replaced the failure it was recording'
            status = schedule.get_schedule()
            assert status['last_outcome'] == 'failed'
            assert 'export' in (status['last_outcome_reason'] or '')

    def test_the_outcome_row_refusing_to_be_written_does_not_fail_the_backup(
            self, app, backup_settings_sandbox, monkeypatch):
        """The outcome is a report kept across restarts, not the work. Its
        write is guarded for exactly this: the archive is on disk, its
        schedule timestamp is stored -- so the run does not come due again --
        and only the report of it is missing."""
        from sqlalchemy.orm.session import Session
        from services.backup import schedule
        with app.app_context():
            _enable_unattended_backups()
            monkeypatch.setattr(
                'services.backup.schedule.BackupService.iter_backup',
                lambda self, password, **kwargs: b'the archive bytes')
            _audit_spy(monkeypatch)

            real_commit = Session.commit
            refused = []

            def commit(self, *args, **kwargs):
                pending = list(self.new) + list(self.dirty)
                if any(getattr(row, 'key', None) in _OUTCOME_KEYS
                       for row in pending):
                    refused.append(1)
                    raise RuntimeError('the outcome row could not be written')
                return real_commit(self, *args, **kwargs)

            with monkeypatch.context() as injected:
                injected.setattr(Session, 'commit', commit)
                result = schedule.run_scheduled_backup()
            db.session.rollback()

            assert refused, 'the outcome write was never reached'
            assert result['status'] == 'ok'
            assert len(list(backup_settings_sandbox.glob(
                'ucm_backup_*.ucmbkp'))) == 1
            assert schedule._get('backup.last_run'), \
                'the schedule timestamp was lost with the outcome report'


class TestRetentionThatCannotDeleteEverything:
    """One archive that refuses to be deleted -- an immutable snapshot, a
    file another process holds, a mount gone read-only -- must not leave the
    directory in a state the catalogue disagrees with, and must never cost
    the last restore point."""

    def _five_recorded_archives(self, directory):
        """Five archives, all older than the retention age, newest last."""
        return [
            _write_archive(directory,
                           f'ucm_backup_2000010{index}_000000.ucmbkp',
                           bytes([65 + index]) * 600, 100 - index)
            for index in range(5)
        ]

    def test_one_failed_deletion_neither_stops_the_batch_nor_is_counted(
            self, app, backup_settings_sandbox, monkeypatch):
        from services.backup import schedule, storage
        directory = backup_settings_sandbox
        with app.app_context():
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '0')
            archives = self._five_recorded_archives(directory)
            stubborn = archives[1]
            real_unlink = os.unlink

            def flaky(path, *args, **kwargs):
                if str(path) == str(stubborn):
                    raise OSError(errno.EPERM, 'Operation not permitted')
                return real_unlink(path, *args, **kwargs)

            with monkeypatch.context() as injected:
                injected.setattr(os, 'unlink', flaky)
                removed = schedule.run_backup_retention()

            surviving = sorted(directory.glob('ucm_backup_*.ucmbkp'))
            assert removed == len(archives) - len(surviving), \
                'the count reported includes an archive that is still there'
            assert stubborn in surviving
            assert archives[2] not in surviving and archives[3] not in surviving, \
                'the failure stopped the deletions that came after it'

            # Nothing that is still here contradicts what was recorded of it.
            paths = [str(path) for path in surviving]
            assert storage.tampered(paths) == []
            assert storage.newest_validated(paths) == str(archives[-1])

    def test_the_last_provable_restore_point_is_never_the_one_that_goes(
            self, app, backup_settings_sandbox, monkeypatch):
        """And once an archive is written again, the catalogue stops vouching
        for the names retention removed: a record left behind could otherwise
        vouch for a name a new file reuses."""
        from services.backup import schedule, storage
        directory = backup_settings_sandbox
        with app.app_context():
            _set('backup_retention_days', '7')
            _set('backup_min_keep', '1')
            _set('backup_max_total_mb', '0')
            archives = self._five_recorded_archives(directory)
            newest = archives[-1]
            real_unlink = os.unlink

            def flaky(path, *args, **kwargs):
                if str(path) == str(archives[0]):
                    raise OSError(errno.EROFS, 'Read-only file system')
                return real_unlink(path, *args, **kwargs)

            with monkeypatch.context() as injected:
                injected.setattr(os, 'unlink', flaky)
                schedule.run_backup_retention()

            assert newest.exists(), \
                'the last archive that still matches its record was removed'

            storage.create_archive(b'a newer archive than any of these')
            on_disk = {path.name for path in directory.glob('ucm_backup_*.ucmbkp')}
            assert set(storage.read_catalog(directory)) == on_disk, \
                'the catalogue still vouches for archives that are gone'


class TestARestartThatCannotBeAskedFor:
    """The restart is what makes the restore whole for the other workers, and
    it is the one step that happens after everything is already committed and
    published. It cannot be a reason to report a failure, and it cannot be
    passed over in silence either: the operator has to be told to do it."""

    def test_the_operator_is_told_and_the_restore_is_not_taken_back(
            self, app, auth_client, groups_archive, monkeypatch, tmp_path):
        from models.group import Group
        from utils import service_manager
        blob, _before = groups_archive

        store = tmp_path / 'sessions'
        store.mkdir()
        monkeypatch.setitem(app.config, 'SESSION_FILE_DIR', str(store))
        monkeypatch.setattr(
            service_manager, 'restart_service',
            lambda: (_ for _ in ()).throw(
                OSError(errno.EROFS, 'Read-only file system')))

        response = _restore_through_the_route(auth_client, blob)

        assert response.status_code == 200, response.data
        body = json.loads(response.data)
        assert body['data']['restart_requested'] is False
        assert 'restart' in body['message'].lower(), \
            f'nothing told the operator to restart: {body["message"]}'

        with app.app_context():
            assert Group.query.filter_by(name=GROUP_NAME).first() is not None, \
                'a restart that could not be requested undid the restore'


class TestEachScheduledFailureIsReportedForWhatItIs:
    """Four different failures, four different things to do about them. They
    used to be one silent log line and a green scheduler view; what they must
    produce now is an outcome an administrator can act on, an audit entry,
    and -- the reason the disk once filled -- no second archive a minute
    later when the first one is already there."""

    def _unattended_run_fails(self, monkeypatch, injection):
        from services.backup import schedule
        _enable_unattended_backups()
        calls = _audit_spy(monkeypatch)
        injection()
        return schedule, calls

    def test_an_export_that_fails_leaves_no_archive_and_names_itself(
            self, app, backup_settings_sandbox, monkeypatch):
        with app.app_context():
            schedule, calls = self._unattended_run_fails(
                monkeypatch,
                lambda: monkeypatch.setattr(
                    'services.backup.schedule.BackupService.iter_backup',
                    lambda self, password, **kwargs: (_ for _ in ()).throw(
                        RuntimeError('the export could not be produced'))))

            with pytest.raises(RuntimeError):
                schedule.run_scheduled_backup()

            status = schedule.get_schedule()
            assert status['last_outcome'] == 'failed'
            assert 'export' in status['last_outcome_reason']
            assert status['last_archive'] is None
            assert not list(backup_settings_sandbox.glob('ucm_backup_*'))
            assert [call['success'] for call in calls] == [False]
            assert schedule._get('backup.last_run') is None, \
                'a run that produced nothing must be due again on the next tick'

    def test_a_write_that_fails_leaves_no_archive_and_names_itself(
            self, app, backup_settings_sandbox, monkeypatch):
        from services.backup import storage
        with app.app_context():
            schedule, calls = self._unattended_run_fails(
                monkeypatch,
                lambda: (
                    monkeypatch.setattr(
                        'services.backup.schedule.BackupService.iter_backup',
                        lambda self, password, **kwargs: b'the archive bytes'),
                    monkeypatch.setattr(
                        storage, 'write_archive_atomically',
                        lambda directory, name, data: (_ for _ in ()).throw(
                            OSError(errno.ENOSPC, 'No space left on device'))),
                ))

            with pytest.raises(OSError) as failure:
                schedule.run_scheduled_backup()

            assert failure.value.errno == errno.ENOSPC
            status = schedule.get_schedule()
            assert status['last_outcome'] == 'failed'
            assert 'space' in status['last_outcome_reason'].lower()
            assert not list(backup_settings_sandbox.glob('ucm_backup_*.ucmbkp'))
            assert [call['success'] for call in calls] == [False]

    def test_an_archive_that_does_not_read_back_is_removed_and_reported(
            self, app, backup_settings_sandbox, monkeypatch):
        """A short write parses as a container and restores as nothing. It is
        not a restore point, so it is neither kept nor recorded, and the run
        is reported as the failure it is."""
        from services.backup import storage
        from services.backup.errors import BackupValidationError
        with app.app_context():
            schedule, calls = self._unattended_run_fails(
                monkeypatch,
                lambda: (
                    monkeypatch.setattr(
                        'services.backup.schedule.BackupService.iter_backup',
                        lambda self, password, **kwargs: b'the archive bytes'),
                    monkeypatch.setattr(
                        storage, 'digest_of',
                        lambda path: (3, 'not the digest that was written')),
                ))

            with pytest.raises(BackupValidationError):
                schedule.run_scheduled_backup()

            status = schedule.get_schedule()
            assert status['last_outcome'] == 'failed'
            assert 'read back' in status['last_outcome_reason']
            assert not list(backup_settings_sandbox.glob('ucm_backup_*.ucmbkp'))
            assert storage.read_catalog(backup_settings_sandbox) == {}, \
                'an archive that could not be validated was still recorded'
            assert [call['success'] for call in calls] == [False]

    def test_a_schedule_that_cannot_be_reserved_writes_nothing_and_says_so(
            self, app, backup_settings_sandbox, monkeypatch):
        """The run reserves its slot before writing: a reservation that cannot be
        stored is a failure with no archive, never an archive the schedule forgets."""
        from services.backup import schedule as schedule_module
        with app.app_context():
            schedule, calls = self._unattended_run_fails(
                monkeypatch,
                lambda: (
                    monkeypatch.setattr(
                        'services.backup.schedule.BackupService.iter_backup',
                        lambda self, password, **kwargs: b'the archive bytes'),
                    monkeypatch.setattr(
                        schedule_module, 'config_compare_and_set',
                        lambda *a: (_ for _ in ()).throw(RuntimeError('the row was refused'))),
                ))

            with pytest.raises(schedule.ScheduledBackupError):
                schedule.run_scheduled_backup()

            status = schedule.get_schedule()
            assert status['last_outcome'] == 'failed'
            assert 'reserved' in status['last_outcome_reason']
            assert status['last_archive'] is None
            assert not list(backup_settings_sandbox.glob('ucm_backup_*.ucmbkp'))
            assert [call['success'] for call in calls] == [False]


class TestRecordingTheOutcomeCannotFailTheBackup:
    """`_record_outcome` guarded only its commit. The query and the add in
    front of it could fail too, and the exception then left the function,
    reached the caller, and turned a backup that is on disk and readable into
    a recorded failure -- which then called this again from its own `except`,
    replacing the original error with this one."""

    def test_a_failure_before_the_commit_is_swallowed_like_one_after_it(
            self, app, monkeypatch):
        from services.backup import schedule

        with app.app_context():
            from models import SystemConfig

            def explode(*args, **kwargs):
                raise RuntimeError('the session is gone')

            monkeypatch.setattr(SystemConfig, 'query', property(explode))

            # Must not raise: the caller treats anything escaping as a failed
            # backup.
            schedule._record_outcome('ok', None)

    def test_the_outcome_is_still_recorded_when_nothing_fails(self, app):
        from services.backup import schedule

        with app.app_context():
            from models import SystemConfig, db as _db

            schedule._record_outcome('ok', 'nothing to report')
            row = SystemConfig.query.filter_by(
                key=schedule._LAST_OUTCOME_KEY).first()

            assert row is not None and row.value == 'ok'
            _db.session.rollback()
