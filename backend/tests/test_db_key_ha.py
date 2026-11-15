"""In HA every node shares UCM_DB_ENCRYPTION_KEY: the machine-derived key is never used there."""
import pytest
from cryptography.fernet import Fernet

import utils.encryption as enc
from config.settings import Config
from utils import ha


@pytest.fixture
def machine(monkeypatch, tmp_path):
    """The machine-id fallback pointed at tmp paths, with no explicit key."""
    monkeypatch.delenv('UCM_DB_ENCRYPTION_KEY', raising=False)
    monkeypatch.delenv('UCM_REQUIRE_DB_ENCRYPTION_KEY', raising=False)
    key_path = tmp_path / 'data' / '.machine-key'
    etc_id = tmp_path / 'machine-id'
    etc_id.write_text('')
    monkeypatch.setattr(enc, 'MACHINE_KEY_PATH', str(key_path))
    monkeypatch.setattr(enc, 'MACHINE_ID_PATHS', (str(etc_id), str(key_path)))
    enc.get_cipher.cache_clear()
    yield key_path
    enc.get_cipher.cache_clear()


def test_ha_never_falls_back_to_the_machine_key(machine, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    with pytest.raises(RuntimeError, match='UCM_DB_ENCRYPTION_KEY'):
        enc._get_encryption_key()
    assert not machine.exists()  # no per-node key was created either


def test_outside_ha_the_fallback_stays(machine, monkeypatch, caplog):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert enc._get_encryption_key()
    assert 'UCM_DB_ENCRYPTION_KEY is not set' in caplog.text


@pytest.fixture
def ha_cfg(monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'DATABASE_TYPE', 'postgresql')
    monkeypatch.setenv('SECRET_KEY', 's')
    monkeypatch.setenv('KEY_ENCRYPTION_KEY', 'k')
    monkeypatch.setenv('UCM_DB_ENCRYPTION_KEY', Fernet.generate_key().decode())
    return Config


def test_ha_start_refused_without_the_shared_db_key(ha_cfg, monkeypatch):
    monkeypatch.delenv('UCM_DB_ENCRYPTION_KEY')
    with pytest.raises(SystemExit, match='UCM_DB_ENCRYPTION_KEY'):
        ha.validate_ha_config(Config)


def test_ha_start_refused_with_an_unusable_db_key(ha_cfg, monkeypatch):
    monkeypatch.setenv('UCM_DB_ENCRYPTION_KEY', '0' * 64)  # hex, not a Fernet key
    with pytest.raises(SystemExit, match='UCM_DB_ENCRYPTION_KEY'):
        ha.validate_ha_config(Config)


def test_ha_start_accepts_a_fernet_db_key(ha_cfg):
    ha.validate_ha_config(Config)


def test_decrypt_required_names_the_secret_it_cannot_open(monkeypatch):
    monkeypatch.setenv('UCM_DB_ENCRYPTION_KEY', Fernet.generate_key().decode())
    enc.get_cipher.cache_clear()
    try:
        foreign = Fernet(Fernet.generate_key()).encrypt(b'hunter2').decode()
        with pytest.raises(enc.SecretUnreadable, match='webhook 7 secret') as err:
            enc.decrypt_required(foreign, 'webhook 7 secret')
        assert 'hunter2' not in str(err.value) and foreign not in str(err.value)
        assert enc.decrypt_required(enc.encrypt_value('ok'), 'x') == 'ok'
        assert enc.decrypt_required('legacy-plain', 'x') == 'legacy-plain'
        assert enc.decrypt_required(None, 'x') is None
    finally:
        enc.get_cipher.cache_clear()
