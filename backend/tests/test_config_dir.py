"""UCM_CONFIG_DIR moves ucm.env and master.key: a fresh process given it reads,
writes and opens nothing under the installation's own configuration directory."""
import os
import subprocess
import sys
import textwrap
from pathlib import Path

from cryptography.fernet import Fernet

BACKEND = Path(__file__).resolve().parent.parent

# Runs in the child: any filesystem event naming a host path aborts the process.
CHILD = textwrap.dedent('''
    import os, sys
    FORBIDDEN = ('/etc/ucm', '/opt/ucm', '/var/lib/softhsm', '/var/log/ucm')
    PATH_EVENTS = {'open', 'os.chmod', 'os.chown', 'os.mkdir', 'os.rename', 'os.remove',
                   'os.link', 'os.symlink', 'os.listdir', 'os.scandir', 'os.truncate', 'os.utime'}

    def guard(event, args):
        if event in PATH_EVENTS and args and isinstance(args[0], (str, bytes, os.PathLike)):
            path = os.fsdecode(os.fspath(args[0]))
            if path.startswith(FORBIDDEN):
                os.write(2, f'FORBIDDEN {event} {path}\\n'.encode())
                os._exit(97)

    sys.addaudithook(guard)

    from config.settings import Config
    from security.encryption import KeyEncryption, MASTER_KEY_PATH
    from services.database_admin.persistence import env_file_path

    enc = KeyEncryption()
    print('node', Config.NODE_ID)
    print('source', enc.key_source)
    print('key_path', MASTER_KEY_PATH)
    print('env_path', env_file_path())
    print('roundtrip', enc.decrypt_string(enc.encrypt_string('payload')) == 'payload')
''')


def _run(tmp_path, extra=None):
    config_dir = tmp_path / 'config'
    data_dir = tmp_path / 'data'
    data_dir.mkdir(exist_ok=True)
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(tmp_path),
        'PYTHONPATH': str(BACKEND),
        'PYTHONDONTWRITEBYTECODE': '1',
        'UCM_CONFIG_DIR': str(config_dir),
        'DATA_DIR': str(data_dir),
        'DATABASE_PATH': str(data_dir / 'ucm.db'),
        'LC_ALL': 'C',
    }
    env.update(extra or {})
    return subprocess.run([sys.executable, '-c', CHILD], cwd=tmp_path, env=env,
                          capture_output=True, text=True, timeout=120)


def _values(out):
    return dict(line.split(' ', 1) for line in out.splitlines() if ' ' in line)


def test_env_file_and_master_key_come_from_the_config_dir(tmp_path):
    config_dir = tmp_path / 'config'
    config_dir.mkdir()
    (config_dir / 'ucm.env').write_text('UCM_NODE_ID=from-config-dir\nSECRET_KEY=s3cret\n')
    key = config_dir / 'master.key'
    key.write_text(Fernet.generate_key().decode() + '\n')
    key.chmod(0o600)

    result = _run(tmp_path)

    assert result.returncode == 0, result.stderr[-3000:]
    values = _values(result.stdout)
    assert values['node'] == 'from-config-dir'
    assert values['source'] == 'file'
    assert values['key_path'] == str(key)
    assert values['env_path'] == str(config_dir / 'ucm.env')
    assert values['roundtrip'] == 'True'


def test_without_a_key_file_the_environment_key_is_used(tmp_path):
    result = _run(tmp_path, {'KEY_ENCRYPTION_KEY': Fernet.generate_key().decode()})

    assert result.returncode == 0, result.stderr[-3000:]
    values = _values(result.stdout)
    assert values['source'] == 'env'
    assert values['key_path'] == str(tmp_path / 'config' / 'master.key')


def test_key_file_is_written_in_the_config_dir(tmp_path):
    script = CHILD.split('from config.settings')[0] + textwrap.dedent('''
        from cryptography.fernet import Fernet
        from security.encryption import KeyEncryption
        KeyEncryption.write_key_file(Fernet.generate_key().decode(), exclusive=True)
    ''')
    config_dir = tmp_path / 'config'
    env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'HOME': str(tmp_path),
           'PYTHONPATH': str(BACKEND), 'PYTHONDONTWRITEBYTECODE': '1',
           'UCM_CONFIG_DIR': str(config_dir), 'DATA_DIR': str(tmp_path), 'LC_ALL': 'C'}
    result = subprocess.run([sys.executable, '-c', script], cwd=tmp_path, env=env,
                            capture_output=True, text=True, timeout=120)

    assert result.returncode == 0, result.stderr[-3000:]
    assert (config_dir / 'master.key').stat().st_mode & 0o777 == 0o600


def test_default_config_dir_is_unchanged(monkeypatch):
    from config import paths

    monkeypatch.delenv('UCM_CONFIG_DIR', raising=False)
    assert paths.config_dir() == Path('/etc/ucm')
    assert paths.env_file() == Path('/etc/ucm/ucm.env')
    assert paths.master_key_file() == Path('/etc/ucm/master.key')
    monkeypatch.setenv('UCM_CONFIG_DIR', '')
    assert paths.config_dir() == Path('/etc/ucm')
