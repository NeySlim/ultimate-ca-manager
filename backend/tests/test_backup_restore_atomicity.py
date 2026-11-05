"""A restore happens entirely, or not at all.

The gate of this work: an error injected at any phase must leave the database
and the files exactly as they were. Each test breaks one phase and checks that
the instance did not move.
"""
import pytest

from models import db
from services.backup import manifest

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


@pytest.fixture
def archive_of_one_group(app):
    """An archive holding one group, and a target that has lost it."""
    from models.group import Group
    with app.app_context():
        Group.query.filter_by(name='atomicity-group').delete()
        db.session.add(Group(name='atomicity-group'))
        db.session.commit()

        blob = _service().create_backup(PASSWORD, include=_only('groups'))

        Group.query.filter_by(name='atomicity-group').delete()
        db.session.commit()
        yield blob, {group.name for group in Group.query.all()}

        Group.query.filter_by(name='atomicity-group').delete()
        db.session.commit()


def _names():
    from models.group import Group
    return {group.name for group in Group.query.all()}


class TestAnErrorAtAnyPhaseChangesNothing:
    def test_a_failure_while_applying(self, app, archive_of_one_group, monkeypatch):
        blob, before = archive_of_one_group
        import services.backup.restore_rbac as rbac
        with app.app_context():
            monkeypatch.setattr(
                rbac.RestoreRbacMixin, '_restore_groups',
                lambda self, data, results, *rest: (_ for _ in ()).throw(
                    RuntimeError('the section could not be applied')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before

    def test_a_failure_while_resolving_references(self, app, archive_of_one_group,
                                                  monkeypatch):
        blob, before = archive_of_one_group
        import services.backup.restore_core as core
        with app.app_context():
            monkeypatch.setattr(
                core, 'relink_references',
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('references could not be resolved')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before

    def test_a_failure_while_removing_what_the_archive_omits(
            self, app, archive_of_one_group, monkeypatch):
        blob, before = archive_of_one_group
        import services.backup.restore_core as core
        with app.app_context():
            monkeypatch.setattr(
                core, 'remove_before_writes',
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('the replacement could not be carried out')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before

    def test_a_failure_while_publishing_the_files(self, app, archive_of_one_group,
                                                 monkeypatch):
        """The files are published inside the transaction, so a file that
        cannot be placed takes the database back with it."""
        blob, before = archive_of_one_group
        import services.backup.restore.files as files
        with app.app_context():
            monkeypatch.setattr(
                files.StagedFiles, 'publish',
                lambda self: (_ for _ in ()).throw(
                    OSError('the files could not be published')))

            with pytest.raises(OSError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before

    def test_a_failure_at_the_commit_puts_the_files_back(self, app, tmp_path,
                                                         monkeypatch):
        """The last thing that can fail is the commit, and by then the files
        are already in place."""
        from services.backup.restore.files import StagedFiles

        destination = tmp_path / 'https_cert.pem'
        destination.write_bytes(b'the certificate in use')

        staged = StagedFiles()
        staged.stage(destination, b'the certificate from the archive')
        staged.publish()
        assert destination.read_bytes() == b'the certificate from the archive'

        # What restore_backup does when the transaction block raises
        staged.unpublish()
        staged.discard()
        assert destination.read_bytes() == b'the certificate in use'


class TestTwoRestoresLeaveTheSameInstance:
    def test_restoring_twice_changes_nothing_the_second_time(
            self, app, archive_of_one_group):
        blob, _before = archive_of_one_group
        with app.app_context():
            _service().restore_backup(blob, PASSWORD)
            first = _names()
            _service().restore_backup(blob, PASSWORD)
            assert _names() == first
