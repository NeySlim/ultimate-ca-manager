"""The scheduled-backup password survives saves that do not change it.

GET never returns the password, so the Settings screen holds an empty field
and every section's save sent `backup_password: ''` -- which erased the
password the administrator had just set.
"""
import json

import pytest

from models import db, SystemConfig


PASSWORD = 'Correct-Horse-Battery-9'


def _patch(client, payload):
    return client.patch('/api/v2/settings/general', data=json.dumps(payload),
                        content_type='application/json')


def _stored():
    row = SystemConfig.query.filter_by(key='backup_password').first()
    return row.value if row else None


@pytest.fixture(autouse=True)
def keep_backup_password(app):
    """The database is shared: put the password back as it was."""
    with app.app_context():
        before = _stored()
    yield
    with app.app_context():
        row = SystemConfig.query.filter_by(key='backup_password').first()
        if before is None:
            if row:
                db.session.delete(row)
        elif row:
            row.value = before
        else:
            db.session.add(SystemConfig(key='backup_password', value=before))
        db.session.commit()


def _password_set(client):
    response = client.get('/api/v2/settings/general')
    assert response.status_code == 200
    data = response.get_json()['data']
    assert data['backup_password'] == ''
    return data['backup_password_set']


def test_saving_another_setting_keeps_the_password(app, auth_client):
    assert _patch(auth_client, {'backup_password': PASSWORD}).status_code == 200
    with app.app_context():
        stored = _stored()
    assert stored

    # What the screen sends when any other section is saved
    response = _patch(auth_client, {'backup_retention_days': 30,
                                    'backup_password': ''})
    assert response.status_code == 200, response.data

    with app.app_context():
        assert _stored() == stored
        from services.backup.schedule import _get_backup_password
        assert _get_backup_password() == PASSWORD
    assert _password_set(auth_client) is True


def test_clear_flag_removes_the_password(app, auth_client):
    assert _patch(auth_client, {'backup_password': PASSWORD}).status_code == 200

    response = _patch(auth_client, {'clear_backup_password': True})
    assert response.status_code == 200, response.data

    with app.app_context():
        assert not _stored()
    assert _password_set(auth_client) is False


def test_clear_flag_with_a_new_password_is_refused(app, auth_client):
    assert _patch(auth_client, {'backup_password': PASSWORD}).status_code == 200
    with app.app_context():
        stored = _stored()

    response = _patch(auth_client, {'clear_backup_password': True,
                                    'backup_password': 'Another-Horse-Battery-7'})
    assert response.status_code == 400, response.data

    with app.app_context():
        assert _stored() == stored


@pytest.mark.parametrize('flag', ['true', 1, None])
def test_clear_flag_must_be_a_boolean(app, auth_client, flag):
    assert _patch(auth_client, {'backup_password': PASSWORD}).status_code == 200
    with app.app_context():
        stored = _stored()

    response = _patch(auth_client, {'clear_backup_password': flag})
    assert response.status_code == 400, response.data

    with app.app_context():
        assert _stored() == stored


def test_clearing_the_password_is_audited(app, auth_client):
    from models import AuditLog
    assert _patch(auth_client, {'backup_password': PASSWORD}).status_code == 200
    assert _patch(auth_client, {'clear_backup_password': True}).status_code == 200

    with app.app_context():
        entry = (AuditLog.query.filter_by(action='settings_update')
                 .order_by(AuditLog.id.desc()).first())
        assert 'backup password cleared' in entry.details
