"""After a restore, no session opened before it is accepted, whatever the store.

On both restore routes: a session left idle, a session whose request was in flight
during the restore and saved after it, the session of the operator who restored, and
sessions the store keeps (as Redis does, whose entries a restore does not remove).
"""
import io
import json
import uuid

import pytest

from models import APIKey, User, db

PASSWORD = 'TestPass123!'
PROTECTED = '/api/v2/account/apikeys'
ROUTES = ('/api/v2/system/restore', '/api/v2/settings/backup/restore')


@pytest.fixture
def restore_carries_data(monkeypatch):
    """The routes' own steps after a restore that changed something, without an archive."""
    from services.backup_service import BackupService
    from utils import service_manager
    monkeypatch.setattr(BackupService, 'restore_backup',
                        lambda self, *a, **k: {'sections_carried': ['users']})
    monkeypatch.setattr(service_manager, 'restart_service', lambda: (True, 'restart requested'))


@pytest.fixture
def accounts(app, create_user):
    names = []

    def make(role='operator'):
        name = f'restore-{uuid.uuid4().hex[:8]}'
        names.append(name)
        create_user(username=name, role=role, email=f'{name}@test.local')
        return name
    yield make
    with app.app_context():
        for name in names:
            user = User.query.filter_by(username=name).first()
            if user is not None:
                APIKey.query.filter_by(user_id=user.id).delete()
                db.session.delete(user)
        db.session.commit()


def _login(app, username):
    client = app.test_client()
    answer = client.post('/api/v2/auth/login',
                         data=json.dumps({'username': username, 'password': PASSWORD}),
                         content_type='application/json')
    assert answer.status_code == 200, answer.data[:300]
    return client


def _cookie(client):
    return client.get_cookie('session').value


def _refused(app, cookie):
    stale = app.test_client()
    stale.set_cookie('session', cookie)
    return stale.get(PROTECTED).status_code == 401


def _restore(client, url):
    return client.post(url, data={'password': 'x', 'file': (io.BytesIO(b'x'), 'r.ucmbkp')},
                       content_type='multipart/form-data')


@pytest.mark.parametrize('url', ROUTES)
def test_no_session_opened_before_a_restore_is_accepted_after_it(
        app, accounts, restore_carries_data, url):
    from flask import request, session as flask_session
    from auth.unified import AuthManager
    restorer = _login(app, accounts('admin'))
    idle = _cookie(_login(app, accounts()))
    busy = _cookie(_login(app, accounts()))
    operator = _cookie(restorer)

    with app.test_request_context(PROTECTED, headers={'Cookie': f'session={busy}'}):
        assert AuthManager().authenticate_request(request) is not None
        answer = _restore(restorer, url)
        assert answer.status_code == 200, answer.data
        # The request in flight ends after the restore and saves its session
        app.session_interface.save_session(app, flask_session, app.response_class())

    assert not any(h.startswith('session=') and not h.startswith('session=;')
                   for h in answer.headers.getlist('Set-Cookie')), 'the restore re-issued its session'
    assert restorer.get(PROTECTED).status_code == 401, "the operator's session survived"
    assert _refused(app, operator), "the operator's session survived the restore"
    assert _refused(app, idle), 'an idle session survived the restore'
    assert _refused(app, busy), 'a session in flight survived the restore'


def test_a_session_the_store_keeps_is_refused_after_a_restore(app, accounts, monkeypatch):
    """Redis entries are not removed by a restore: the stored session alone must not pass."""
    from services.backup.restore import invalidate
    monkeypatch.setattr(invalidate, '_remove_session_files', lambda: 0)
    before = _cookie(_login(app, accounts()))
    with app.app_context():
        invalidate.invalidate_after_restore()
    assert _refused(app, before)
    # A sign-in after the restore is valid, and refused after the next one
    between = _cookie(_login(app, accounts()))
    assert not _refused(app, between)
    with app.app_context():
        invalidate.invalidate_after_restore()
    assert _refused(app, between)


def test_a_failed_restore_closes_no_session(app, accounts, monkeypatch):
    from services.backup_service import BackupService
    monkeypatch.setattr(BackupService, 'restore_backup',
                        lambda self, *a, **k: (_ for _ in ()).throw(ValueError('bad archive')))
    restorer = _login(app, accounts('admin'))
    idle = _cookie(_login(app, accounts()))
    assert _restore(restorer, ROUTES[0]).status_code >= 400
    assert restorer.get(PROTECTED).status_code == 200
    assert not _refused(app, idle)


def test_an_archive_carrying_nothing_closes_no_session(app, accounts, monkeypatch):
    from services.backup_service import BackupService
    monkeypatch.setattr(BackupService, 'restore_backup',
                        lambda self, *a, **k: {'sections_carried': []})
    restorer = _login(app, accounts('admin'))
    for url in ROUTES:
        assert _restore(restorer, url).status_code == 200
    assert restorer.get(PROTECTED).status_code == 200


def test_a_login_the_restore_overtakes_is_refused_after_it(app, accounts, monkeypatch):
    """The password was checked against the rows before the restore; the session the
    login opens after it, on the restored row with the same id, is not accepted."""
    from datetime import timedelta
    from auth import twofa_enforcement
    from auth.session_epoch import advance_epoch
    name = accounts()

    def restore_lands(user):
        row = db.session.get(User, user.id)
        row.role = 'admin'
        row.created_at = row.created_at - timedelta(days=30)
        db.session.commit()
        advance_epoch()
        return []
    monkeypatch.setattr(twofa_enforcement, 'second_factor_methods', restore_lands)
    client = _login(app, name)
    assert client.get(PROTECTED).status_code == 401, 'a login begun before the restore survived it'
    assert client.get('/api/v2/auth/verify').get_json().get('data', {}).get('authenticated') is not True
