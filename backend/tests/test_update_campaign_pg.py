"""HA rolling update on PostgreSQL: two nodes acting at the same instant take one step.

Two coordinators (two leaders in turn) dispatch one turn and one command; two processes of
the dispatched node download once; two admins starting a campaign start one.
"""
import json
import threading
from datetime import timedelta

import pytest

import services.update_campaign as uc
import services.updates as updates
from config.settings import Config
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PREFIX = 'ucpg-'
SHA = 'cd' * 32
ASSETS = [{'name': 'p.deb', 'browser_download_url': 'https://x/p.deb'},
          {'name': 'p.deb.sha256', 'browser_download_url': 'https://x/p.deb.sha256'},
          {'name': 'full-stop-migrations.json', 'browser_download_url': 'https://x/full-stop-migrations.json'}]


def _clean(app):
    from models import ClusterCommand, ClusterNode, SystemConfig, db
    with app.app_context():
        SystemConfig.query.filter_by(key=uc.CAMPAIGN_KEY).delete()
        ClusterNode.query.delete()
        ClusterCommand.query.filter(ClusterCommand.kind == 'update').delete()
        db.session.commit()


@pytest.fixture
def ha(app, monkeypatch):
    from models import ClusterNode, db
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(updates, 'package_family', lambda: 'deb')
    monkeypatch.setattr(updates, 'fetch_expected_sha256', lambda url, name: SHA)
    monkeypatch.setattr(updates, 'fetch_full_stop_marks', lambda url: {})
    _clean(app)
    now = utc_now()
    with app.app_context():
        for name in ('a', 'b'):
            db.session.add(ClusterNode(node_id=PREFIX + name, started_at=now - timedelta(minutes=10),
                                       heartbeat_at=now, is_leader=False, pid=1, version='3.0',
                                       package_family='deb'))
        db.session.commit()
    yield
    _clean(app)


def _together(app, monkeypatch, run):
    """Both threads read the campaign before either writes it."""
    real = uc.read_campaign
    both = threading.Barrier(2, timeout=10)

    def read_then_meet():
        value = real()
        try:
            both.wait()
        except threading.BrokenBarrierError:
            pass
        return value
    monkeypatch.setattr(uc, 'read_campaign', read_then_meet)
    results, errors = [], []

    def worker(i):
        try:
            with app.app_context():
                results.append(run(i))
                from models import db
                db.session.remove()
        except Exception as exc:  # noqa: BLE001
            errors.append(repr(exc))
    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    monkeypatch.setattr(uc, 'read_campaign', real)
    assert errors == []
    return results


def _commands(app):
    from models import ClusterCommand
    with app.app_context():
        return [(c.node_id, json.loads(c.payload)) for c in
                ClusterCommand.query.filter_by(kind='update').all()]


def test_two_admins_starting_at_once_start_one_campaign(app, ha, monkeypatch):
    results = _together(app, monkeypatch, lambda i: uc.start_campaign('3.1', ASSETS, f'admin{i}')[0])
    assert sorted(results) == [False, True]


def test_two_coordinators_at_once_dispatch_one_turn_and_one_command(app, ha, monkeypatch):
    with app.app_context():
        assert uc.start_campaign('3.1', ASSETS, 'admin')[0]
    results = _together(app, monkeypatch, lambda i: uc.campaign_tick())
    assert sorted(results, key=str) == [('dispatch', PREFIX + 'a', None), None]
    assert [c[0] for c in _commands(app)] == [PREFIX + 'a']


def test_two_processes_of_the_dispatched_node_download_once(app, ha, monkeypatch):
    calls = []
    monkeypatch.setattr(updates, 'download_update',
                        lambda url, name, expected_sha256=None: calls.append(expected_sha256) or '/nowhere/p.deb')
    monkeypatch.setattr(updates, 'install_update', lambda path, **kw: calls.append(path))
    with app.app_context():
        uc.start_campaign('3.1', ASSETS, 'admin')
        uc.campaign_tick()
    payload = _commands(app)[0][1]
    _together(app, monkeypatch, lambda i: uc.run_local_turn(payload, node_id=PREFIX + 'a', version='3.0'))
    assert calls == [SHA, '/nowhere/p.deb']


def test_a_pending_migration_that_needs_a_full_stop_refuses_the_campaign(app, ha, monkeypatch):
    """The registry read is PostgreSQL's: a marked name it lacks refuses, one it holds does not."""
    monkeypatch.setattr(updates, 'fetch_full_stop_marks', lambda url: {
        '300_upgrade_from_2_254': 'applied long ago', '399_drop_relay_payload': 'moved to Redis'})
    with app.app_context():
        ok, message, _ = uc.start_campaign('3.1', ASSETS, 'admin')
        assert uc.read_campaign()[1] is None
    assert not ok and '399_drop_relay_payload' in message and 'moved to Redis' in message
    assert '300_upgrade_from_2_254' not in message
    assert _commands(app) == []
