"""HA rolling update: one node at a time, the next only once the previous one is back on the
target version; a node that does not come back stops the campaign. No test installs anything:
the download and the local install are witnesses."""
import json
import os
from datetime import datetime, timedelta

import pytest

import services.update_campaign as uc
import services.updates as updates
from config.settings import Config

T0 = datetime(2026, 11, 12, 3, 0, 0)
STALE = 180
GUARD = 900
SHA = 'ab' * 32


DEB = {'download_url': 'https://x/p.deb', 'package_name': 'p.deb', 'sha256': SHA}
MANIFEST = {'name': 'full-stop-migrations.json', 'browser_download_url': 'https://x/full-stop-migrations.json'}
ASSETS = [{'name': 'p.deb', 'browser_download_url': 'https://x/p.deb'},
          {'name': 'p.deb.sha256', 'browser_download_url': 'https://x/p.deb.sha256'}, MANIFEST]


def _node(started_ago, beat_ago, version, now=T0, family='deb'):
    return uc.NodeView(now - timedelta(seconds=started_ago), now - timedelta(seconds=beat_ago), version,
                       family)


def _campaign(**kw):
    c = {'id': 'c1', 'status': uc.RUNNING, 'target': '3.1', 'packages': {'deb': dict(DEB)},
         'families': {}, 'initiated_by': 'admin',
         'started_at': T0.isoformat(), 'finished_at': None, 'order': ['a', 'b', 'c'],
         'skipped': [], 'done': [], 'current': None, 'failed': None}
    c.update(kw)
    return c


def _plan(campaign, nodes, now=T0):
    return uc.plan_step(campaign, nodes, now, stale_seconds=STALE, guard=GUARD)


# ------------------------------------------------------------------ ordering, pure


def test_the_first_node_in_order_is_dispatched_alone():
    nodes = {n: _node(600, 10, '3.0') for n in 'abc'}
    new, event = _plan(_campaign(), nodes)
    assert event == ('dispatch', 'a', None)
    assert new['current'] == {'node': 'a', 'since': T0.isoformat(), 'state': uc.DISPATCHED}
    assert new['done'] == []


def test_nothing_moves_while_the_node_in_progress_is_not_back():
    since = T0 - timedelta(seconds=60)
    c = _campaign(current={'node': 'a', 'since': since.isoformat(), 'state': uc.INSTALLING})
    nodes = {n: _node(600, 10, '3.0') for n in 'abc'}
    assert _plan(c, nodes) == (None, None)


def test_the_next_node_starts_only_once_the_previous_one_beats_on_the_target():
    since = T0 - timedelta(seconds=120)
    c = _campaign(current={'node': 'a', 'since': since.isoformat(), 'state': uc.INSTALLING})
    nodes = {'a': _node(30, 5, '3.1'), 'b': _node(600, 10, '3.0'), 'c': _node(600, 10, '3.0')}
    new, event = _plan(c, nodes)
    assert event == ('node_done', 'a', None)
    assert new['done'] == ['a'] and new['current'] is None
    new, event = _plan(new, nodes)
    assert event == ('dispatch', 'b', None)


def test_a_node_on_the_target_but_with_a_stale_heartbeat_is_not_back():
    since = T0 - timedelta(seconds=120)
    c = _campaign(current={'node': 'a', 'since': since.isoformat(), 'state': uc.INSTALLING})
    nodes = {'a': _node(30, STALE + 5, '3.1'), 'b': _node(600, 10, '3.0'), 'c': _node(600, 10, '3.0')}
    assert _plan(c, nodes) == (None, None)


def test_a_node_that_does_not_come_back_stops_the_campaign_after_the_guard():
    since = T0 - timedelta(seconds=GUARD + 1)
    c = _campaign(current={'node': 'a', 'since': since.isoformat(), 'state': uc.INSTALLING})
    nodes = {'a': _node(3600, STALE + 600, '3.0'), 'b': _node(600, 10, '3.0'), 'c': _node(600, 10, '3.0')}
    new, event = _plan(c, nodes)
    assert event[0] == 'stopped' and event[1] == 'a'
    assert new['status'] == uc.STOPPED
    assert new['failed']['node'] == 'a' and 'not back' in new['failed']['reason']
    assert new['done'] == [] and new['current'] is None
    # Stopped: the rest of the cluster is not updated behind it
    assert _plan(new, nodes) == (None, None)


def test_a_node_back_on_the_old_version_stops_the_campaign_at_once():
    since = T0 - timedelta(seconds=120)
    c = _campaign(current={'node': 'a', 'since': since.isoformat(), 'state': uc.INSTALLING})
    nodes = {'a': _node(30, 5, '3.0'), 'b': _node(600, 10, '3.0'), 'c': _node(600, 10, '3.0')}
    new, event = _plan(c, nodes)
    assert event[0] == 'stopped' and event[1] == 'a'
    assert '3.0' in new['failed']['reason']


def test_the_next_node_without_a_fresh_heartbeat_stops_the_campaign():
    c = _campaign(done=['a'])
    nodes = {'a': _node(30, 5, '3.1'), 'b': _node(3600, STALE + 1, '3.0'), 'c': _node(600, 10, '3.0')}
    new, event = _plan(c, nodes)
    assert event[0] == 'stopped' and event[1] == 'b'


def test_a_node_already_on_the_target_is_counted_done_without_an_install():
    c = _campaign(done=['a'])
    nodes = {'a': _node(30, 5, '3.1'), 'b': _node(30, 5, '3.1~1'),
             'c': _node(600, 10, '3.0')}
    new, event = _plan(c, nodes)
    assert event == ('node_done', 'b', None)


def test_the_campaign_ends_once_every_node_is_done():
    c = _campaign(done=['a', 'b', 'c'])
    new, event = _plan(c, {})
    assert event == ('finished', None, None)
    assert new['status'] == uc.DONE and new['finished_at'] == T0.isoformat()


# ------------------------------------------------------------------ against the database


PREFIX = 'uc-test-'


def _clean(app):
    from models import ClusterCommand, ClusterNode, SystemConfig, db
    with app.app_context():
        SystemConfig.query.filter_by(key=uc.CAMPAIGN_KEY).delete()
        ClusterNode.query.delete()
        ClusterCommand.query.filter(ClusterCommand.kind == 'update').delete()
        db.session.commit()


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', PREFIX + 'a')
    monkeypatch.setattr(updates, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(updates, 'package_family', lambda: 'deb')
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHA)
    monkeypatch.setattr(updates, 'fetch_full_stop_marks', lambda url: dict(FULL_STOP))
    FULL_STOP.clear()
    _clean(app)
    yield
    _clean(app)


# What the release's full-stop manifest names, per test
FULL_STOP = {}


def _rows(app, **versions):
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    now = utc_now()
    with app.app_context():
        for name, version in versions.items():
            db.session.add(ClusterNode(node_id=PREFIX + name, started_at=now - timedelta(minutes=10),
                                       heartbeat_at=now, is_leader=False, pid=1, version=version,
                                       package_family='deb'))
        db.session.commit()


def _back(app, name, version):
    from models import ClusterNode, db
    from utils.datetime_utils import utc_now
    with app.app_context():
        node = db.session.get(ClusterNode, PREFIX + name)
        node.started_at = node.heartbeat_at = utc_now() + timedelta(seconds=1)
        node.version = version
        db.session.commit()


def _commands(app):
    from models import ClusterCommand
    with app.app_context():
        return [(c.node_id, json.loads(c.payload)) for c in
                ClusterCommand.query.filter_by(kind='update').order_by(ClusterCommand.id).all()]


def _state(app):
    with app.app_context():
        return uc.read_campaign()[1]


def _start(app, assets=ASSETS):
    with app.app_context():
        return uc.start_campaign('3.1', assets, 'admin')


def test_a_campaign_without_a_checksum_is_refused(app, ha):
    _rows(app, a='3.0', b='3.0')
    ok, message, _ = _start(app, assets=ASSETS[:1])
    assert not ok and 'SHA-256' in message
    assert _state(app) is None


def test_a_release_whose_pending_migration_needs_a_full_stop_is_refused_before_any_install(
        app, ha, no_install):
    _rows(app, a='3.0', b='3.0')
    FULL_STOP['399_drop_relay_payload'] = 'the relay payload moved to Redis'
    ok, message, _ = _start(app)
    assert not ok
    assert '399_drop_relay_payload' in message and 'the relay payload moved to Redis' in message
    assert 'every node stopped' in message and 'Nothing was installed' in message
    assert _state(app) is None and _commands(app) == []


@pytest.fixture
def registry(app):
    """The app database's own _migrations (the in-memory test database has none): names added."""
    from sqlalchemy import inspect, text
    from models import db
    names = []
    with app.app_context():
        created = not inspect(db.engine).has_table('_migrations')
        db.session.execute(text("CREATE TABLE IF NOT EXISTS _migrations (id INTEGER PRIMARY KEY, "
                                "name VARCHAR(255) NOT NULL UNIQUE)"))
        db.session.commit()
    yield names.append
    with app.app_context():
        for name in names:
            db.session.execute(text("DELETE FROM _migrations WHERE name = :n"), {'n': name})
        if created:
            db.session.execute(text("DROP TABLE _migrations"))
        db.session.commit()


def test_a_marked_migration_already_applied_lets_the_campaign_start(app, ha, registry):
    from sqlalchemy import text
    from models import db
    with app.app_context():
        db.session.execute(text("INSERT INTO _migrations (name) VALUES ('399_applied_here')"))
        db.session.commit()
    registry('399_applied_here')
    _rows(app, a='3.0', b='3.0')
    FULL_STOP['399_applied_here'] = 'applied by the first node of an earlier full stop'
    ok, message, _ = _start(app)
    assert ok, message


def test_a_release_without_the_manifest_is_refused(app, ha):
    _rows(app, a='3.0', b='3.0')
    ok, message, _ = _start(app, assets=ASSETS[:2])
    assert not ok and 'full-stop-migrations.json' in message
    assert _state(app) is None


def test_a_manifest_that_cannot_be_read_is_refused(app, ha, monkeypatch):
    def broken(url):
        raise ValueError('not JSON')
    monkeypatch.setattr(updates, 'fetch_full_stop_marks', broken)
    _rows(app, a='3.0', b='3.0')
    ok, message, _ = _start(app)
    assert not ok and 'full-stop-migrations.json' in message and 'not JSON' in message
    assert _state(app) is None


def test_the_install_route_says_why_a_full_stop_is_needed(app, auth_client, ha, monkeypatch, no_install):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **k: _release())
    _rows(app, a='3.0', b='3.0')
    FULL_STOP['399_drop_relay_payload'] = 'the relay payload moved to Redis'
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 409, r.data
    assert '399_drop_relay_payload' in r.get_json()['detail']
    assert _state(app) is None and _commands(app) == []


def test_a_second_campaign_while_one_runs_is_refused(app, ha):
    _rows(app, a='3.0', b='3.0')
    assert _start(app)[0]
    ok, message, _ = _start(app)
    assert not ok and 'already running' in message


def test_two_campaigns_from_the_same_read_start_once(app, ha, monkeypatch):
    """Both callers read no campaign; the compare-and-set lets one store its own."""
    _rows(app, a='3.0', b='3.0')
    real = uc.read_campaign
    monkeypatch.setattr(uc, 'read_campaign', lambda: (None, None))
    first = _start(app)
    second = _start(app)
    monkeypatch.setattr(uc, 'read_campaign', real)
    assert [first[0], second[0]] == [True, False]
    assert _state(app)['id'] == first[2]['id']


def test_the_tick_sends_one_update_command_to_the_first_node_only(app, ha):
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        assert uc.campaign_tick()[0] == 'dispatch'
        assert uc.campaign_tick() is None  # a waits for its install: nothing more
    commands = _commands(app)
    assert commands == [(PREFIX + 'a', {'campaign': _state(app)['id'], 'version': '3.1',
                                        'packages': {'deb': DEB}})]


def _witnesses(monkeypatch, calls, fail=None):
    def download(url, name, expected_sha256=None):
        calls.append(('download', expected_sha256))
        if fail:
            raise Exception(fail)
        return '/nowhere/p.deb'
    monkeypatch.setattr(updates, 'download_update', download)
    monkeypatch.setattr(updates, 'install_update',
                        lambda path, **kw: calls.append(('install', path, kw['to_version'])))


def test_the_dispatched_node_downloads_verified_then_asks_its_local_install_once(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
    payload = _commands(app)[0][1]
    with app.app_context():
        uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0')
        uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0')  # replayed: nothing
        uc.run_local_turn(payload, node_id=PREFIX + 'b', version='3.0')  # not its turn
    assert calls == [('download', SHA), ('install', '/nowhere/p.deb', '3.1')]
    assert _state(app)['current']['state'] == uc.REQUESTED


def test_a_campaign_stopped_during_the_download_installs_nothing(app, ha, monkeypatch, tmp_path):
    """The guard fires while the node downloads: the package is dropped, never installed."""
    from services.scheduler_leader import cluster_utc_now
    calls = []
    package = tmp_path / 'p.deb'

    def download(url, name, expected_sha256=None):
        package.write_bytes(b'pkg')
        calls.append(uc.campaign_tick(now=cluster_utc_now() + timedelta(seconds=uc.NODE_GUARD_SECONDS + 5)))
        return str(package)
    monkeypatch.setattr(updates, 'download_update', download)
    monkeypatch.setattr(updates, 'install_update', lambda path, **kw: calls.append('install'))
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[0][1], node_id=PREFIX + 'a', version='3.0')
    assert calls[0][0] == 'stopped' and 'install' not in calls
    assert not package.exists()
    state = _state(app)
    assert state['status'] == uc.STOPPED and 'within' in state['failed']['reason']


def test_a_stale_turn_never_drops_the_package_of_the_turn_resumed_after_it(app, ha, monkeypatch, tmp_path):
    """Stopped mid-download, resumed, taken again by the sibling process: the first turn's
    late drop leaves the package the second turn handed to the install watcher."""
    from services.scheduler_leader import cluster_utc_now
    installed, downloads = [], []

    def download(url, name, expected_sha256=None):
        path = tmp_path / name
        path.write_bytes(b'pkg')
        downloads.append(name)
        if len(downloads) == 1:  # the first turn's download outlives the guard
            assert uc.campaign_tick(now=cluster_utc_now() + timedelta(
                seconds=uc.NODE_GUARD_SECONDS + 5))[0] == 'stopped'
            assert uc.resume_campaign('admin')[0]
            assert uc.campaign_tick()[0] == 'dispatch'
            uc.run_local_turn(_commands(app)[1][1], node_id=PREFIX + 'a', version='3.0')
        return str(path)
    monkeypatch.setattr(updates, 'download_update', download)
    monkeypatch.setattr(updates, 'install_update', lambda path, **kw: installed.append(path))
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[0][1], node_id=PREFIX + 'a', version='3.0')
    assert len(installed) == 1 and _state(app)['current']['state'] == uc.REQUESTED
    assert installed[0].endswith('.deb') and os.path.exists(installed[0])
    assert len(set(downloads)) == 2


def test_the_full_roll_goes_one_node_after_the_other(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[-1][1], node_id=PREFIX + 'a', version='3.0')
        assert uc.campaign_tick() is None
    _back(app, 'a', '3.1')
    with app.app_context():
        assert uc.campaign_tick()[0] == 'node_done'
        assert uc.campaign_tick() == ('dispatch', PREFIX + 'b', None)
        uc.run_local_turn(_commands(app)[-1][1], node_id=PREFIX + 'b', version='3.0')
    _back(app, 'b', '3.1')
    with app.app_context():
        assert uc.campaign_tick()[0] == 'node_done'
        assert uc.campaign_tick()[0] == 'finished'
    state = _state(app)
    assert state['status'] == uc.DONE and state['done'] == [PREFIX + 'a', PREFIX + 'b']
    assert [c[0] for c in _commands(app)] == [PREFIX + 'a', PREFIX + 'b']


def test_a_failed_download_stops_the_campaign_with_its_reason(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls, fail='Checksum mismatch for p.deb')
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[0][1], node_id=PREFIX + 'a', version='3.0')
        assert uc.campaign_tick() is None
    state = _state(app)
    assert state['status'] == uc.STOPPED
    assert state['failed']['node'] == PREFIX + 'a'
    assert 'Checksum mismatch' in state['failed']['reason']
    assert ('install', '/nowhere/p.deb', '3.1') not in calls


def test_a_command_without_its_checksum_installs_nothing(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls)
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        payload = dict(_commands(app)[0][1], packages={'deb': dict(DEB, sha256=None)})
        uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0')
    assert calls == []
    assert _state(app)['status'] == uc.STOPPED


def test_a_stopped_campaign_resumes_on_request_from_the_failed_node(app, ha, monkeypatch):
    calls = []
    _witnesses(monkeypatch, calls, fail='network down')
    _rows(app, a='3.0', b='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[0][1], node_id=PREFIX + 'a', version='3.0')
        assert uc.resume_campaign('admin')[0]
        assert not uc.resume_campaign('admin')[0]  # running: nothing to resume
        assert uc.campaign_tick() == ('dispatch', PREFIX + 'a', None)
    state = _state(app)
    assert state['status'] == uc.RUNNING and state['failed'] is None


def test_update_is_a_cluster_command_run_by_the_campaign(app):
    from services import cluster_commands as cc
    assert cc.UPDATE in cc.KINDS
    seen = []
    import services.update_campaign as module
    original = module.run_local_turn
    try:
        module.run_local_turn = lambda payload: seen.append(payload)
        cc.HANDLERS[cc.UPDATE]({'campaign': 'x'})
    finally:
        module.run_local_turn = original
    assert seen == [{'campaign': 'x'}]


# ------------------------------------------------------------------ entry points


@pytest.fixture
def no_install(monkeypatch):
    def boom(*a, **k):
        raise AssertionError('no local install in this test')
    monkeypatch.setattr(updates, 'download_update', boom)
    monkeypatch.setattr(updates, 'install_update', boom)


def _release(**kw):
    r = {'update_available': True, 'current_version': '3.0', 'latest_version': '3.1',
         'download_url': 'https://x/p.deb', 'package_name': 'p.deb',
         'checksum_url': 'https://x/p.deb.sha256', 'assets': ASSETS}
    r.update(kw)
    return r


def test_the_install_route_starts_a_rolling_update_in_ha(app, auth_client, ha, monkeypatch, no_install):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **k: _release())
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHA)
    _rows(app, a='3.0', b='3.0')
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 200, r.data
    assert [c[0] for c in _commands(app)] == [PREFIX + 'a']
    r = auth_client.get('/api/v2/system/updates/campaign')
    body = r.get_json()['data']
    assert body['ha'] is True
    assert body['campaign']['target'] == '3.1'
    assert body['campaign']['current']['node'] == PREFIX + 'a'


def test_the_install_route_refuses_a_release_without_checksum_in_ha(app, auth_client, ha, monkeypatch,
                                                                     no_install):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'check_for_updates', lambda **k: _release(checksum_url=None, assets=ASSETS[:1]))
    _rows(app, a='3.0')
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 409, r.data
    assert 'SHA-256' in r.get_json()['detail']
    assert _state(app) is None


def test_the_install_route_in_a_container_names_the_orchestrator_in_ha(auth_client, ha, monkeypatch,
                                                                      no_install):
    monkeypatch.setenv('UCM_DOCKER', '1')
    r = auth_client.post('/api/v2/system/updates/install', json={})
    assert r.status_code == 400, r.data
    assert 'orchestrator' in r.get_json()['message']


def test_the_resume_route_restarts_a_stopped_campaign(app, auth_client, ha, monkeypatch):
    _rows(app, a='3.0')
    _start(app)
    with app.app_context():
        raw, c = uc.read_campaign()
        uc._stop(raw, c, PREFIX + 'a', 'test')
    r = auth_client.post('/api/v2/system/updates/campaign/resume', json={})
    assert r.status_code == 200, r.data
    assert _state(app)['status'] == uc.RUNNING


def test_scheduled_auto_install_in_ha_starts_a_rolling_update(app, ha, monkeypatch, no_install):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHA)
    _rows(app, a='3.0', b='3.0')
    from models import SystemConfig, db
    with app.app_context():
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
        updates._auto_install(_release())
        assert uc.read_campaign()[1]['initiated_by'] == 'scheduler'
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
    assert [c[0] for c in _commands(app)] == [PREFIX + 'a']


def test_scheduled_auto_install_in_ha_without_checksum_starts_nothing(app, ha, monkeypatch, no_install):
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    _rows(app, a='3.0')
    from models import SystemConfig, db
    with app.app_context():
        updates._auto_install(_release(checksum_url=None, assets=ASSETS[:1]))
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
    assert _state(app) is None


def test_scheduled_auto_install_in_a_container_logs_its_refusal(monkeypatch, caplog, no_install):
    monkeypatch.setenv('UCM_DOCKER', '1')
    with caplog.at_level('INFO', logger='ucm.updates'):
        updates._auto_install(_release())
    assert 'orchestrator' in caplog.text


def test_outside_ha_the_scheduled_install_stays_local(app, monkeypatch):
    """Non-regression: no campaign, the local download and install run as before."""
    monkeypatch.setattr(Config, 'HA_MODE', False)
    monkeypatch.delenv('UCM_DOCKER', raising=False)
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHA)
    calls = []
    _witnesses(monkeypatch, calls)
    monkeypatch.setattr(uc, 'start_campaign', lambda *a, **k: calls.append('campaign'))
    from models import SystemConfig, db
    with app.app_context():
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
        updates._auto_install(_release())
        SystemConfig.query.filter_by(key=updates._ATTEMPTED_VERSION_KEY).delete()
        db.session.commit()
    assert calls == [('download', SHA), ('install', '/nowhere/p.deb', '3.1')]


def test_a_stop_is_audited_and_pushed_to_the_browsers(app, ha, monkeypatch):
    import websocket.emitters as ws
    from services.audit_service import AuditService
    alerts, audits = [], []
    monkeypatch.setattr(ws, 'on_system_alert', lambda kind, message, severity, details: alerts.append(
        (kind, severity, details['campaign']['status'], message)))
    monkeypatch.setattr(AuditService, 'log_action', staticmethod(lambda **kw: audits.append(kw)))
    _witnesses(monkeypatch, [], fail='network down')
    _rows(app, a='3.0')
    _start(app)
    with app.app_context():
        uc.campaign_tick()
        uc.run_local_turn(_commands(app)[0][1], node_id=PREFIX + 'a', version='3.0')
    assert alerts[-1][:3] == ('update_campaign', 'critical', uc.STOPPED)
    assert 'network down' in alerts[-1][3]
    assert audits[-1]['success'] is False and 'network down' in audits[-1]['details']
