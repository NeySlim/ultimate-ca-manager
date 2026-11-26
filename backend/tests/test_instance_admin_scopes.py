"""Scopes a fleet console's key holds instead of admin:system (#403).

write:backups starts a backup and follows its job, write:updates installs an update and follows
an HA rolling update; neither opens anything else admin:system guards. Both stay admin-only.
"""
import json

import pytest

from auth.permissions import CUSTOM_ROLE_GRANTABLE_PERMISSIONS, is_reserved_permission
from tests.conftest import assert_success


def _key(auth_client, permissions, name):
    r = auth_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': name, 'permissions': permissions}), content_type='application/json')
    return assert_success(r, 201)['key']


@pytest.fixture(scope='module')
def backup_key(auth_client):
    return _key(auth_client, ['write:backups'], 'console-backup')


@pytest.fixture(scope='module')
def update_key(auth_client):
    return _key(auth_client, ['write:updates'], 'console-update')


@pytest.fixture(scope='module')
def unrelated_key(auth_client):
    return _key(auth_client, ['read:settings', 'write:settings', 'read:instance'], 'console-other')


def _post(app, key, path, body=None):
    return app.test_client().post(path, data=json.dumps(body or {}), content_type='application/json',
                                  headers={'X-API-Key': key})


def _get(app, key, path):
    return app.test_client().get(path, headers={'X-API-Key': key})


@pytest.mark.parametrize('scope', ['write:backups', 'write:updates'])
def test_the_scopes_are_admin_only(scope):
    assert is_reserved_permission(scope)
    assert scope not in CUSTOM_ROLE_GRANTABLE_PERMISSIONS


@pytest.mark.parametrize('scope', ['write:backups', 'write:updates'])
def test_a_non_admin_cannot_mint_them(viewer_client, scope):
    r = viewer_client.post('/api/v2/account/apikeys', data=json.dumps(
        {'name': 'x', 'permissions': [scope]}), content_type='application/json')
    assert r.status_code == 403


def test_write_backups_reaches_the_backup_route(app, backup_key):
    # Past authorisation: the route's own validation answers
    r = _post(app, backup_key, '/api/v2/system/backup/create', {})
    assert r.status_code == 400, r.data
    assert b'password' in r.data.lower()


def test_a_key_without_it_is_refused_the_backup(app, unrelated_key, update_key):
    for key in (unrelated_key, update_key):
        assert _post(app, key, '/api/v2/system/backup/create', {}).status_code == 403


def test_write_backups_follows_backup_jobs_and_no_other_kind(app):
    from api.v2.system import jobs as jobs_routes
    from services import jobs
    kinds = {k for k in jobs.types()}
    with app.test_request_context():
        from flask import g
        g.permissions = ['write:backups']
        readable = {k for k in kinds if jobs_routes._readable(k)}
    assert readable == {'backup'}


def test_write_backups_opens_nothing_else_of_admin_system(app, backup_key):
    for method, path in (('GET', '/api/v2/system/backups'), ('POST', '/api/v2/system/backup/restore'),
                         ('GET', '/api/v2/system/backup/x.ucmbkp/download'),
                         ('POST', '/api/v2/system/database/reset'), ('GET', '/api/v2/system/updates/check')):
        r = _get(app, backup_key, path) if method == 'GET' else _post(app, backup_key, path)
        assert r.status_code == 403, (path, r.status_code)


def test_write_updates_reaches_the_install_route(app, update_key, monkeypatch):
    import services.updates as updates
    monkeypatch.setattr(updates, 'is_container_install', lambda: False)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **kw: {'update_available': False})
    r = _post(app, update_key, '/api/v2/system/updates/install', {})
    assert r.status_code == 400, r.data
    assert b'No update available' in r.data


def test_write_updates_follows_the_rolling_update(app, update_key):
    assert _get(app, update_key, '/api/v2/system/updates/campaign').status_code == 200


def test_a_key_without_it_is_refused_the_update(app, unrelated_key, backup_key):
    for key in (unrelated_key, backup_key):
        assert _post(app, key, '/api/v2/system/updates/install', {}).status_code == 403
        assert _get(app, key, '/api/v2/system/updates/campaign').status_code == 403


def test_write_updates_opens_nothing_else_of_admin_system(app, update_key):
    for method, path in (('POST', '/api/v2/system/updates/campaign/resume'),
                         ('PATCH', '/api/v2/system/updates/settings'),
                         ('POST', '/api/v2/system/backup/create')):
        client = app.test_client()
        r = client.open(path, method=method, data='{}', content_type='application/json',
                        headers={'X-API-Key': update_key})
        assert r.status_code == 403, (path, r.status_code)
