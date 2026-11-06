"""An archive written before the SSH CA scopes existed restores with them.

The upgrade migration widens what is in the database; a restore puts back what
the archive holds, so an older archive is widened the same way on the way in.
"""
import json

import pytest

from models import db
from models.api_key import APIKey
from models.group import Group, permission_list
from models.rbac import CustomRole
from tests.test_backup_export_manifest import PASSWORD, _only, _reseal

from tests.fresh_app import fresh_app_fixtures

app, auth_client, create_ca, create_cert, create_user = fresh_app_fixtures()

NAME = 'ssh-scope-restore'


def _service():
    from services.backup_service import BackupService
    return BackupService()


@pytest.fixture
def archived(app):
    """Rows holding SSH scopes only, then an archive of them; rows removed after."""
    with app.app_context():
        from models import User
        admin = User.query.filter_by(username='admin').first()
        db.session.add_all([
            Group(name=NAME, permissions=['read:ssh', 'write:ssh']),
            CustomRole(name=NAME, permissions=['write:ssh', 'delete:ssh']),
            APIKey(key_hash='f' * 64, user_id=admin.id, name=NAME, permissions=json.dumps(['read:ssh'])),
        ])
        db.session.commit()
        svc = _service()
        blob = svc.create_backup(PASSWORD, include=_only('groups', 'custom_roles', 'api_keys', 'users'))
        _key, data = svc._decrypt_framed(blob, PASSWORD)
    yield svc, blob, data
    with app.app_context():
        Group.query.filter_by(name=NAME).delete()
        CustomRole.query.filter_by(name=NAME).delete()
        APIKey.query.filter_by(name=NAME).delete()
        db.session.commit()


def _restored(app, svc, blob):
    with app.app_context():
        svc.restore_backup(blob, PASSWORD, mode='merge')
        db.session.expire_all()
        return (permission_list(Group.query.filter_by(name=NAME).one().permissions),
                CustomRole.query.filter_by(name=NAME).one().permissions,
                json.loads(APIKey.query.filter_by(name=NAME).one().permissions))


def test_an_older_archive_restores_with_the_ssh_ca_scopes(app, archived):
    svc, blob, data = archived
    data['metadata'].pop('permissions_revision', None)
    data.pop('checksum', None)
    group, role, key = _restored(app, svc, _reseal(svc, blob, data))
    assert group == ['read:ssh', 'read:ssh_cas', 'write:ssh', 'write:ssh_cas']
    assert role == ['write:ssh', 'write:ssh_cas', 'delete:ssh', 'delete:ssh_cas']
    assert key == ['read:ssh', 'read:ssh_cas']


def test_a_current_archive_restores_exactly_what_it_holds(app, archived):
    svc, blob, data = archived
    assert data['metadata']['permissions_revision'] >= 1
    group, role, key = _restored(app, svc, blob)
    assert group == ['read:ssh', 'write:ssh']
    assert role == ['write:ssh', 'delete:ssh']
    assert key == ['read:ssh']
