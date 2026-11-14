"""The full-stop mark: read from the migration's source, published with the release, and honoured
at startup. In HA a node refuses to apply a marked migration while another node beats fresh on
another version; outside HA the mark changes nothing."""
import json
import os
import shutil
import subprocess
import sys
import textwrap
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


def _beat(db, node, version, age=5):
    with db.engine.begin() as conn:
        now = (conn.execute(text("SELECT clock_timestamp() AT TIME ZONE 'UTC'")).scalar()
               if db.dialect == 'postgresql' else None)
    if now is None:
        from utils.datetime_utils import utc_now
        now = utc_now()
    at = now - timedelta(seconds=age)
    with db.engine.begin() as conn:
        conn.execute(text("INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, version) "
                          "VALUES (:n, :at, :at, :f, :v)"), {'n': node, 'at': at, 'f': False, 'v': version})


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
