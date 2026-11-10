"""Orphaned discovery runs: recovered at registration on a single node; in HA only by the
leader when it takes over, and only the runs no live node can still be running."""
import secrets
from datetime import timedelta

import pytest

from config.settings import Config
from models import ClusterNode, ScanRun, db
from services.discovery_scheduler_task import DiscoverySchedulerTask
from services.scheduler_service import SchedulerService
from utils.datetime_utils import utc_now

NODE = f'disc-{secrets.token_hex(3)}-'


@pytest.fixture
def runs(app):
    made = []

    def add(node_id, triggered_by='manual'):
        run = ScanRun(status='running', triggered_by=triggered_by, node_id=node_id)
        db.session.add(run)
        db.session.commit()
        made.append(run.id)
        return run.id
    with app.app_context():
        yield add
        ScanRun.query.filter(ScanRun.id.in_(made)).delete(synchronize_session=False)
        ClusterNode.query.filter(ClusterNode.node_id.like(NODE + '%')).delete(synchronize_session=False)
        db.session.commit()


def status(run_id):
    db.session.expire_all()
    return db.session.get(ScanRun, run_id).status


def test_registration_on_an_ha_node_leaves_running_scans_alone(app, runs, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    run_id = runs(NODE + 'other', 'scheduled')
    scheduler = SchedulerService(wake_interval=60)
    DiscoverySchedulerTask.register(scheduler, app)
    assert 'discovery_scan' in scheduler.tasks
    assert status(run_id) == 'running'
    assert scheduler._leadership_hooks  # the leader recovers them when it takes over


def test_registration_on_a_single_node_recovers_as_before(app, runs, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', False)
    run_id = runs(None, 'manual')
    scheduler = SchedulerService(wake_interval=60)
    DiscoverySchedulerTask.register(scheduler, app)
    assert status(run_id) == 'failed'
    assert not scheduler._leadership_hooks


def test_takeover_fails_only_what_no_live_node_runs(app, runs, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    now = utc_now()
    for name, seen in (('alive', now), ('gone', now - timedelta(hours=1))):
        db.session.add(ClusterNode(node_id=NODE + name, started_at=seen, heartbeat_at=seen))
    db.session.commit()
    kept = runs(NODE + 'alive', 'manual')
    scheduled = runs(NODE + 'alive', 'scheduled')  # only a leader runs these: the former one
    gone = runs(NODE + 'gone', 'manual')
    legacy = runs(None, 'manual')
    scheduler = SchedulerService(wake_interval=60)
    DiscoverySchedulerTask.register(scheduler, app)
    for hook in scheduler._leadership_hooks:
        hook()
    assert [status(r) for r in (kept, scheduled, gone, legacy)] == ['running', 'failed', 'failed', 'failed']


def test_a_scan_records_the_node_that_runs_it(app, runs, monkeypatch):
    """Manual scans start in a web worker, scheduled ones on the leader: the scanner names the node."""
    from services.discovery import scanner
    from services.discovery_service import DiscoveryService

    class NoThread:
        def __init__(self, *a, **k):
            pass

        def start(self):
            scanner._scan_semaphore.release()  # what the scan thread does when it ends
    monkeypatch.setattr(scanner.threading, 'Thread', NoThread)
    monkeypatch.setattr(Config, 'NODE_ID', NODE + 'scanner')
    run_id = DiscoveryService().start_scan(['192.0.2.1'], ports=[443])
    try:
        assert db.session.get(ScanRun, run_id).node_id == NODE + 'scanner'
    finally:
        db.session.delete(db.session.get(ScanRun, run_id))
        db.session.commit()
