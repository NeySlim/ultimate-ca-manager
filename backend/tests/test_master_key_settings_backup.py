"""A setting stored under the master key leaves in the clear in a backup and
comes back under the master key, the layer its readers decrypt."""
import pytest

from models import db, SystemConfig


KEY = 'acme.client.eab_hmac_key'


@pytest.fixture
def eab_setting(app):
    """Put the setting back as it was: the database is shared."""
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        before = (row.value, row.encrypted) if row else None
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first()
        if before is None:
            if row:
                db.session.delete(row)
        else:
            row = row or SystemConfig(key=KEY)
            row.value, row.encrypted = before
            db.session.add(row)
        db.session.commit()


def test_a_master_key_setting_is_exported_in_the_clear(
        app, eab_setting, encryption_enabled, monkeypatch):
    from types import SimpleNamespace
    from security.encryption import encrypt_text
    from services.backup import BackupService, export_core

    with app.app_context():
        row = SystemConfig.query.filter_by(key=KEY).first() or SystemConfig(key=KEY)
        row.value = encrypt_text('hmac-in-clear')
        db.session.add(row)
        db.session.commit()

        # Only this row: others may hold secrets under a key this test lacks
        monkeypatch.setattr(export_core, 'SystemConfig', SimpleNamespace(
            query=SimpleNamespace(all=lambda: [row])))
        exported = BackupService()._export_configuration(True)

    assert exported['settings'][KEY] == 'hmac-in-clear'
    assert KEY in exported['encrypted_settings']


def test_a_master_key_setting_is_restored_under_the_master_key(
        app, eab_setting, encryption_enabled):
    from security.encryption import decrypt_text, key_encryption
    from services.backup.restore.settings import restore_encrypted_settings

    with app.app_context():
        restore_encrypted_settings({'settings': {KEY: 'hmac-in-clear'}}, [KEY])
        db.session.commit()
        stored = SystemConfig.query.filter_by(key=KEY).first().value

    # decrypt_text is what the ACME client reads it with
    assert key_encryption.is_string_encrypted(stored)
    assert decrypt_text(stored) == 'hmac-in-clear'
