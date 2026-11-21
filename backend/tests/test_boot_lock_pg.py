"""HA startup: migrations and schema initialisation run on one node at a time, under a
PostgreSQL session advisory lock; a node that waits too long refuses to start."""
import os
import secrets
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from config.settings import Config
from services import scheduler_leader
from tests import pg_app_harness

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

BACKEND = Path(__file__).resolve().parents[1]
PROBE = textwrap.dedent('''
    """Test-only migration: counts its runs and lasts long enough to overlap another node."""
    from sqlalchemy import text
    pg_compatible = True

    def upgrade(conn):
        conn.execute(text("CREATE TABLE IF NOT EXISTS boot_probe (pid INTEGER)"))
        conn.execute(text("INSERT INTO boot_probe VALUES (pg_backend_pid())"))
        conn.execute(text("SELECT pg_sleep(3)"))
''')
# The child reads neither the host's env file nor its master key, as under conftest
BOOT = textwrap.dedent('''
    import sys
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    import os
    from pathlib import Path
    from security import encryption  # nor the host's master key
    encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
    encryption.key_encryption.reload()
    import migration_runner
    if sys.argv[1]:
        migration_runner.MIGRATIONS_DIR = Path(sys.argv[1])
    from services import scheduler_leader
    scheduler_leader.BOOT_LOCK_KEY = int(sys.argv[2])
    from config import settings
    from utils.db_url import sqlalchemy_url
    import os
    settings.TestingConfig.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['DATABASE_URL'])
    from app import create_app
    create_app('testing')
    print('BOOTED')
''')


@pytest.fixture
def schema():
    name = f'{pg_app_harness.SCHEMA}_boot{secrets.token_hex(2)}'
    pg_app_harness._new_schema(pg_app_harness._marker[0].cursor(), name)
    return name


def _boot(schema, migrations, key, tmp_path, n):
    from cryptography.fernet import Fernet
    data = tmp_path / f'node{n}'
    data.mkdir(exist_ok=True)
    env = dict(os.environ, UCM_HA='1', UCM_NODE_ID=f'boot-{n}', DATA_DIR=str(data),
               DATABASE_PATH=str(data / 'ucm.db'), DATABASE_URL=pg_app_harness.app_url(schema),
               SECRET_KEY='boot-test', KEY_ENCRYPTION_KEY=Fernet.generate_key().decode(),
               UCM_SKIP_SECRET_VALIDATION='1')
    return subprocess.Popen([sys.executable, '-c', BOOT, str(migrations or ''), str(key)],
                            cwd=BACKEND, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)


def _probe_runs(schema):
    engine = create_engine(pg_app_harness.app_url(schema))
    try:
        with engine.connect() as conn:
            runs = conn.execute(text('SELECT count(*) FROM boot_probe')).scalar()
            marked = conn.execute(text("SELECT count(*) FROM _migrations WHERE name = '999_boot_probe'")
                                  ).scalar()
            return runs, marked
    finally:
        engine.dispose()


def test_two_nodes_starting_together_run_a_pending_migration_once(schema, tmp_path):
    key = secrets.randbits(62)
    first = _boot(schema, None, key, tmp_path, 0)  # a fresh database, built once
    out = first.communicate(timeout=180)[0]
    assert first.returncode == 0 and 'BOOTED' in out, out[-3000:]

    migrations = tmp_path / 'migrations'
    migrations.mkdir()
    for f in (BACKEND / 'migrations').glob('*.py'):
        (migrations / f.name).symlink_to(f)
    (migrations / '999_boot_probe.py').write_text(PROBE)
    nodes = [_boot(schema, migrations, key, tmp_path, n) for n in (1, 2)]
    outputs = [p.communicate(timeout=240)[0] for p in nodes]
    for p, out in zip(nodes, outputs):
        assert p.returncode == 0 and 'BOOTED' in out, out[-3000:]
    assert _probe_runs(schema) == (1, 1)
    assert sum('no pending migrations' in out for out in outputs) == 1


def test_a_node_that_waits_past_the_lock_timeout_fails_explicitly(app, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    key = secrets.randbits(62)
    from models import db
    with app.app_context():
        url = db.engine.url
    with scheduler_leader.boot_lock(url, key=key):
        with pytest.raises(scheduler_leader.BootLockTimeout, match='more than 1s'):
            with scheduler_leader.boot_lock(url, timeout=1, key=key):
                pass
    with scheduler_leader.boot_lock(url, timeout=1, key=key):
        pass  # free again once the holder left


def test_without_ha_no_lock_is_taken(monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    with scheduler_leader.boot_lock('postgresql://nowhere.invalid/none', timeout=1):
        pass
