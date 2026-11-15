"""A private Redis server for the tests: its own process on a Unix socket, no TCP port.

`redis-server` runs with `--port 0`, no persistence, in a directory of the test run;
it is stopped by its PID. Tests that need it are marked with `needs_redis`
(tests/optional_backends.py): skipped without the binary, failed under UCM_TEST_REQUIRE_REDIS=1.
"""
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from tests.optional_backends import needs

REDIS_SERVER = shutil.which('redis-server')
needs_redis = needs('redis', REDIS_SERVER, 'redis-server not installed')

# AF_UNIX paths are limited to about 107 bytes
_MAX_SOCKET_PATH = 100


class RedisServer:
    def __init__(self, directory: Path):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        if len(str(directory / 'redis.sock')) > _MAX_SOCKET_PATH:
            directory = Path(tempfile.mkdtemp(prefix='ucm-redis-'))
            self._own_dir = directory
        else:
            self._own_dir = None
        self.dir = directory
        self.socket = directory / 'redis.sock'
        self.proc = None

    def url(self, db=0) -> str:
        return f'unix://{self.socket}?db={db}'

    def client(self, db=0):
        import redis
        return redis.Redis(unix_socket_path=str(self.socket), db=db, socket_timeout=5)

    def start(self):
        assert REDIS_SERVER, 'redis-server not installed'
        self.socket.unlink(missing_ok=True)
        self.proc = subprocess.Popen(
            [REDIS_SERVER, '--port', '0', '--unixsocket', str(self.socket), '--unixsocketperm', '700',
             '--save', '', '--appendonly', 'no', '--dir', str(self.dir), '--daemonize', 'no',
             '--loglevel', 'warning', '--logfile', str(self.dir / 'redis.log')],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(f'redis-server exited: {self.log()}')
            try:
                if self.socket.exists() and self.client().ping():
                    return self
            except Exception:  # noqa: BLE001  # not accepting yet
                pass
            time.sleep(0.05)
        self.stop()
        raise RuntimeError(f'redis-server did not start: {self.log()}')

    def stop(self):
        proc, self.proc = self.proc, None
        if proc is None:
            return
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(10)
        self.socket.unlink(missing_ok=True)

    def close(self):
        self.stop()
        if self._own_dir is not None:
            shutil.rmtree(self._own_dir, ignore_errors=True)

    def log(self) -> str:
        try:
            return (self.dir / 'redis.log').read_text()[-2000:]
        except OSError:
            return ''


BACKEND = Path(__file__).resolve().parent.parent
GUARD_DIR = BACKEND / 'tests' / 'ha' / 'guard'


def sandbox_env(root: Path, **extra) -> dict:
    """The environment of a UCM process started by a test: nothing inherited but PATH,
    every path under ``root``, and the HA bench guard that kills it on an installation path."""
    from cryptography.fernet import Fernet
    root = Path(root)
    for sub in ('data', 'config', 'logs', 'tmp'):
        (root / sub).mkdir(parents=True, exist_ok=True)
    env = {
        'PATH': os.environ.get('PATH', '/usr/bin:/bin'),
        'HOME': str(root),
        'TMPDIR': str(root / 'tmp'),
        'LC_ALL': 'C.UTF-8',
        'PYTHONPATH': os.pathsep.join([str(GUARD_DIR), str(BACKEND)]),
        'PYTHONDONTWRITEBYTECODE': '1',
        'UCM_HA_GUARD_FILE': str(root / 'guard.log'),
        'UCM_CONFIG_DIR': str(root / 'config'),
        'UCM_BASE_PATH': str(root),
        'DATA_DIR': str(root / 'data'),
        'DATABASE_PATH': str(root / 'data' / 'ucm.db'),
        'UCM_LOG_FILE': str(root / 'logs' / 'ucm.log'),
        'UCM_LOG_DIR': str(root / 'logs'),
        'UCM_DB_ENCRYPTION_KEY': Fernet.generate_key().decode('ascii'),
        'SECRET_KEY': 'redis-test-secret-key',
        'UCM_ENV': 'test',
        'UCM_DEV_MODE': 'true',
        'HTTP_REDIRECT': 'false',
        'CSRF_DISABLED': 'true',
        'INITIAL_ADMIN_PASSWORD': 'changeme123',
        'FQDN': 'ucm.test',
    }
    env.update({k: str(v) for k, v in extra.items()})
    return env


def guard_hits(root: Path) -> str:
    try:
        return (Path(root) / 'guard.log').read_text()
    except OSError:
        return ''
