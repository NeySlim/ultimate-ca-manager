"""The full-stop mark: read from the migration's source, published with the release, and honoured
at startup. In HA a node refuses to apply a marked migration while another node beats fresh on
another version; outside HA the mark changes nothing."""
import json
import os
import shutil
import subprocess
import sys
import textwrap
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from sqlalchemy import inspect, text

import migration_marks
from config.settings import Config
from tests.upgrade_2254_support import BACKENDS, make_base

ROOT = Path(__file__).resolve().parents[2]
PIVOT = '300_upgrade_from_2_254'
REASON = 'the probe column replaces a column 3.0 still writes'


def _write(path, body):
    path.write_text(textwrap.dedent(body))
    return path


# --- Reading the mark -----------------------------------------------------------------------

def test_the_mark_is_the_literal_reason_at_module_level(tmp_path):
    marked = _write(tmp_path / '301_a.py', f'pg_compatible = True\nrequires_full_stop = "{REASON}"\n')
    plain = _write(tmp_path / '302_b.py', 'pg_compatible = True\n')
    assert migration_marks.full_stop_reason(marked) == REASON
    assert migration_marks.full_stop_reason(plain) is None


@pytest.mark.parametrize('body', [
    'requires_full_stop = ""\n',
    'WHY = "x"\nrequires_full_stop = WHY\n',
    'requires_full_stop = True\n',
    'def upgrade(conn):\n    requires_full_stop = "x"\n',
    'requires_full_stop = "a"\nrequires_full_stop = ""\n',
    'requires_full_stop = "a"\nrequires_full_stop = "b"\n',
    'requires_full_stop, other = "why", 1\n',
    'for requires_full_stop in ["why"]:\n    pass\n',
    'import os as requires_full_stop\n',
])
def test_a_mark_that_cannot_be_read_as_written_is_an_error(tmp_path, body):
    with pytest.raises(ValueError, match='requires_full_stop'):
        migration_marks.full_stop_reason(_write(tmp_path / '301_bad.py', body))


def test_the_manifest_lists_the_marked_migrations_only(tmp_path):
    _write(tmp_path / '301_a.py', f'requires_full_stop = "{REASON}"\n')
    _write(tmp_path / '302_b.py', 'pg_compatible = True\n')
    _write(tmp_path / '_helper.py', 'requires_full_stop = "not a migration"\n')
    out = subprocess.run([sys.executable, str(ROOT / 'backend' / 'migration_marks.py'), str(tmp_path)],
                         capture_output=True, text=True, check=True).stdout
    assert json.loads(out) == {'full_stop': {'301_a': REASON}}


def test_the_upgrade_from_2x_is_marked():
    import migration_runner
    assert migration_marks.full_stop_marks(migration_runner.MIGRATIONS_DIR).keys() >= {PIVOT}


def test_the_release_publishes_the_manifest_its_runner_reads(tmp_path):
    """The step of the release job, run as written, writes the asset the campaign looks for."""
    job = yaml.safe_load((ROOT / '.github' / 'workflows' / 'build-release.yml').read_text())['jobs']['release']
    names = [s.get('name') for s in job['steps']]
    step = next(s for s in job['steps'] if 'migration_marks.py' in str(s.get('run', '')))
    create = next(s for s in job['steps'] if str(s.get('uses', '')).startswith('softprops/action-gh-release'))
    assert names.index(step['name']) < names.index(create['name'])
    assert 'artifacts/*' in create['with']['files']
    (tmp_path / 'artifacts').mkdir()
    os.symlink(ROOT / 'backend', tmp_path / 'backend')
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    subprocess.run(['bash', '-ec', step['run']], cwd=tmp_path, env=env, check=True)
    published = json.loads((tmp_path / 'artifacts' / migration_marks.FULL_STOP_ASSET).read_text())
    import migration_runner
    assert published == migration_marks.manifest(migration_runner.MIGRATIONS_DIR)


def test_the_contributor_rule_names_the_mark_the_runner_reads():
    rule = (ROOT / 'CONTRIBUTING.md').read_text()
    assert f'\n{migration_marks.MARK} = "' in rule


# --- At startup -----------------------------------------------------------------------------

MARKED = f'''
import sqlite3
from sqlalchemy import text
pg_compatible = True
requires_full_stop = "{REASON}"


def upgrade(conn):
    sql = "ALTER TABLE websocket_relay ADD COLUMN probe VARCHAR(8)"
    conn.execute(sql) if isinstance(conn, sqlite3.Connection) else conn.execute(text(sql))
'''
UNMARKED = MARKED.replace(f'requires_full_stop = "{REASON}"\n', '')


@pytest.fixture(params=BACKENDS)
def cluster(request, tmp_path, monkeypatch):
    """A 3.0 database whose cluster_nodes the test fills, and a migrations directory holding 300."""
    import migration_runner
    work = tmp_path / 'migrations'
    work.mkdir()
    shutil.copy(migration_runner.MIGRATIONS_DIR / f'{PIVOT}.py', work)
    monkeypatch.setattr(migration_runner, 'MIGRATIONS_DIR', work)
    for db in make_base(request.param, tmp_path, monkeypatch, 'stop'):
        assert db.upgrade()
        db.work = work
        monkeypatch.setattr(Config, 'HA_MODE', True)
        monkeypatch.setattr(Config, 'NODE_ID', 'node-b')
        monkeypatch.setattr(Config, 'APP_VERSION', '3.1')
        yield db


def _beat(db, node, version, age=5, pid=4242):
    with db.engine.begin() as conn:
        now = (conn.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar()
               if db.dialect == 'postgresql' else None)
    if now is None:
        from utils.datetime_utils import utc_now
        now = utc_now()
    at = now - timedelta(seconds=age)
    with db.engine.begin() as conn:
        conn.execute(text("DELETE FROM cluster_nodes WHERE node_id = :n"), {'n': node})
        conn.execute(text("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, version, pid) "
                          "VALUES (:n, :at, :at, :f, :v, :p)"),
                     {'n': node, 'at': at, 'f': False, 'v': version, 'p': pid})


def _pending(db, body=MARKED, name='301_probe'):
    (db.work / f'{name}.py').write_text(body)
    return name


def _applied(db, name='301_probe'):
    columns = {c['name'] for c in inspect(db.engine).get_columns('websocket_relay')}
    in_registry = name in db.registry()
    assert in_registry == ('probe' in columns)
    return in_registry


def test_a_marked_migration_waits_while_a_node_of_the_old_version_beats(cluster, capsys):
    _beat(cluster, 'node-a', '3.0')
    _pending(cluster)
    assert cluster.upgrade() is False
    out = capsys.readouterr().out
    assert '301_probe requires every node stopped' in out and REASON in out
    assert 'node-a (3.0)' in out and 'Nothing was changed' in out
    assert not _applied(cluster)


@pytest.mark.parametrize('case', ['stale', 'same version', 'own row', 'ha off', 'unmarked'])
def test_a_marked_migration_applies_once_no_other_version_beats(cluster, monkeypatch, case):
    if case == 'stale':
        _beat(cluster, 'node-a', '3.0', age=3600)
    elif case == 'same version':
        _beat(cluster, 'node-a', '3.1-1')
    elif case == 'own row':
        _beat(cluster, 'node-b', '3.0')
    else:
        _beat(cluster, 'node-a', '3.0')
    if case == 'ha off':
        monkeypatch.setattr(Config, 'HA_MODE', False)
    _pending(cluster, UNMARKED if case == 'unmarked' else MARKED)
    assert cluster.upgrade() is True
    assert _applied(cluster)


def test_a_node_stopped_cleanly_lets_the_next_start_apply_at_once(cluster):
    """Stop every node, upgrade one, start it: the others' rows are fresh but say stopped."""
    import migration_runner
    _beat(cluster, 'node-a', '3.0')
    cluster._route()
    migration_runner.mark_node_stopped('node-a')
    assert cluster.run("SELECT pid FROM cluster_nodes WHERE node_id = 'node-a'") == [(None,)]
    _pending(cluster)
    assert cluster.upgrade() is True
    assert _applied(cluster)


_ON_EXIT = r'''
import boot_config
boot_config.wstep_enabled = lambda data_path: False
boot_config.mtls_client_ca = lambda data_path: None
import gunicorn_config
import scheduler_supervisor
from sqlalchemy import create_engine, text

engine = create_engine(__import__('os').environ['DATABASE_URL'])


def stop():
    # The scheduler process writes its last heartbeat while it stops: the mark comes after it
    with engine.begin() as conn:
        conn.execute(text("UPDATE cluster_nodes SET pid = 7 WHERE node_id = 'node-a'"))
scheduler_supervisor.supervisor.stop = stop
gunicorn_config.on_exit(None)
with engine.connect() as conn:
    print(conn.execute(text("SELECT pid FROM cluster_nodes WHERE node_id = 'node-a'")).scalar())
'''


def test_the_gunicorn_master_marks_its_node_stopped_on_exit(tmp_path, monkeypatch):
    backend = str(ROOT / 'backend')
    for db in make_base('sqlite', tmp_path, monkeypatch, 'exit'):
        assert db.upgrade()
        _beat(db, 'node-a', '3.0')
        (tmp_path / 'etc').mkdir()
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(DATA_DIR=str(tmp_path), UCM_BASE_PATH=str(tmp_path), UCM_CONFIG_DIR=str(tmp_path / 'etc'),
                   PYTHONPATH=backend, UCM_HA='1', UCM_NODE_ID='node-a', DATABASE_URL=db.url,
                   DATABASE_PATH=db.sqlite_path)
        run = subprocess.run([sys.executable, '-c', _ON_EXIT], cwd=backend, env=env,
                             capture_output=True, text=True, timeout=60)
        assert run.returncode == 0, run.stderr
        assert run.stdout.strip().splitlines()[-1] == 'None'


class _Time:
    """The monotonic clock and sleep of the wait; while it sleeps, node-a either beats on
    (alive) or ages (killed), and no engine the runner opened may hold a connection."""

    def __init__(self, db, monkeypatch, killed):
        import migration_runner
        self.db, self.killed, self.t, self.engines = db, killed, 0.0, []
        self.locked = False
        made = migration_runner.create_engine

        def record(*a, **k):
            engine = made(*a, **k)
            self.engines.append(engine)
            return engine
        monkeypatch.setattr(migration_runner, 'create_engine', record)

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        assert 0 < seconds <= 15 and not self.locked
        assert all(e.pool.checkedout() == 0 and e.pool.checkedin() == 0 for e in self.engines)
        self.t += seconds
        assert self.t < 600, 'the wait is not bounded'
        _beat(self.db, 'node-a', '3.0', age=5 + self.t if self.killed else 5)


def _waits(out):
    return [line for line in out.splitlines() if line.startswith('Waiting')]


def test_a_killed_node_is_waited_for_then_the_migration_applies(cluster, monkeypatch, capsys):
    import migration_runner
    _beat(cluster, 'node-a', '3.0')
    _pending(cluster)
    cluster._route()
    clock = _Time(cluster, monkeypatch, killed=True)

    @contextmanager
    def lock(url):
        clock.locked = True
        yield
        clock.locked = False
    assert migration_runner.run_at_startup(lock, clock=clock, sleep=clock.sleep) is True
    assert 170 <= clock.t <= 185
    waits = _waits(capsys.readouterr().out)
    assert 11 <= len(waits) <= 13 and all('node-a (3.0)' in w for w in waits)
    assert _applied(cluster)


def test_a_live_node_of_another_version_is_refused_after_the_wait(cluster, monkeypatch, capsys):
    import migration_runner
    from services.scheduler_leader import STALE_PASSES
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    _beat(cluster, 'node-a', '3.0')
    _pending(cluster)
    cluster._route()
    clock = _Time(cluster, monkeypatch, killed=False)
    assert migration_runner.wait_for_full_stop(clock=clock, sleep=clock.sleep) == ['node-a (3.0)']
    stale = STALE_PASSES * WAKE_INTERVAL_SECONDS
    assert stale <= clock.t <= stale + migration_runner.FULL_STOP_MARGIN_SECONDS
    assert all('node-a (3.0)' in w for w in _waits(capsys.readouterr().out))
    assert cluster.upgrade() is False
    assert not _applied(cluster)


def test_nothing_is_waited_for_without_a_holder(cluster, monkeypatch):
    import migration_runner
    _beat(cluster, 'node-a', '3.0', age=3600)
    _pending(cluster)
    cluster._route()
    clock = _Time(cluster, monkeypatch, killed=True)
    assert migration_runner.wait_for_full_stop(clock=clock, sleep=clock.sleep) == []
    assert clock.t == 0


def test_a_mark_that_cannot_be_read_refuses_the_start_in_ha(cluster, capsys):
    _pending(cluster, MARKED.replace(f'requires_full_stop = "{REASON}"', 'requires_full_stop = True'))
    assert cluster.upgrade() is False
    assert 'string literal' in capsys.readouterr().out
    assert not _applied(cluster)


def test_status_tells_why_the_next_start_will_be_refused(cluster, capsys):
    import migration_runner
    _beat(cluster, 'node-a', '3.0')
    _pending(cluster)
    cluster._route()
    migration_runner.show_status()
    out = capsys.readouterr().out
    assert 'Refused: Migration 301_probe requires every node stopped' in out


def test_the_ha_guide_names_the_asset_and_the_delay_the_code_uses():
    from services.scheduler_leader import STALE_PASSES
    from services.scheduler_service import WAKE_INTERVAL_SECONDS
    guide = (ROOT / 'docs' / 'HA.md').read_text()
    upgrading = guide[guide.index('## Upgrading'):]
    assert f'`{migration_marks.FULL_STOP_ASSET}`' in upgrading
    assert STALE_PASSES * WAKE_INTERVAL_SECONDS == 180 and 'three minutes' in upgrading
    assert 'The move from 2.x to 3.0 is a full stop' in upgrading
    import migration_runner
    assert (migration_runner.FULL_STOP_LOG_SECONDS, migration_runner.FULL_STOP_MARGIN_SECONDS) == (15, 15)
    assert 'every 15 seconds' in upgrading and 'three minutes and 15 seconds' in upgrading
