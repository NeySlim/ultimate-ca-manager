"""A restored account is the account the archive holds, not six of its columns.

`_restore_users` wrote username, email, full name, role, active and the
password hash. The manifest declares far more, and the export has carried
them since the archive was made manifest-driven: every one of the rest was
dropped on the way back in. An account came back without its MFA secret,
without its backup codes, without the SSO identity that binds it to its
provider and without the custom role that gives it anything beyond its base
rights -- and the restore reported a success.
"""
import pytest

from models import db, User
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    """An include map carrying just these sections."""
    return {name: name in names for name in manifest.SECTIONS}


@pytest.fixture
def furnished_user(app, create_user):
    """A user with everything an account can carry, removed afterwards."""
    create_user(username='zzrestore-columns', role='operator')

    with app.app_context():
        user = User.query.filter_by(username='zzrestore-columns').first()
        user.full_name = 'Restore Columns'
        user.totp_secret = 'ZZTOTPSECRET234567'
        user.mfa_enabled = True
        user.totp_confirmed = True
        user.backup_codes = '["code-one", "code-two"]'
        user.sso_external_id = 'zz-external-id'
        db.session.commit()
        carried = {
            'totp_secret': user.totp_secret,
            'backup_codes': user.backup_codes,
            'sso_external_id': user.sso_external_id,
            'full_name': user.full_name,
        }

    yield carried

    with app.app_context():
        User.query.filter_by(username='zzrestore-columns').delete(
            synchronize_session=False)
        db.session.commit()


def _archive_of_users(app):
    with app.app_context():
        return _service().create_backup(PASSWORD, include=_only('users'))


class TestEveryColumnComesBack:
    def test_the_mfa_secret_and_backup_codes_survive(self, app, furnished_user):
        """The two columns that decide whether the account can log in again."""
        blob = _archive_of_users(app)

        with app.app_context():
            user = User.query.filter_by(username='zzrestore-columns').first()
            user.totp_secret = None
            user.backup_codes = None
            user.mfa_enabled = False
            user.totp_confirmed = False
            db.session.commit()

            _service().restore_backup(blob, PASSWORD, mode='merge')
            db.session.expire_all()
            restored = User.query.filter_by(username='zzrestore-columns').first()

            assert restored.totp_secret == furnished_user['totp_secret']
            assert restored.backup_codes == furnished_user['backup_codes']
            assert restored.mfa_enabled is True
            assert restored.totp_confirmed is True

    def test_the_sso_identity_survives(self, app, furnished_user):
        """Without it the account is no longer the one the provider knows."""
        blob = _archive_of_users(app)

        with app.app_context():
            user = User.query.filter_by(username='zzrestore-columns').first()
            user.sso_external_id = None
            db.session.commit()

            _service().restore_backup(blob, PASSWORD, mode='merge')
            db.session.expire_all()
            restored = User.query.filter_by(username='zzrestore-columns').first()

            assert restored.sso_external_id == furnished_user['sso_external_id']

    def test_no_declared_column_is_left_behind(self, app, furnished_user):
        """The contract, rather than a list of columns written by hand: what
        the manifest declares and the archive carries is what the row holds
        afterwards."""
        blob = _archive_of_users(app)
        section = manifest.SECTIONS['users']

        with app.app_context():
            archived = next(
                row for row in _service()._decrypt_framed(blob, PASSWORD)[1]['users']
                if row['username'] == 'zzrestore-columns')

            from sqlalchemy import inspect as sa_inspect

            user = User.query.filter_by(username='zzrestore-columns').first()
            nullable = {c.name for c in sa_inspect(User).local_table.columns
                        if c.nullable}
            for column in archived:
                if column in section.exclude or column in section.handled:
                    continue
                if column in ('id', 'username') or column.startswith('_'):
                    continue
                # Only what the schema lets go: emptying a required column
                # would be refused by the database, not by the restore.
                if column in nullable and hasattr(user, column):
                    setattr(user, column, None)
            db.session.commit()

            _service().restore_backup(blob, PASSWORD, mode='merge')
            db.session.expire_all()
            restored = User.query.filter_by(username='zzrestore-columns').first()

            lost = []
            for column, value in archived.items():
                if column in section.exclude or column in section.handled:
                    continue
                if column == 'id' or column.startswith('_'):
                    continue
                if column.endswith('_ref'):
                    continue
                if value in (None, '', False):
                    continue
                if getattr(restored, column, None) in (None, ''):
                    lost.append(column)

        assert lost == [], f'columns the archive carried and the restore dropped: {lost}'


class TestThePasswordIsNotLostToAnOldArchive:
    @pytest.mark.parametrize('how', ['absent', 'empty'])
    def test_an_archive_without_a_hash_keeps_the_working_one(
            self, app, furnished_user, how):
        """An archive written by a version that did not carry the hash would
        otherwise lock every account out of the instance.

        Two shapes, and only the second reaches the guard: a key the archive
        does not have at all is never applied, since the restore walks the
        keys the row holds. A key the archive holds and sets to nothing is
        applied, and without the guard it emptied a column the account cannot
        sign in without -- and that the database refuses to leave empty, so
        the whole restore died on it.
        """
        blob = _archive_of_users(app)
        service = _service()

        with app.app_context():
            key, payload = service._decrypt_framed(blob, PASSWORD)
            for row in payload['users']:
                if how == 'absent':
                    row.pop('password_hash', None)
                else:
                    row['password_hash'] = None

            user = User.query.filter_by(username='zzrestore-columns').first()
            before = user.password_hash
            assert before, 'the fixture user has no password to protect'

            service._restore_users(payload, {'users': 0},
                                   _plan_for(payload))
            db.session.flush()
            db.session.expire_all()
            restored = User.query.filter_by(username='zzrestore-columns').first()

            assert restored.password_hash == before
            db.session.rollback()


def _plan_for(payload):
    from services.backup.restore.plan import RestorePlan

    return RestorePlan.build(payload)


class TestASecretGoesBackWhereTheApplicationReadsIt:
    """A secret is put back by its manifest name, which is the model's own
    attribute, and that is deliberate in both directions.

    Where the attribute is a property over a private column, the property
    re-encrypts with this installation's key: that is what makes an archive
    restorable somewhere else, and writing the private column directly is the
    bug that lost at-rest encryption for the SSO and SMTP credentials.

    Where it is a plain column, the application reads the column itself --
    `pyotp.TOTP(user.totp_secret)` -- so the archive's value is exactly what
    belongs in it. Encrypting those on the way in would hand the application
    a ciphertext it never decrypts: an account whose MFA can no longer be
    verified, restored from a backup that looked complete.
    """

    def test_the_totp_secret_is_usable_by_the_code_that_reads_it(
            self, app, furnished_user):
        import pyotp

        blob = _archive_of_users(app)

        with app.app_context():
            user = User.query.filter_by(username='zzrestore-columns').first()
            user.totp_secret = None
            db.session.commit()

            _service().restore_backup(blob, PASSWORD, mode='merge')
            db.session.expire_all()
            restored = User.query.filter_by(username='zzrestore-columns').first()

            # The exact call the login path makes. A ciphertext raises here.
            code = pyotp.TOTP(restored.totp_secret).now()

        assert len(code) == 6 and code.isdigit()
