"""A restore happens entirely, or not at all.

The gate of this work: an error injected at any phase must leave the database
and the files exactly as they were. Each test breaks one phase and checks that
the instance did not move.
"""
import pytest

from models import db
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

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

    @pytest.mark.parametrize('phase', ['remove_before_writes', 'remove_after_writes'])
    def test_a_failure_while_removing_what_the_archive_omits(
            self, app, archive_of_one_group, monkeypatch, phase):
        """Before the writes, or after them with the archive's rows already written."""
        blob, before = archive_of_one_group
        import services.backup.restore_core as core
        with app.app_context():
            monkeypatch.setattr(
                core, phase,
                lambda *args, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('the replacement could not be carried out')))

            with pytest.raises(RuntimeError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before

    def test_a_failure_while_listing_the_files_it_removes(self, app, archive_of_one_group,
                                                           monkeypatch):
        """The list of paths the rows no longer name is the last write of the
        transaction: a failure there takes the rows and the generation back."""
        from services import file_regen_service
        from services.backup import restore_core
        blob, before = archive_of_one_group
        with app.app_context():
            generation = file_regen_service.current_generation()
            monkeypatch.setattr(restore_core, 'keep_named_paths', lambda: (_ for _ in ()).throw(
                OSError('the list could not be written')))

            with pytest.raises(OSError):
                _service().restore_backup(blob, PASSWORD)

            db.session.rollback()
            assert _names() == before
            assert file_regen_service.current_generation() == generation


class TestTwoRestoresLeaveTheSameInstance:
    def test_restoring_twice_changes_nothing_the_second_time(
            self, app, archive_of_one_group):
        blob, _before = archive_of_one_group
        with app.app_context():
            _service().restore_backup(blob, PASSWORD)
            first = _names()
            _service().restore_backup(blob, PASSWORD)
            assert _names() == first
