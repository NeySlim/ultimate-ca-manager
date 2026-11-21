"""The backup size ceiling travels in an archive and comes back with a restore."""
from models import SystemConfig, db
from services.backup import manifest

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

PASSWORD = 'Ceiling-Restore-Pass-9'


def _set(value):
    row = SystemConfig.query.filter_by(key='backup_max_total_mb').first()
    if row is None:
        db.session.add(SystemConfig(key='backup_max_total_mb', value=value))
    else:
        row.value = value
    db.session.commit()


def test_the_ceiling_is_exported_and_restored(app):
    from services.backup_service import BackupService
    with app.app_context():
        _set('77')
        svc = BackupService()
        blob = svc.create_backup(
            PASSWORD, include={name: name == 'configuration' for name in manifest.SECTIONS})
        _key, data = svc._decrypt_framed(blob, PASSWORD)
        assert data['configuration']['settings']['backup_max_total_mb'] == '77'

        _set('3')
        svc.restore_backup(blob, PASSWORD)
        db.session.expire_all()
        assert SystemConfig.query.filter_by(key='backup_max_total_mb').first().value == '77'
