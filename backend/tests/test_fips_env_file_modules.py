"""ucm.env is read after the -fips entrypoint checked the module: it must not move OPENSSL_MODULES."""
import os

from config import settings


def _env_file(tmp_path, monkeypatch, line):
    (tmp_path / 'ucm.env').write_text(line + '\n')
    monkeypatch.setenv('UCM_CONFIG_DIR', str(tmp_path))


def test_env_file_sets_openssl_modules_when_the_environment_has_none_pos(tmp_path, monkeypatch):
    # what the entrypoint's pin guards against: an unset variable is taken from ucm.env
    monkeypatch.delenv('OPENSSL_MODULES', raising=False)
    _env_file(tmp_path, monkeypatch, 'OPENSSL_MODULES=/elsewhere')
    settings.load_env_files()
    assert os.environ.get('OPENSSL_MODULES') == '/elsewhere'
    monkeypatch.delenv('OPENSSL_MODULES')


def test_env_file_does_not_move_a_pinned_openssl_modules_neg(tmp_path, monkeypatch):
    monkeypatch.setenv('OPENSSL_MODULES', '/usr/lib/ossl-modules')
    _env_file(tmp_path, monkeypatch, 'OPENSSL_MODULES=/elsewhere')
    settings.load_env_files()
    assert os.environ['OPENSSL_MODULES'] == '/usr/lib/ossl-modules'
