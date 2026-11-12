"""The session secret stored under the DEK: rotation, grace, start-up fallback, DEK rotation.

Every test that may reach the environment-file path neutralises update_env_file and the
restart first; the stored rows are removed and the app's key put back after each test.
"""
import logging
from datetime import timedelta

import pytest

from models import db, SystemConfig
from tests.conftest import UCM_TEST_ENV_FILE

ROTATE = '/api/v2/system/security/rotate-secrets'
STATUS = '/api/v2/system/security/secrets-status'


@pytest.fixture(autouse=True)
def _no_host_side_effects(monkeypatch):
    """The environment-file path and the restart never reach the host."""
    def guarded(path, *a, **k):
        assert str(path) == str(UCM_TEST_ENV_FILE), f'unsandboxed env path {path}'
        return True, 'ok', None
    monkeypatch.setattr('api.v2.system.security.update_env_file', guarded)
    monkeypatch.setattr('utils.service_manager.restart_service', lambda *a, **k: True)


@pytest.fixture
def stored(app):
    """The session key rows, the DEKs, the cluster commands and the audit ledger as they were
    (entries sealed under a test KEK would read as a lost master key at a later start)."""
    from models import AuditLog, ClusterCommand, EncryptionKey
    from security import session_key
    from security.dek_rotation import GRACE_KEY
    ledger = AuditLog.__table__

    def clean():
        with app.app_context():
            db.session.rollback()
            SystemConfig.query.filter(SystemConfig.key.in_(session_key.ALL_KEYS + (GRACE_KEY,))
                                      ).delete(synchronize_session=False)
            EncryptionKey.query.delete()
            ClusterCommand.query.delete()
            db.session.commit()
            session_key.load(app)
    clean()
    with app.app_context():
        saved = [dict(row._mapping) for row in db.session.execute(ledger.select())]
    env = app.config['SECRET_KEY']
    yield session_key
    clean()
    with app.app_context():
        db.session.execute(ledger.delete())
        if saved:
            db.session.execute(ledger.insert(), saved)
        db.session.commit()
    from security.encryption import key_encryption
    key_encryption.reload()
    assert app.config['SECRET_KEY'] == env


def _rows(app):
    from security import session_key
    with app.app_context():
        db.session.expire_all()
        return {r.key: r.value for r in
                SystemConfig.query.filter(SystemConfig.key.in_(session_key.ALL_KEYS))}


def _csrf(app, user_id=1):
    from security.csrf import CSRFProtection
    with app.app_context():
        return CSRFProtection.generate_token(user_id)


def _valid(app, token, user_id=1):
    from security.csrf import CSRFProtection
    with app.app_context():
        return CSRFProtection.validate_token(token, user_id)[0]


def _later(monkeypatch, seconds):
    """Every clock the session key reads, moved ``seconds`` ahead."""
    from security import session_key
    from utils.datetime_utils import utc_now
    later = lambda: utc_now() + timedelta(seconds=seconds)  # noqa: E731
    monkeypatch.setattr(session_key, '_now', later)
    monkeypatch.setattr(session_key, '_local_now', later)


def test_rotation_stores_the_key_encrypted_and_never_shows_it(
        app, auth_client, stored, encryption_enabled, caplog):
    from models import AuditLog
    from security.encryption import decrypt_master_key_value, key_encryption
    env = app.config['SECRET_KEY']
    caplog.set_level(logging.DEBUG)
    r = auth_client.post(ROTATE, json={})
    assert r.status_code == 200, r.data
    new = app.config['SECRET_KEY']
    assert new and new != env
    rows = _rows(app)
    assert key_encryption.is_encrypted(rows[stored.ACTIVE_KEY])
    assert key_encryption.is_encrypted(rows[stored.PREVIOUS_KEY])
    with app.app_context():
        assert decrypt_master_key_value(rows[stored.ACTIVE_KEY], 'text') == new
        assert decrypt_master_key_value(rows[stored.PREVIOUS_KEY], 'text') == env
        audit = AuditLog.query.filter_by(action='secrets_rotated').order_by(
            AuditLog.id.desc()).first()
        assert audit is not None and new not in (audit.details or '')
    assert new not in r.get_data(as_text=True)
    assert new not in caplog.text
    assert r.get_json()['data']['mode'] == 'database'


def test_a_token_of_the_previous_key_is_accepted_during_the_grace_only(
        app, auth_client, stored, encryption_enabled, monkeypatch):
    before = _csrf(app)
    assert auth_client.post(ROTATE, json={}).status_code == 200
    after = _csrf(app)
    assert _valid(app, before) and _valid(app, after)
    _later(monkeypatch, stored.GRACE_SECONDS + 1)
    assert not _valid(app, before)
    assert _valid(app, after)
    assert app.config['SECRET_KEY_FALLBACKS'] == []


def test_a_second_rotation_waits_for_the_end_of_the_grace(
        app, auth_client, stored, encryption_enabled, monkeypatch):
    assert auth_client.post(ROTATE, json={}).status_code == 200
    active = _rows(app)[stored.ACTIVE_KEY]
    r = auth_client.post(ROTATE, json={})
    assert r.status_code == 409, r.data
    assert _rows(app)[stored.ACTIVE_KEY] == active
    _later(monkeypatch, stored.GRACE_SECONDS + 1)
    assert auth_client.post(ROTATE, json={}).status_code == 200


def test_the_retire_task_drops_the_previous_key_once_due(
        app, auth_client, stored, encryption_enabled, monkeypatch):
    assert auth_client.post(ROTATE, json={}).status_code == 200
    with app.app_context():
        assert stored.retire_if_due() is False
    assert stored.PREVIOUS_KEY in _rows(app)
    _later(monkeypatch, stored.GRACE_SECONDS + 1)
    with app.app_context():
        assert stored.retire_if_due() is True
    rows = _rows(app)
    assert stored.PREVIOUS_KEY not in rows and stored.RETIRE_KEY not in rows
    assert stored.ACTIVE_KEY in rows


def test_an_unreadable_row_starts_on_the_environment_key_with_a_warning(
        app, stored, encryption_enabled, caplog):
    import base64
    from cryptography.fernet import Fernet
    from security.encryption import ENCRYPTED_MARKER
    env = app.config['SECRET_KEY']
    foreign = base64.b64encode(ENCRYPTED_MARKER + Fernet(Fernet.generate_key()).encrypt(
        b'k' * 43)).decode()
    with app.app_context():
        db.session.add(SystemConfig(key=stored.ACTIVE_KEY, value=foreign))
        db.session.commit()
        with caplog.at_level(logging.WARNING, logger='security.session_key'):
            stored.load(app)
    assert app.config['SECRET_KEY'] == env
    assert 'does not decrypt' in caplog.text


def test_a_row_in_the_clear_is_never_used(app, stored, encryption_enabled, caplog):
    env = app.config['SECRET_KEY']
    with app.app_context():
        db.session.add(SystemConfig(key=stored.ACTIVE_KEY, value='p' * 43))
        db.session.commit()
        with caplog.at_level(logging.WARNING, logger='security.session_key'):
            stored.load(app)
    assert app.config['SECRET_KEY'] == env
    assert 'not encrypted' in caplog.text


def test_a_dek_rotation_rewrites_the_session_key_and_it_stays_readable(
        app, auth_client, stored, encryption_enabled, dek_refresh_now, dek_retire_at_once):
    from security.encryption import key_encryption
    assert auth_client.post(ROTATE, json={}).status_code == 200
    key = app.config['SECRET_KEY']
    before = _rows(app)
    with app.app_context():
        version = key_encryption.dek_version_of(before[stored.ACTIVE_KEY])
    r = auth_client.post('/api/v2/system/security/rotate-encryption-key')
    assert r.status_code == 200, r.data
    after = _rows(app)
    with app.app_context():
        assert key_encryption.dek_version_of(after[stored.ACTIVE_KEY]) > version
        assert key_encryption.dek_version_of(after[stored.PREVIOUS_KEY]) > version
        stored.load(app)
    assert app.config['SECRET_KEY'] == key


def test_without_encryption_the_environment_file_path_is_unchanged(
        app, auth_client, stored, monkeypatch):
    from security.encryption import key_encryption
    assert not key_encryption.is_encrypting
    seen = []

    def guarded(path, rewrite, *a, **k):
        assert str(path) == str(UCM_TEST_ENV_FILE), f'unsandboxed env path {path}'
        seen.append(rewrite('SECRET_KEY=old\n'))
        return True, 'ok', None
    monkeypatch.setattr('api.v2.system.security.update_env_file', guarded)
    r = auth_client.post(ROTATE, json={'new_secret': 'n' * 40})
    assert r.status_code == 200, r.data
    assert seen == ['SECRET_KEY=' + 'n' * 40 + '\n']
    assert r.get_json()['data']['mode'] == 'environment_file'
    assert _rows(app) == {}


def test_ha_without_encryption_is_refused(app, auth_client, stored, monkeypatch):
    from config.settings import Config
    monkeypatch.setattr(Config, 'HA_MODE', True)
    r = auth_client.post(ROTATE, json={})
    assert r.status_code == 409 and r.get_json()['code'] == 'ha_mode'


def test_ha_with_encryption_rotates_in_the_database(
        app, auth_client, stored, encryption_enabled, monkeypatch):
    from config.settings import Config
    from models import ClusterCommand
    monkeypatch.setattr(Config, 'HA_MODE', True)
    r = auth_client.post(ROTATE, json={})
    assert r.status_code == 200, r.data
    key = app.config['SECRET_KEY']
    with app.app_context():
        commands = ClusterCommand.query.filter_by(kind='reload_secret_key').all()
        assert len(commands) == 1
        assert key not in (commands[0].payload or '')


def test_status_names_where_the_key_comes_from(app, auth_client, stored, encryption_enabled):
    data = auth_client.get(STATUS).get_json()['data']['session_secret']
    assert data['source'] == 'environment' and data['rotation'] == 'database'
    assert auth_client.post(ROTATE, json={}).status_code == 200
    data = auth_client.get(STATUS).get_json()['data']['session_secret']
    assert data['source'] == 'database' and data['previous_accepted_until']


def test_disabling_encryption_drops_the_stored_key(
        app, auth_client, stored, encryption_enabled, dek_refresh_now):
    from security import dek_rotation
    assert auth_client.post(ROTATE, json={}).status_code == 200
    with app.app_context():
        dek_rotation.begin_disable()
    assert _rows(app) == {}
    assert app.config['SECRET_KEY'] == stored.environment_key(app)


def test_the_stored_key_never_travels_in_a_backup():
    from security import session_key
    from services.backup import installation
    assert set(session_key.ALL_KEYS) <= installation.LOCAL_SETTINGS


def test_the_decrypting_sweep_of_a_disable_never_writes_the_key_in_the_clear(
        app, auth_client, stored, encryption_enabled, dek_refresh_now):
    from security import dek_rotation
    from security.encryption import key_encryption
    assert auth_client.post(ROTATE, json={}).status_code == 200
    with app.app_context():
        dek_rotation.rewrite(decrypt=True)
    rows = _rows(app)
    assert key_encryption.is_encrypted(rows[stored.ACTIVE_KEY])
    assert key_encryption.is_encrypted(rows[stored.PREVIOUS_KEY])
