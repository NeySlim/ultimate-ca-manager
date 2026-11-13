"""The profile API and the per-profile keytab: write scope of the upload, composed file kept in step."""
import io
import json

import pytest

from models import ClusterCommand, User, WindowsEnrollmentProfile, db
from models.rbac import CustomRole
from services import cluster_commands as cc
from services import shared_files
from services.kerberos import keytab_format, negotiate_auth
# The fixture builds the default profile, a second one and the node file in a tmp path
from tests.test_keytab_composed import HOST, ONE, TWO, profiles  # noqa: F401

URL = '/api/v2/windows-profiles'
UPLOAD = '/api/v2/kerberos/keytab'


def _upload(client, data, profile_id):
    return client.post(UPLOAD, data={'file': (io.BytesIO(data), 'k.keytab'), 'profile_id': str(profile_id)},
                       content_type='multipart/form-data')


def _realms():
    return sorted({e.realm for e in keytab_format.read_entries(negotiate_auth.KEYTAB_PATH.read_bytes())})


@pytest.fixture
def kerberos_writer(app, auth_client):
    """A viewer holding write:kerberos and nothing on xcep."""
    r = auth_client.post('/api/v2/rbac/roles', json={'name': 'wp-kt-writer',
                                                     'permissions': ['read:kerberos', 'write:kerberos']})
    assert r.status_code == 200, r.data
    role_id = r.get_json()['data']['id']
    body = {'username': 'wp_kt_writer', 'password': 'TestPass123!', 'email': 'wpkt@test.local',
            'role': 'viewer', 'custom_role_id': role_id}
    r = auth_client.post('/api/v2/users', json=body)
    assert r.status_code in (200, 201), r.data
    c = app.test_client()
    assert c.post('/api/v2/auth/login', json={'username': body['username'],
                                              'password': body['password']}).status_code == 200
    yield c
    with app.app_context():
        User.query.filter_by(username=body['username']).delete()
        CustomRole.query.filter_by(id=role_id).delete()
        db.session.commit()


def test_a_keytab_for_a_profile_needs_the_write_scope_of_profiles(app, kerberos_writer, profiles):  # noqa: F811
    r = _upload(kerberos_writer, TWO, profiles.two)
    assert r.status_code == 403
    with app.app_context():
        assert db.session.get(WindowsEnrollmentProfile, profiles.two).keytab is None


def test_the_profile_api_carries_no_second_keytab_path(auth_client, profiles):  # noqa: F811
    assert _upload(auth_client, TWO, profiles.two).status_code == 200
    got = auth_client.get(f'{URL}/{profiles.two}').get_json()['data']
    assert got['keytab_set'] is True and 'keytab' not in got
    r = auth_client.put(f'{URL}/{profiles.two}', json={'keytab': 'AAAA', 'keytab_set': False})
    assert r.status_code == 200
    assert auth_client.get(f'{URL}/{profiles.two}').get_json()['data']['keytab_set'] is True


def test_disabling_then_deleting_a_profile_recomposes_the_served_file(app, auth_client, profiles,  # noqa: F811
                                                                      monkeypatch):
    from config.settings import Config
    monkeypatch.setattr(Config, 'HA_MODE', True)
    assert _upload(auth_client, ONE, profiles.default).status_code == 200
    assert _upload(auth_client, TWO, profiles.two).status_code == 200
    assert _realms() == ['ONE.TEST', 'TWO.TEST']
    with app.app_context():
        ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).delete()
        db.session.commit()

    assert auth_client.put(f'{URL}/{profiles.two}', json={'enabled': False}).status_code == 200
    assert _realms() == ['ONE.TEST']
    with app.app_context():
        assert ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).count() == 1
        stored = shared_files.read_file(shared_files.KERBEROS_KEYTAB)
    assert stored == negotiate_auth.KEYTAB_PATH.read_bytes()

    assert auth_client.put(f'{URL}/{profiles.two}', json={'enabled': True}).status_code == 200
    assert _realms() == ['ONE.TEST', 'TWO.TEST']

    assert auth_client.delete(f'{URL}/{profiles.two}').status_code == 200
    assert _realms() == ['ONE.TEST']
    with app.app_context():
        assert shared_files.read_file(shared_files.KERBEROS_KEYTAB) == negotiate_auth.KEYTAB_PATH.read_bytes()


def test_a_profile_without_keytab_leaves_the_file_alone(app, auth_client, profiles,  # noqa: F811
                                                        monkeypatch):
    from config.settings import Config
    monkeypatch.setattr(Config, 'HA_MODE', True)
    assert _upload(auth_client, ONE, profiles.default).status_code == 200
    with app.app_context():
        ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).delete()
        db.session.commit()
    assert auth_client.put(f'{URL}/{profiles.two}', json={'enabled': False}).status_code == 200
    assert auth_client.delete(f'{URL}/{profiles.two}').status_code == 200
    assert _realms() == ['ONE.TEST']
    with app.app_context():
        assert ClusterCommand.query.filter_by(kind=cc.RELOAD_KEYTAB).count() == 0
