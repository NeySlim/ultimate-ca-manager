"""FIPS preflight from the API and the command line, and the scheduled
backups' KDF setting the preflight's remedy points to."""
import json
import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

import fips_mode
from config.settings import Config
from models import SystemConfig, User, db
from scripts import fips_preflight as cli
from services.backup import container
from services.database_admin.helpers import _force_register_all_models
from services.database_admin.migration import _create_target_schema
from utils.db_url import sqlalchemy_url

SCRYPT_HASH = 'scrypt:32768:8:1$abcdefgh$' + 'ab' * 64
ROUTE = '/api/v2/system/fips-preflight'
_READ_ONLY_APP = cli.read_only_app


def _set(key, value):
    row = SystemConfig.query.filter_by(key=key).first()
    if row:
        row.value = value
    else:
        db.session.add(SystemConfig(key=key, value=value))
    db.session.commit()


def _delete(key):
    SystemConfig.query.filter_by(key=key).delete()
    db.session.commit()


@pytest.fixture
def scrypt_user(app):
    with app.app_context():
        user = User(username='preflight-scrypt', email='ps@example.com', password_hash=SCRYPT_HASH)
        db.session.add(user)
        db.session.commit()
        user_id = user.id
    yield user_id
    with app.app_context():
        User.query.filter_by(id=user_id).delete()
        db.session.commit()


class TestRoute:
    def test_reports_what_fips_mode_refuses_and_changes_nothing(self, app, auth_client, scrypt_user):
        response = auth_client.get(ROUTE)
        assert response.status_code == 200
        report = response.get_json()['data']
        assert {'fips_active', 'ready', 'summary', 'findings', 'errors', 'checked'} <= set(report)
        finding = next(f for f in report['findings'] if f['id'] == 'users.password_scrypt')
        assert any('preflight-scrypt' in e for e in finding['examples'])
        assert report['ready'] is False
        with app.app_context():
            assert db.session.get(User, scrypt_user).password_hash == SCRYPT_HASH

    def test_needs_admin_system(self, viewer_client):
        assert viewer_client.get(ROUTE).status_code == 403


@pytest.fixture
def instance_db(tmp_path):
    """A SQLite installation of its own, and a configuration that points at it."""
    path = tmp_path / 'ucm.db'
    _force_register_all_models()
    engine = create_engine(f'sqlite:///{path}')
    _create_target_schema(engine, False)

    class InstanceConfig:
        SQLALCHEMY_DATABASE_URI = f'sqlite:///{path}'
        SQLALCHEMY_TRACK_MODIFICATIONS = False
        HTTPS_CERT_PATH = None

    yield engine, InstanceConfig
    engine.dispose()


class TestCommandLine:
    def _run(self, monkeypatch, capsys, config, *args):
        monkeypatch.setattr(cli, 'read_only_app', lambda: _READ_ONLY_APP(config))
        code = cli.main(list(args))
        return code, capsys.readouterr().out

    def test_blockers_exit_1_in_text_and_json(self, instance_db, monkeypatch, capsys):
        engine, config = instance_db
        with engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (username, email, password_hash, role, auth_source) "
                "VALUES ('cli-scrypt', 'c@example.com', :h, 'viewer', 'local')"), {'h': SCRYPT_HASH})
        code, out = self._run(monkeypatch, capsys, config, '--json')
        assert code == 1
        report = json.loads(out)
        assert [f['id'] for f in report['findings'] if f['severity'] == 'blocker'] == \
            ['users.password_scrypt']
        code, out = self._run(monkeypatch, capsys, config)
        assert code == 1
        assert '[BLOCKER] users.password_scrypt (1)' in out
        assert '- cli-scrypt (#1)' in out
        assert 'Remedy: ' in out

    def test_nothing_blocking_exits_0(self, instance_db, monkeypatch, capsys):
        _engine, config = instance_db
        code, out = self._run(monkeypatch, capsys, config)
        assert code == 0
        assert '0 blocker(s)' in out

    def test_a_check_that_cannot_run_exits_2(self, instance_db, monkeypatch, capsys):
        engine, config = instance_db
        with engine.begin() as connection:
            connection.execute(text('DROP TABLE users'))
        code, out = self._run(monkeypatch, capsys, config)
        assert code == 2
        assert '[ERROR] users.password_scrypt' in out

    def test_the_database_is_opened_read_only(self, instance_db):
        _engine, config = instance_db
        app = cli.read_only_app(config)
        with app.app_context():
            with pytest.raises(OperationalError, match='readonly'):
                db.session.execute(text("DELETE FROM users"))
                db.session.commit()
            db.session.rollback()


@pytest.mark.postgres
@pytest.mark.skipif(not os.getenv('UCM_TEST_PG_URL'), reason='UCM_TEST_PG_URL not set')
def test_the_postgresql_connection_is_read_only():
    class PgConfig:
        SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['UCM_TEST_PG_URL'])
        SQLALCHEMY_TRACK_MODIFICATIONS = False

    app = _READ_ONLY_APP(PgConfig)
    with app.app_context():
        try:
            assert db.session.execute(
                text("SELECT current_setting('transaction_read_only')")).scalar() == 'on'
        finally:
            db.session.rollback()
            db.engine.dispose()


class TestScheduledBackupKdf:
    def test_the_schedule_route_stores_and_reports_it(self, app, auth_client):
        try:
            response = auth_client.patch('/api/v2/settings/backup/schedule', json={'kdf': 'pbkdf2'})
            assert response.status_code == 200
            assert response.get_json()['data']['kdf'] == 'pbkdf2'
            assert auth_client.patch('/api/v2/settings/backup/schedule',
                                     json={'kdf': 'md5'}).status_code == 400
        finally:
            with app.app_context():
                _delete('backup_kdf')

    def test_general_settings_store_and_report_it(self, app, auth_client):
        try:
            assert auth_client.patch('/api/v2/settings/general',
                                     json={'backup_kdf': 'pbkdf2'}).status_code == 200
            assert auth_client.get('/api/v2/settings/general').get_json()['data']['backup_kdf'] == 'pbkdf2'
            assert auth_client.patch('/api/v2/settings/general',
                                     json={'backup_kdf': 'scrypt'}).status_code == 400
        finally:
            with app.app_context():
                _delete('backup_kdf')

    def test_fips_mode_refuses_argon2id(self, app, auth_client, monkeypatch):
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        response = auth_client.patch('/api/v2/settings/backup/schedule', json={'kdf': 'argon2id'})
        assert response.status_code == 400
        with app.app_context():
            assert SystemConfig.query.filter_by(key='backup_kdf').first() is None

    def test_an_unchanged_kdf_does_not_block_a_save_in_fips_mode(self, app, auth_client, monkeypatch):
        with app.app_context():
            _set('backup_kdf', 'argon2id')
        monkeypatch.setattr(fips_mode, 'enabled', lambda: True)
        try:
            site_name = auth_client.get('/api/v2/settings/general').get_json()['data']['site_name']
            assert auth_client.patch('/api/v2/settings/general', json={
                'site_name': site_name, 'backup_kdf': 'argon2id'}).status_code == 200
            with app.app_context():
                _set('backup_kdf', 'pbkdf2')
            assert auth_client.patch('/api/v2/settings/general', json={
                'site_name': site_name, 'backup_kdf': 'argon2id'}).status_code == 400
        finally:
            with app.app_context():
                _delete('backup_kdf')

    @pytest.mark.parametrize('kdf, expected', [('pbkdf2', container.KDF_PBKDF2),
                                               ('argon2id', container.KDF_ARGON2ID)])
    def test_the_scheduled_run_writes_with_it(self, app, tmp_path, monkeypatch, kdf, expected):
        from services.backup import schedule
        from utils.encryption import encrypt_if_needed
        monkeypatch.setattr(Config, 'BACKUP_DIR', tmp_path, raising=False)
        monkeypatch.setattr(schedule, '_LAST_ATTEMPT', {'at': None})
        with app.app_context():
            try:
                _set('auto_backup_enabled', 'true')
                _set('backup_password', encrypt_if_needed('a scheduled backup password'))
                _set('backup_kdf', kdf)
                _delete('backup.last_run')
                result = schedule.run_scheduled_backup()
                assert result['status'] == 'ok'
                assert (tmp_path / result['filename']).read_bytes()[6] == expected
            finally:
                for key in ('auto_backup_enabled', 'backup_password', 'backup_kdf', 'backup.last_run'):
                    _delete(key)
