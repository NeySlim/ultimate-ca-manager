"""Settings kept encrypted at rest, and what a backup does with them.

Two ways a setting is secret: the row says so, or its value is ciphertext (the
scheduled-backup password is stored that way). The export skipped the first
outright and carried the second as ciphertext bound to the source's database
key, so a restored installation lost its scheduled backups either way.
"""
import pytest

from models import SystemConfig, db
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
def secret_setting(app):
    """A setting stored the way the backup password is stored."""
    from utils.encryption import encrypt_if_needed
    with app.app_context():
        SystemConfig.query.filter_by(key='probe_backup_password').delete()
        db.session.add(SystemConfig(key='probe_backup_password',
                                    value=encrypt_if_needed('unattended-secret')))
        db.session.commit()
    yield 'probe_backup_password'
    with app.app_context():
        SystemConfig.query.filter_by(key='probe_backup_password').delete()
        db.session.commit()


class TestTheArchiveCarriesIt:
    def test_the_value_travels_in_the_clear_inside_the_container(
            self, app, secret_setting):
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('configuration'))
            _key, data = svc._decrypt_framed(blob, PASSWORD)
            configuration = data['configuration']

            assert configuration['settings'][secret_setting] == 'unattended-secret'
            assert secret_setting in configuration['encrypted_settings']

    def test_a_setting_flagged_as_encrypted_is_no_longer_skipped(self, app):
        with app.app_context():
            row = SystemConfig(key='probe_flagged_setting', value='plain value')
            row.encrypted = True
            db.session.add(row)
            db.session.commit()
            try:
                svc = _service()
                blob = svc.create_backup(PASSWORD, include=_only('configuration'))
                _key, data = svc._decrypt_framed(blob, PASSWORD)
                settings = data['configuration']['settings']
                assert 'probe_flagged_setting' in settings, \
                    'a setting marked as secret is missing from the archive'
            finally:
                SystemConfig.query.filter_by(key='probe_flagged_setting').delete()
                db.session.commit()


class TestTheRestorePutsItBackEncrypted:
    def test_the_setting_is_usable_and_stored_encrypted_again(
            self, app, secret_setting):
        from utils.encryption import is_encrypted, decrypt_value
        with app.app_context():
            svc = _service()
            blob = svc.create_backup(PASSWORD, include=_only('configuration'))

            # The target holds something else entirely
            row = SystemConfig.query.filter_by(key=secret_setting).first()
            row.value = 'not the archived value'
            row.encrypted = False
            db.session.commit()

            svc.restore_backup(blob, PASSWORD)
            db.session.expire_all()

            row = SystemConfig.query.filter_by(key=secret_setting).first()
            assert row is not None
            assert is_encrypted(row.value), \
                'the secret was written back in the clear'
            assert decrypt_value(row.value) == 'unattended-secret'
            assert row.encrypted is True, \
                'the row no longer says it holds a secret, so the next backup '\
                'would treat it as an ordinary setting'
