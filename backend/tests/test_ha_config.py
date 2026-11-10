"""UCM_HA configuration: startup validation, node id, restart signal."""
import logging
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from config import settings
from config.settings import Config
from utils import ha

BACKEND = Path(__file__).resolve().parent.parent


@pytest.fixture
def ha_cfg(monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'DATABASE_TYPE', 'postgresql')
    monkeypatch.setenv('SECRET_KEY', 's')
    monkeypatch.setenv('KEY_ENCRYPTION_KEY', 'k')
    monkeypatch.setenv('REDIS_URL', 'redis://x')
    return Config


def test_sqlite_refused_names_database_url(ha_cfg, monkeypatch):
    monkeypatch.setattr(Config, 'DATABASE_TYPE', 'sqlite')
    with pytest.raises(SystemExit, match='DATABASE_URL'):
        ha.validate_ha_config(Config)


def test_missing_secret_key_refused(ha_cfg, monkeypatch):
    monkeypatch.delenv('SECRET_KEY')
    with pytest.raises(SystemExit, match='SECRET_KEY'):
        ha.validate_ha_config(Config)


def test_missing_key_encryption_key_refused(ha_cfg, monkeypatch, tmp_path):
    monkeypatch.delenv('KEY_ENCRYPTION_KEY')
    monkeypatch.setattr('security.encryption.MASTER_KEY_PATH', tmp_path / 'master.key')
    with pytest.raises(SystemExit, match='KEY_ENCRYPTION_KEY'):
        ha.validate_ha_config(Config)


def test_master_key_file_accepted_with_warning(ha_cfg, monkeypatch, tmp_path, caplog):
    monkeypatch.delenv('KEY_ENCRYPTION_KEY')
    mk = tmp_path / 'master.key'
    mk.write_text('x')
    monkeypatch.setattr('security.encryption.MASTER_KEY_PATH', mk)
    with caplog.at_level(logging.WARNING):
        ha.validate_ha_config(Config)
    assert 'master.key identity between nodes is not verified' in caplog.text


def test_valid_ha_config_starts(ha_cfg, caplog):
    with caplog.at_level(logging.WARNING):
        ha.validate_ha_config(Config)
    assert 'sessions' not in caplog.text


def test_ha_without_redis_warns_about_sessions(ha_cfg, monkeypatch, caplog):
    monkeypatch.delenv('REDIS_URL')
    monkeypatch.delenv('UCM_REDIS_URL', raising=False)
    with caplog.at_level(logging.WARNING):
        ha.validate_ha_config(Config)
    assert 'filesystem sessions are not shared' in caplog.text


def test_without_ha_nothing_checked_or_logged(monkeypatch, caplog):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.setattr(Config, 'DATABASE_TYPE', 'sqlite')
    with caplog.at_level(logging.WARNING):
        ha.validate_ha_config(Config)
    assert 'HA' not in caplog.text


def _import_config(env):
    code = "from config.settings import Config; print(Config.HA_MODE, Config.NODE_ID)"
    out = subprocess.run([sys.executable, '-I', '-c', f"import sys; sys.path.insert(0, {str(BACKEND)!r}); {code}"],
                         capture_output=True, text=True, env=env, cwd=str(BACKEND))
    return out.stdout.split()


def test_node_id_defaults_to_hostname_and_ha_flag_parsed():
    import os
    base = {k: v for k, v in os.environ.items() if k not in ('UCM_HA', 'UCM_NODE_ID')}
    assert _import_config(base) == ['False', socket.gethostname()]
    assert _import_config({**base, 'UCM_HA': 'yes', 'UCM_NODE_ID': 'n2'}) == ['True', 'n2']


def test_restart_in_ha_writes_no_signal_file(monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(settings, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(settings, 'is_docker', lambda: False)
    ok, _ = settings.restart_ucm_service()
    assert ok is False
    assert not (tmp_path / '.restart_requested').exists()
    monkeypatch.setattr(Config, 'HA_MODE', False)
    ok, _ = settings.restart_ucm_service()
    assert ok is True and (tmp_path / '.restart_requested').exists()
