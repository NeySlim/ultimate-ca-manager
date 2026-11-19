"""The history an archive carries comes back when it is asked for.

Five sections were listed as restored and no code path ever wrote them: the
export collected them, the restore counted them among the sections it
applies, and they went nowhere. An operator who asks for the audit log, the
discovery results or the enrolment history in their archive is asking to get
them back, and was told they had.
"""
import pytest
from sqlalchemy import text

from models import db
from services.backup import manifest
from services.backup.export_generic import load_model
from services.backup.restore_core import GENERIC_SECTIONS, RESTORED_SECTIONS

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'

# The sections that used to be announced and dropped.
HISTORY_SECTIONS = (
    'audit_logs', 'discovered_certificates', 'msca_requests', 'scan_runs',
    'scep_requests',
)


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


class TestNothingIsAnnouncedWithoutBeingWritten:
    def test_every_section_said_to_be_restored_has_a_writer(self):
        """The list is a promise made to the caller: a section in it that no
        code path writes is a restore reporting work it never did.

        Read from the parsed source rather than from its text: a section
        named only in a comment or in the prose of a docstring, which is
        exactly what a restorer emptied of its body leaves behind, used to
        count as a writer.
        """
        import ast
        import glob
        import os

        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        named = set()
        for path in (glob.glob(os.path.join(here, 'services/backup/restore*.py'))
                     + glob.glob(os.path.join(here, 'services/backup/restore/*.py'))):
            tree = ast.parse(open(path).read())
            docstrings = {ast.get_docstring(node)
                          for node in ast.walk(tree)
                          if isinstance(node, (ast.Module, ast.ClassDef,
                                               ast.FunctionDef))}
            # The two lists under test name every section themselves; a name
            # is a writer only where some other statement uses it.
            catalogues = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign) and any(
                        isinstance(target, ast.Name)
                        and target.id in ('RESTORED_SECTIONS', 'GENERIC_SECTIONS')
                        for target in node.targets):
                    catalogues.update(map(id, ast.walk(node)))

            # A section is written where its name is *passed* somewhere:
            # `backup_data.get('x')`, `apply_columns(row, 'x', ...)`. A key of
            # the results counter (`results['x'] += 1`) or of the dictionary
            # that initialises it is bookkeeping, and a restorer emptied of
            # its body keeps both.
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                for argument in list(node.args) + [kw.value for kw in node.keywords]:
                    if (isinstance(argument, ast.Constant)
                            and isinstance(argument.value, str)
                            and id(argument) not in catalogues
                            and argument.value not in docstrings):
                        named.add(argument.value)

        assert named, 'no source was read: the restorers were not found'
        unwritten = sorted(set(RESTORED_SECTIONS) - set(GENERIC_SECTIONS) - named)
        assert unwritten == [], (
            'these sections are announced as restored and nothing writes '
            f'them: {unwritten}')

    @pytest.mark.parametrize('name', HISTORY_SECTIONS)
    def test_the_section_is_applied_from_the_manifest(self, name):
        assert name in GENERIC_SECTIONS, (
            f'{name} is not applied by the generic path, so nothing restores it')


class TestTheHistoryActuallyComesBack:
    def test_an_audit_entry_is_restored(self, app):
        """The audit log is the section an operator is most likely to ask
        for, and the one nothing was writing."""
        with app.app_context():
            db.session.execute(text(
                "INSERT INTO audit_logs (action, details, timestamp) "
                "VALUES ('zzhistory-restore', 'carried by the archive', "
                "'2026-01-01 00:00:00')"))
            db.session.commit()

            blob = _service().create_backup(
                PASSWORD, include=_only('audit_logs'))

            db.session.execute(text(
                "DELETE FROM audit_logs WHERE action = 'zzhistory-restore'"))
            db.session.commit()
            assert db.session.execute(text(
                "SELECT COUNT(*) FROM audit_logs "
                "WHERE action = 'zzhistory-restore'")).scalar() == 0

            try:
                results = _service().restore_backup(
                    blob, PASSWORD, mode='merge')

                assert db.session.execute(text(
                    "SELECT COUNT(*) FROM audit_logs "
                    "WHERE action = 'zzhistory-restore'")).scalar() == 1
                assert results.get('audit_logs', 0) >= 1
            finally:
                db.session.execute(text(
                    "DELETE FROM audit_logs WHERE action = 'zzhistory-restore'"))
                db.session.commit()

    def test_a_section_that_is_not_asked_for_is_not_restored(self, app):
        """They stay opt-in: an archive that does not carry the history does
        not empty it either."""
        with app.app_context():
            blob = _service().create_backup(
                PASSWORD, include=_only('groups'))
            _key, payload = _service()._decrypt_framed(blob, PASSWORD)

        assert not payload.get('audit_logs')


def _columns_of(row):
    """Every column of a row, as plain values, so it can be written again."""
    from sqlalchemy import inspect as sa_inspect

    return {column.key: getattr(row, column.key)
            for column in sa_inspect(type(row)).mapper.columns}


class TestASingletonSectionIsRecognisedOnTheWayBack:
    """Three sections hold one row for the whole installation: the SMTP
    configuration, the notification settings, the Active Directory connector.

    Their identity is the primary key, which the archive carries from the
    source and which means nothing anywhere else. On another installation --
    or on this one after the row has been recreated -- the number does not
    match, so the restore found no row to update and added a second one. The
    installation then held two configurations and used whichever the query
    happened to return.

    `ad_connector` goes through the generic path and is what holds
    `existing_id` to its promise; the other two are restored by hand-written
    restorers that look the row up themselves, and are here because the
    property being asserted -- one row after a restore -- is the same one, and
    whoever moves them onto the generic path should not have to discover it.
    """

    @pytest.mark.parametrize('section_name', [
        'smtp_config', 'notification_config', 'ad_connector'])
    def test_the_row_is_updated_and_not_added_beside(self, app, section_name):
        model = load_model(manifest.SECTIONS[section_name])
        extra = {'type': 'email'} if section_name == 'notification_config' else {}

        with app.app_context():
            # Whatever another file of this worker left behind is put back
            # afterwards. Skipping instead meant the one parametrisation that
            # goes through the generic path, and so the only one that holds
            # `existing_id` to its promise, did not run whenever an earlier
            # file had written a connector of its own.
            standing = [_columns_of(row) for row in model.query.all()]
            model.query.delete(synchronize_session=False)
            db.session.commit()

            db.session.add(model(**extra))
            db.session.commit()
            blob = _service().create_backup(PASSWORD, include=_only(section_name))

            # The row is recreated with another key, so the id the archive
            # carries is not the id the row has here -- the ordinary case on
            # any installation that is not the one the archive came from. The
            # number is set explicitly because SQLite hands a freed rowid
            # straight back, which would hide the very thing being tested;
            # PostgreSQL, whose sequence keeps going, is where this was found.
            model.query.delete(synchronize_session=False)
            db.session.commit()
            db.session.add(model(id=500, **extra))
            db.session.commit()

            try:
                _service().restore_backup(blob, PASSWORD, mode='merge')
                db.session.expire_all()

                assert model.query.count() == 1, (
                    f'{section_name} holds {model.query.count()} rows: the '
                    'restore added a second configuration beside the one that '
                    'was there, and nothing chooses between them')
            finally:
                model.query.delete(synchronize_session=False)
                for columns in standing:
                    db.session.add(model(**columns))
                db.session.commit()
