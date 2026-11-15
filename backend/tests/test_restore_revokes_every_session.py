"""After a restore, no session opened before it is accepted, whatever the store.

On the file store, the SQL store (SQLite, and PostgreSQL shared by two nodes) and Redis
shared by two nodes: a session left idle, a session whose request was in flight during
the restore and saved after it, and the session of the operator who restored.
"""
import io
import uuid

import pytest

from models import User, db
from tests.test_factor_change_sessions import (  # noqa: F401 (fixtures)
    PASSWORD, _cleanup, _drop_session_table_from_metadata, _make_user, _open_session,
    _signed_in, nodes)


@pytest.fixture
def restore_carries_data(monkeypatch):
    """The route's own steps after a restore that changed something, without an archive."""
    from services.backup_service import BackupService
    from utils import service_manager
    monkeypatch.setattr(BackupService, 'check_archive_opens', lambda self, *a, **k: None)
    monkeypatch.setattr(BackupService, 'restore_backup_from_stream',
                        lambda self, *a, **k: {'sections_carried': ['users']})
    monkeypatch.setattr(service_manager, 'restart_service', lambda: (True, 'restart requested'))


def _make_admin(application):
    with application.app_context():
        user = User(username=f'restorer-{uuid.uuid4().hex[:8]}', role='admin',
                    email=f'{uuid.uuid4().hex[:8]}@example.test')
        user.set_password(PASSWORD)
        db.session.add(user)
        db.session.commit()
        info = {'id': user.id, 'username': user.username, 'secret': None, 'key': None}
        db.session.remove()
        return info


def _restore(client):
    csrf = client.get('/api/v2/auth/verify').get_json()['data'].get('csrf_token')
    headers = {'X-CSRF-Token': csrf} if csrf else {}
    return client.post('/api/v2/system/restore', headers=headers,
                       data={'password': 'x', 'file': (io.BytesIO(b'x'), 'r.ucmbkp')},
                       content_type='multipart/form-data')


def _refused(application, cookie):
    stale = application.test_client()
    stale.set_cookie('session', cookie)
    return stale.get('/api/v2/account/profile').status_code == 401


@pytest.mark.parametrize('route_node', ['same-node', 'other-node'])
def test_no_session_opened_before_a_restore_is_accepted_after_it(
        nodes, restore_carries_data, route_node):
    from flask import request, session as flask_session
    from auth.unified import AuthManager
    first_node, second_node = nodes
    restoring_node = first_node if route_node == 'same-node' else second_node
    operator = _make_admin(first_node)
    idle_user, busy_user = _make_user(first_node), _make_user(first_node)
    try:
        restorer = _open_session(restoring_node, operator)
        idle = _open_session(first_node, idle_user).get_cookie('session').value
        busy = _open_session(first_node, busy_user).get_cookie('session').value
        operator_cookie = restorer.get_cookie('session').value

        with second_node.test_request_context('/api/v2/account/profile',
                                              headers={'Cookie': f'session={busy}'}):
            assert AuthManager().authenticate_request(request) is not None
            r = _restore(restorer)
            assert r.status_code == 200, r.data
            # the in-flight request ends after the restore and saves its session
            second_node.session_interface.save_session(
                second_node, flask_session, second_node.response_class())

        assert not any(h.startswith('session=') and not h.startswith('session=;')
                       for h in r.headers.getlist('Set-Cookie')), 'the restore re-issued its session'
        assert not _signed_in(restorer), "the operator's session survived the restore"
        for node in (first_node, second_node):
            assert _refused(node, operator_cookie), node
            assert _refused(node, idle), 'an idle session survived the restore'
            assert _refused(node, busy), 'a session in flight survived the restore'
        # A sign-in after the restore is valid on every node
        again = _open_session(first_node, idle_user)
        cookie = again.get_cookie('session').value
        assert not _refused(second_node, cookie)
    finally:
        for user in (operator, idle_user, busy_user):
            _cleanup(first_node, user)


def test_the_epoch_only_moves_forward_and_no_archive_carries_it(app):
    from auth.session_epoch import EPOCH_KEY, advance_epoch, current_epoch
    from models import SystemConfig
    from services.backup import installation
    from services.backup_service import BackupService
    with app.app_context():
        first = advance_epoch()
        assert current_epoch() == first
        assert installation.is_local_setting(EPOCH_KEY)
        # An archive that names the key, from this installation or another, is not obeyed
        BackupService()._restore_settings(
            {'configuration': {'settings': {EPOCH_KEY: '0'}}}, {'settings': 0})
        db.session.commit()
        assert current_epoch() == first
        assert advance_epoch() == first + 1
        row = SystemConfig.query.filter_by(key=EPOCH_KEY).one()
        assert row.value == str(first + 1)


def test_a_session_begun_between_two_restores_is_refused_after_the_second(app, monkeypatch):
    from services.backup.restore import invalidate
    from services.backup.restore.invalidate import invalidate_after_restore
    # The stored sessions stay, as Redis entries do: the epoch alone refuses them
    monkeypatch.setattr(invalidate, '_remove_session_files', lambda: 0)
    monkeypatch.setattr(invalidate, '_revoke_flask_sessions', lambda: 0)
    user = _make_user(app)
    try:
        with app.app_context():
            invalidate_after_restore()
        between = _open_session(app, user).get_cookie('session').value
        assert not _refused(app, between)
        with app.app_context():
            invalidate_after_restore()
        assert _refused(app, between)
    finally:
        _cleanup(app, user)
