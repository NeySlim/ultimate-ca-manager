"""UPGRADE.md, sessions: the database store of PostgreSQL without Redis never reads the
session files 2.x wrote, so a cookie of 2.x signs nobody in; the account itself stays.

The database store runs here on a SQLite file, as the other SQL-store tests do; which store
PostgreSQL without Redis gets is test_sessions_store.test_configuration_picks_the_store.
"""
import pytest

from tests.header_guard import guarded

PROFILE = '/api/v2/account/profile'


@pytest.fixture(autouse=True)
def _drop_session_table_from_metadata():
    yield
    from models import db
    t = db.metadata.tables.get('flask_sessions')
    if t is not None:
        db.metadata.remove(t)


def _login(client):
    r = client.post('/api/v2/auth/login/password', json={'username': 'admin',
                                                          'password': 'changeme123'})
    assert r.status_code == 200, r.data


def test_a_file_session_of_2x_is_not_taken_up_by_the_database_store(monkeypatch, tmp_path):
    from config.settings import TestingConfig
    from models import db
    from tests import pg_app_harness
    from tests.conftest import clear_admin_password_flag

    if pg_app_harness.ENABLED:
        pytest.skip('file-database fixture, not meaningful in PostgreSQL mode')
    sessions = tmp_path / 'sessions'
    monkeypatch.setattr(TestingConfig, 'SQLALCHEMY_DATABASE_URI', f'sqlite:///{tmp_path / "u.db"}')
    monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'filesystem')
    monkeypatch.setattr(TestingConfig, 'SESSION_FILE_DIR', sessions)
    from app import create_app
    apps = []
    try:
        files = guarded(create_app('testing'))
        apps.append(files)
        clear_admin_password_flag(files)
        client = files.test_client()
        _login(client)
        cookie = client.get_cookie('session').value
        assert any(sessions.iterdir()), 'the file store wrote no session'

        # A restart on the file store (SQLite, as in 2.x) keeps the session
        again = guarded(create_app('testing'))
        apps.append(again)
        same = again.test_client()
        same.set_cookie('session', cookie)
        assert same.get(PROFILE).status_code == 200

        monkeypatch.setattr(TestingConfig, 'SESSION_TYPE', 'sqlalchemy')
        monkeypatch.setattr(TestingConfig, 'SESSION_SQLALCHEMY_TABLE', 'flask_sessions', raising=False)
        database = guarded(create_app('testing'))
        apps.append(database)
        assert database.config['SESSION_TYPE'] == 'sqlalchemy'
        upgraded = database.test_client()
        upgraded.set_cookie('session', cookie)
        assert upgraded.get(PROFILE).status_code == 401
        # Signing in again works: account and password are untouched
        _login(upgraded)
        assert upgraded.get(PROFILE).status_code == 200
    finally:
        for application in apps:
            with application.app_context():
                db.session.remove()
                db.engine.dispose()
