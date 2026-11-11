"""HA cluster commands outside PostgreSQL: nothing runs or is written without UCM_HA,
and the rolling-restart turn only waits for live nodes still on their old process."""
import threading
from datetime import timedelta

import pytest

from config.settings import Config
from services import cluster_commands as cc
from utils.datetime_utils import utc_now


def _rows(app):
    from models import ClusterCommand, db
    with app.app_context():
        db.session.expire_all()
        return ClusterCommand.query.count()


def test_without_ha_no_thread_and_no_row(app, auth_client, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert cc.start_applier(app) is None
    assert not any(t.name == 'ClusterCommandApplier' for t in threading.enumerate())
    with app.app_context():
        assert cc.emit(cc.RELOAD_SYSLOG) is None
    before = _rows(app)
    from security.rate_limiter import RateLimitConfig
    r = auth_client.put('/api/v2/system/security/rate-limit', json={'enabled': RateLimitConfig.is_enabled()})
    assert r.status_code == 200, r.data
    r = auth_client.put('/api/v2/system/audit/syslog', json={'enabled': False, 'host': '', 'port': 514})
    assert r.status_code == 200, r.data
    assert _rows(app) == before == 0


@pytest.mark.parametrize('kind', ['reload_everything',
                                  'invalidate_password_policy',  # read from the database on every check
                                  'reload_encryption'])          # refused in HA until key envelopes
def test_unknown_kind_is_refused(app, kind):
    with app.app_context(), pytest.raises(ValueError):
        cc.emit(kind)


NOW = utc_now()
ISSUED = NOW - timedelta(seconds=10)
OLD = NOW - timedelta(minutes=5)


@pytest.mark.parametrize('nodes, expected', [
    ([('a', OLD, NOW), ('b', OLD, NOW), ('c', OLD, NOW)], ['a', 'b']),
    ([('a', NOW, NOW), ('b', OLD, NOW)], ['b']),                     # a is back
    ([('a', OLD, NOW - timedelta(seconds=200)), ('b', OLD, NOW)], ['b']),  # a went stale
    ([('d', OLD, NOW)], []),                                         # after c: not ahead
    ([], []),                                                        # single node
])
def test_only_live_nodes_ahead_on_their_old_process_are_waited_for(nodes, expected):
    assert cc.pending_predecessors('c', nodes, ISSUED, NOW, stale_seconds=180) == expected


@pytest.fixture
def ha_commands(app, monkeypatch):
    """HA on this backend; yields the kinds of the commands the test emitted, removed afterwards."""
    from models import ClusterCommand, db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.is_docker', lambda: True)
    with app.app_context():
        floor = db.session.query(db.func.max(ClusterCommand.id)).scalar() or 0

    def kinds():
        with app.app_context():
            db.session.expire_all()
            return [c.kind for c in ClusterCommand.query.filter(ClusterCommand.id > floor)
                    .order_by(ClusterCommand.id)]
    yield kinds
    with app.app_context():
        ClusterCommand.query.filter(ClusterCommand.id > floor).delete()
        db.session.commit()


def _config(app, key):
    from models import SystemConfig, db
    with app.app_context():
        db.session.expire_all()
        row = SystemConfig.query.filter_by(key=key).first()
        return row.value if row else None


def _put_config(app, key, value):
    from models import SystemConfig, db
    with app.app_context():
        row = SystemConfig.query.filter_by(key=key).first()
        if row is None and value is not None:
            db.session.add(SystemConfig(key=key, value=value))
        elif row is not None and value is None:
            db.session.delete(row)
        elif row is not None:
            row.value = value
        db.session.commit()


def test_wstep_toggle_in_a_ha_container_queues_the_restart_with_the_setting(app, auth_client, ha_commands):
    old = _config(app, 'wstep_enabled')
    try:
        r = auth_client.patch('/api/v2/wstep/config', json={'enabled': old != 'true'})
        assert r.status_code == 200, r.data
        assert ha_commands() == [cc.RESTART]
        assert 'requires_container_restart' not in (r.get_json().get('data') or {})
    finally:
        _put_config(app, 'wstep_enabled', old)


def test_mtls_change_in_a_ha_container_queues_the_restart_with_the_setting(app, auth_client, ha_commands,
                                                                          monkeypatch):
    monkeypatch.setattr('api.v2.mtls.is_docker', lambda: True)
    r = auth_client.get('/api/v2/mtls/settings')
    current = (r.get_json() or {}).get('data', {}).get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})  # same value: nothing changes
    assert r.status_code == 200, r.data
    assert ha_commands() == [cc.RESTART]


@pytest.fixture
def broken_emit(app, ha_commands, monkeypatch):
    """Every command the routes emit is invalid (NOT NULL kind): their commit fails."""
    from models import ClusterCommand, db

    def emit(kind, payload=None, target=None):
        command = ClusterCommand(kind=None, created_at=utc_now())
        db.session.add(command)
        return command
    monkeypatch.setattr(cc, 'emit', emit)
    return ha_commands


def test_rate_limits_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    from security.rate_limiter import STORED_KEY, RateLimitConfig
    r = auth_client.put('/api/v2/system/security/rate-limit',
                        json={'custom_limits': {'/api/v2/cc-broken': {'rpm': 9, 'burst': 3}}})
    assert r.status_code != 200
    assert '/api/v2/cc-broken' not in RateLimitConfig.get_config()['custom_limits']
    assert _config(app, STORED_KEY) is None and broken_emit() == []


def test_syslog_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    old = _config(app, 'syslog_port')
    r = auth_client.put('/api/v2/system/audit/syslog', json={'enabled': False, 'host': '', 'port': 5599})
    assert r.status_code != 200
    assert _config(app, 'syslog_port') == old and broken_emit() == []


def test_admin_allowlist_not_saved_when_the_command_is_not(app, auth_client, broken_emit):
    old = _config(app, 'admin_allowed_networks')
    r = auth_client.patch('/api/v2/settings/general', json={'admin_allowed_networks': '127.0.0.0/8'})
    assert r.status_code != 200
    assert _config(app, 'admin_allowed_networks') == old and broken_emit() == []


def test_wstep_toggle_not_saved_when_its_restart_is_not(app, auth_client, broken_emit):
    old = _config(app, 'wstep_enabled')
    try:
        r = auth_client.patch('/api/v2/wstep/config', json={'enabled': old != 'true'})
        assert r.status_code != 200, r.data
        assert _config(app, 'wstep_enabled') == old and broken_emit() == []
    finally:
        _put_config(app, 'wstep_enabled', old)


def test_mtls_change_not_saved_when_its_restart_is_not(app, auth_client, broken_emit):
    r = auth_client.get('/api/v2/mtls/settings')
    current = (r.get_json() or {}).get('data', {}).get('required', False)
    r = auth_client.put('/api/v2/mtls/settings', json={'required': current})
    assert r.status_code != 200, r.data
    assert broken_emit() == []


def test_service_restart_route_fails_when_its_command_is_not_queued(auth_client, broken_emit):
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 500 and broken_emit() == []


_BOOT_READS = r'''
import json, sys
import boot_config
from utils.datetime_utils import utc_now
reads = []

def recorder(name, value):
    def read(data_path):
        stamp = getattr(sys.modules.get('services.cluster_commands'), 'PROCESS_STARTED', None)
        reads.append([name, stamp is not None and stamp <= utc_now()])
        return value
    return read
boot_config.wstep_enabled = recorder('wstep', False)
boot_config.mtls_client_ca = recorder('mtls', None)
import gunicorn_config
print(json.dumps(reads))
'''


_BOOT_SNAPSHOT = r'''
import json, sys
import boot_config


class Committed:
    def rows(self, sql, params=()):
        return [(7,)]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False
boot_config.open_boot_database = lambda data_path: Committed()
reads = []

def recorder(name, value):
    def read(data_path):
        known = getattr(sys.modules.get('services.cluster_commands'), 'KNOWN_AT_START', None)
        reads.append([name, sorted(known or [])])
        return value
    return read
boot_config.wstep_enabled = recorder('wstep', False)
boot_config.mtls_client_ca = recorder('mtls', None)
import gunicorn_config
print(json.dumps(reads))
'''


def test_the_master_reads_the_committed_restarts_before_its_settings(tmp_path):
    """HA: a restart committed after this snapshot restarts the node, whatever the first pass sees."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    backend = str(Path(__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(tmp_path), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=backend, UCM_HA='1')
    run = subprocess.run([sys.executable, '-c', _BOOT_SNAPSHOT], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.strip().splitlines()[-1]) == [['wstep', [7]], ['mtls', [7]]]


def test_the_process_start_is_stamped_before_the_master_reads_a_setting(tmp_path):
    """A restart committed after a setting was read is never judged older than the process."""
    import json
    import os
    import subprocess
    import sys
    from pathlib import Path
    backend = str(Path(__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(tmp_path), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=backend)
    run = subprocess.run([sys.executable, '-c', _BOOT_READS], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert json.loads(run.stdout.strip().splitlines()[-1]) == [['wstep', True], ['mtls', True]]


_WORKER_EXIT = r'''
import boot_config
boot_config.wstep_enabled = lambda data_path: False
boot_config.mtls_client_ca = lambda data_path: None
import gunicorn_config
import services.cluster_commands as cc


class Applier:
    stopped = 0

    def stop(self):
        Applier.stopped += 1
        raise RuntimeError('database gone')
cc._applier = Applier()
gunicorn_config.worker_exit(None, None)
cc._applier = None
gunicorn_config.worker_exit(None, None)
print(Applier.stopped)
'''


def test_a_worker_that_exits_stops_its_applier_and_never_raises(tmp_path):
    """The stop is what gives back a restart claim still pending: the next worker can then claim it."""
    import os
    import subprocess
    import sys
    from pathlib import Path
    backend = str(Path(__file__).resolve().parent.parent)
    env = {k: v for k, v in os.environ.items() if k not in ('DATABASE_URL', 'DATABASE_PATH')}
    env.update(DATA_DIR=str(tmp_path), UCM_BASE_PATH=str(tmp_path), PYTHONPATH=backend)
    run = subprocess.run([sys.executable, '-c', _WORKER_EXIT], cwd=backend, env=env,
                         capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    assert run.stdout.strip().splitlines()[-1] == '1'


@pytest.fixture
def master_on_sqlite(monkeypatch, tmp_path):
    """The gunicorn master in HA, on a SQLite file of the test's own."""
    monkeypatch.setenv('UCM_HA', '1')
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('DATABASE_PATH', str(tmp_path / 'ucm.db'))
    monkeypatch.setattr(cc, 'KNOWN_AT_START', None)
    return tmp_path / 'ucm.db'


def test_a_first_ha_start_before_the_migration_spares_nothing_in_silence(master_on_sqlite, tmp_path, capsys):
    """Upgrade: the migrations that create cluster_commands run after this snapshot."""
    import sqlite3
    with sqlite3.connect(master_on_sqlite) as conn:
        conn.execute('CREATE TABLE system_config (key TEXT, value TEXT)')
    assert cc.snapshot_committed_restarts(str(tmp_path)) == frozenset()
    assert capsys.readouterr().err == ''


def test_any_other_snapshot_error_is_still_reported(master_on_sqlite, tmp_path, capsys):
    master_on_sqlite.write_bytes(b'not a database' * 100)
    assert cc.snapshot_committed_restarts(str(tmp_path)) == frozenset()
    assert 'restarts not read before the settings' in capsys.readouterr().err


def test_stop_that_times_out_with_a_give_back_pending_says_so(app, caplog):
    release = threading.Event()
    applier = cc.CommandApplier(app, 'stuck-node')
    applier._give_back_pending = [None, 41, False]
    applier._thread = threading.Thread(target=release.wait, daemon=True)
    applier._thread.start()
    try:
        with caplog.at_level('INFO'):
            applier.stop(timeout=0.05)
    finally:
        release.set()
        applier._thread.join()
    lines = [r for r in caplog.records if r.levelname == 'ERROR' and 'command 41' in r.getMessage()]
    assert len(lines) == 1 and 'possibly not given back' in lines[0].getMessage(), caplog.text
