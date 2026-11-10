"""Orphaned discovery runs: recovered at registration on a single node; in HA by the leader
at takeover and on every pass, and by a node's web process for its own runs at startup."""
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

    def add(node_id, triggered_by='manual', started_at=None):
        run = ScanRun(status='running', triggered_by=triggered_by, node_id=node_id,
                      started_at=started_at or utc_now())
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
    """A fresh node keeps its manual scans, and its scheduled ones started by its current process:
    a former leader that only lost its lock connection still runs them."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    now = utc_now()
    booted = now - timedelta(minutes=10)
    db.session.add(ClusterNode(node_id=NODE + 'alive', started_at=booted, heartbeat_at=now))
    db.session.add(ClusterNode(node_id=NODE + 'gone', started_at=booted - timedelta(hours=1),
                               heartbeat_at=now - timedelta(hours=1)))
    db.session.commit()
    kept = runs(NODE + 'alive', 'manual')
    scheduled = runs(NODE + 'alive', 'scheduled', started_at=booted + timedelta(minutes=1))
    before_boot = runs(NODE + 'alive', 'scheduled', started_at=booted - timedelta(minutes=1))
    gone = runs(NODE + 'gone', 'manual')
    gone_scheduled = runs(NODE + 'gone', 'scheduled', started_at=now - timedelta(minutes=5))
    legacy = runs(None, 'manual')
    scheduler = SchedulerService(wake_interval=60)
    DiscoverySchedulerTask.register(scheduler, app)
    for hook in scheduler._leadership_hooks:
        hook()
    assert [status(r) for r in (kept, scheduled, before_boot, gone, gone_scheduled, legacy)] == \
        ['running', 'running', 'failed', 'failed', 'failed', 'failed']


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


def test_a_starting_ha_node_fails_its_own_runs_left_by_its_previous_process(app, runs, monkeypatch):
    """The gunicorn master starts before its workers: no run of that node can be alive."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', NODE + 'self')
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '1')  # set by gunicorn_config before preload
    monkeypatch.delenv('UCM_SCHEDULER_PROCESS', raising=False)
    own = runs(NODE + 'self', 'manual')
    other = runs(NODE + 'other', 'manual')
    DiscoverySchedulerTask.register(SchedulerService(wake_interval=60), app)
    assert [status(own), status(other)] == ['failed', 'running']


def test_the_scheduler_process_leaves_the_runs_of_live_web_workers_alone(app, runs, monkeypatch):
    """The scheduler child starts after the workers (both env flags set, as in production):
    recovering there would fail scans they run. The master's side is the test above."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', NODE + 'self')
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '1')
    monkeypatch.setenv('UCM_SCHEDULER_PROCESS', '1')
    manual = runs(NODE + 'self', 'manual')
    scheduled = runs(NODE + 'self', 'scheduled')
    DiscoverySchedulerTask.register(SchedulerService(wake_interval=60), app)
    assert [status(manual), status(scheduled)] == ['running', 'running']


def test_each_pass_fails_the_runs_of_nodes_gone_since_takeover(app, runs, monkeypatch):
    """A former leader still fresh at takeover goes stale later: its orphans must not block a profile."""
    from models import ScanProfile
    from services.discovery_service import DiscoveryService
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', NODE + 'leader')
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '1')
    monkeypatch.setenv('UCM_SCHEDULER_PROCESS', '1')  # the leader's scheduler process
    now = utc_now()
    for name, seen in (('leader', now), ('alive', now), ('gone', now - timedelta(hours=1))):
        db.session.add(ClusterNode(node_id=NODE + name, started_at=seen, heartbeat_at=seen))
    profile = ScanProfile(name=NODE + 'profile', targets='["192.0.2.1"]', ports='[443]',
                          schedule_enabled=True, next_scan_at=now - timedelta(minutes=1))
    db.session.add(profile)
    db.session.commit()
    alive = runs(NODE + 'alive', 'manual')
    mine = runs(NODE + 'leader', 'scheduled')
    gone = runs(NODE + 'gone', 'manual')
    orphan = db.session.get(ScanRun, gone)
    orphan.scan_profile_id = profile.id
    db.session.commit()
    started = []
    monkeypatch.setattr(DiscoveryService, 'start_scan', lambda self, **kw: started.append(kw['profile_id']))
    scheduler = SchedulerService(wake_interval=60)
    try:
        DiscoverySchedulerTask.register(scheduler, app)
        scheduler.tasks['discovery_scan'].func()
        assert [status(r) for r in (alive, mine, gone)] == ['running', 'running', 'failed']
        assert started == [profile.id]
    finally:
        ScanRun.query.filter_by(scan_profile_id=profile.id).delete(synchronize_session=False)
        db.session.delete(db.session.get(ScanProfile, profile.id))
        db.session.commit()


def test_each_pass_fails_the_scheduled_runs_of_a_live_nodes_former_process(app, runs, monkeypatch):
    """A's scheduler child dies mid-scan, B takes over while A's row is still fresh, then A's new
    process rewrites its row: the scan belongs to no live process and must not block the profile."""
    from models import ScanProfile
    from services.discovery_service import DiscoveryService
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', NODE + 'b')
    monkeypatch.setenv('UCM_SCHEDULER_SUPERVISED', '1')
    monkeypatch.setenv('UCM_SCHEDULER_PROCESS', '1')  # B's scheduler process
    now = utc_now()
    old_boot = now - timedelta(hours=1)
    db.session.add(ClusterNode(node_id=NODE + 'a', started_at=old_boot, heartbeat_at=now, pid=1001))
    db.session.add(ClusterNode(node_id=NODE + 'b', started_at=now, heartbeat_at=now))
    profile = ScanProfile(name=NODE + 'profile-a', targets='["192.0.2.1"]', ports='[443]',
                          schedule_enabled=True, next_scan_at=now - timedelta(minutes=1))
    db.session.add(profile)
    db.session.commit()
    orphan = runs(NODE + 'a', 'scheduled', started_at=now - timedelta(minutes=10))
    db.session.get(ScanRun, orphan).scan_profile_id = profile.id
    db.session.commit()
    started = []
    monkeypatch.setattr(DiscoveryService, 'start_scan', lambda self, **kw: started.append(kw['profile_id']))
    scheduler = SchedulerService(wake_interval=60)
    try:
        DiscoverySchedulerTask.register(scheduler, app)
        for hook in scheduler._leadership_hooks:
            hook()
        assert status(orphan) == 'running'  # A's row still names the process that started it
        node_a = db.session.get(ClusterNode, NODE + 'a')
        node_a.started_at, node_a.pid, node_a.heartbeat_at = utc_now(), 1002, utc_now()
        db.session.commit()
        for _ in range(3):
            scheduler.tasks['discovery_scan'].func()
        assert status(orphan) == 'failed'
        assert started == [profile.id]
    finally:
        ScanRun.query.filter_by(scan_profile_id=profile.id).delete(synchronize_session=False)
        db.session.delete(db.session.get(ScanProfile, profile.id))
        db.session.commit()
