"""HA cluster commands on PostgreSQL: two nodes' appliers on the same schema.

A change made on node A reaches node B's memory; a command exists only if its
transaction commits; a failing handler holds nothing back; a rolling restart goes
one node at a time, in node_id order, spares a node started later and does not wait
for a dead node past the guard delay.
"""
import secrets
import threading
import time
from datetime import timedelta

import pytest

from config.settings import Config
from services import cluster_commands as cc
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PREFIX = f'cc-{secrets.token_hex(3)}-'
TICK = 0.05


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _clean(app):
    from models import ClusterCommand, ClusterNode, db
    with app.app_context():
        ClusterCommand.query.delete()
        ClusterNode.query.filter(ClusterNode.node_id.like(PREFIX + '%')).delete(synchronize_session=False)
        db.session.commit()


def _node_row(app, name, started_at=None, seen=None):
    from models import ClusterNode, db
    now = utc_now()
    with app.app_context():
        db.session.add(ClusterNode(node_id=PREFIX + name, started_at=started_at or now - timedelta(seconds=60),
                                   heartbeat_at=now, is_leader=False, pid=1, command_seen=seen))
        db.session.commit()


def _back(app, name):
    """What a restarted node's scheduler process writes: a later started_at, a fresh heartbeat."""
    from models import ClusterNode, db
    with app.app_context():
        node = db.session.get(ClusterNode, PREFIX + name)
        if node is None:
            return  # the test is over
        node.started_at = node.heartbeat_at = utc_now()
        db.session.commit()


def _emit(app, kind, payload=None, target=None):
    from models import db
    with app.app_context():
        command = cc.emit(kind, payload, target)
        db.session.commit()
        return command.id


@pytest.fixture
def ha(app, monkeypatch):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)
    _clean(app)
    made = []

    def make(name, **kw):
        kw.setdefault('tick', TICK)
        kw.setdefault('started_at', utc_now() - timedelta(seconds=30))
        applier = cc.CommandApplier(app, PREFIX + name, **kw)
        made.append(applier)
        return applier
    yield make
    for applier in made:
        applier.stop()
    _clean(app)


def _recorder(log, name):
    return lambda payload: log.append((name, (payload or {}).get('mark')))


def test_rate_limits_changed_on_a_reach_b(app, auth_client, ha):
    from security.rate_limiter import RateLimitConfig
    before = RateLimitConfig.snapshot()
    b = ha('b')
    try:
        r = auth_client.put('/api/v2/system/security/rate-limit',
                            json={'custom_limits': {'/api/v2/cc-test': {'rpm': 7, 'burst': 2}}})
        assert r.status_code == 200, r.data
        RateLimitConfig.apply_snapshot(before)  # node B's memory never saw the request
        assert '/api/v2/cc-test' not in RateLimitConfig.snapshot()['custom_limits']
        b.start()
        assert wait_for(lambda: RateLimitConfig.snapshot()['custom_limits'].get('/api/v2/cc-test')
                        == {'rpm': 7, 'burst': 2})
    finally:
        RateLimitConfig.apply_snapshot(before)


def test_syslog_changed_on_a_reaches_b(app, auth_client, ha):
    from services.syslog_service import syslog_forwarder
    old = dict(syslog_forwarder.config)
    b = ha('b')
    try:
        r = auth_client.put('/api/v2/system/audit/syslog', json={
            'enabled': False, 'host': 'collector.cc.example', 'port': 5514, 'protocol': 'udp'})
        assert r.status_code == 200, r.data
        syslog_forwarder.configure(enabled=False, host=old['host'], port=old['port'])
        b.start()
        assert wait_for(lambda: syslog_forwarder.config['port'] == 5514
                        and syslog_forwarder.config['host'] == 'collector.cc.example')
    finally:
        auth_client.put('/api/v2/system/audit/syslog', json={
            'enabled': False, 'host': old['host'], 'port': old['port'], 'protocol': old['protocol']})
        syslog_forwarder.configure(enabled=False, host=old['host'], port=old['port'])


def test_admin_allowlist_change_is_emitted_with_its_commit(app, auth_client, ha):
    from models import ClusterCommand
    r = auth_client.patch('/api/v2/settings/general', json={'admin_allowed_networks': '127.0.0.0/8'})
    assert r.status_code == 200, r.data
    try:
        with app.app_context():
            kinds = [c.kind for c in ClusterCommand.query.all()]
        assert kinds == [cc.RELOAD_ADMIN_ALLOWLIST]
    finally:
        auth_client.patch('/api/v2/settings/general', json={'admin_allowed_networks': ''})


def test_a_command_in_a_rolled_back_transaction_is_never_applied(app, ha):
    from models import db
    log = []
    b = ha('b', handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    with app.app_context():
        cc.emit(cc.RELOAD_SYSLOG, {'mark': 'rolled-back'})
        db.session.flush()
        db.session.rollback()
    kept = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'kept'})
    b.start()
    assert wait_for(lambda: b.seen == kept)
    assert log == [('b', 'kept')]


def test_a_failing_handler_holds_nothing_back_and_is_not_replayed(app, ha):
    log, calls = [], []

    def boom(payload):
        calls.append(payload)
        raise RuntimeError('handler down')
    b = ha('b', handlers={cc.RELOAD_RATE_LIMITS: boom, cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    _node_row(app, 'b')
    _emit(app, cc.RELOAD_RATE_LIMITS)
    first = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after-failure'})
    b.start()
    assert wait_for(lambda: b.seen == first)
    last = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'later'})
    assert wait_for(lambda: b.seen == last)
    assert len(calls) == 1
    assert log == [('b', 'after-failure'), ('b', 'later')]
    assert wait_for(lambda: _seen(app, 'b') == last)


def _seen(app, name):
    from models import ClusterNode, db
    with app.app_context():
        db.session.expire_all()
        node = db.session.get(ClusterNode, PREFIX + name)
        return node.command_seen if node else None


def test_a_command_committed_late_behind_a_newer_one_is_still_applied(app, ha):
    """Ids are given at insert, rows appear at commit: an older id may show up after a newer one."""
    from sqlalchemy.orm import Session
    from models import ClusterCommand
    from services.scheduler_leader import _dedicated_engine, application_url
    log = []
    b = ha('b', handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    b.start()
    assert wait_for(lambda: b.seen is not None)
    with app.app_context():
        engine = _dedicated_engine(application_url())
    try:
        with Session(bind=engine) as slow, Session(bind=engine) as fast:
            slow.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "slow"}', created_at=utc_now()))
            slow.flush()  # id taken, not committed
            fast.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "fast"}', created_at=utc_now()))
            fast.commit()
            assert wait_for(lambda: ('b', 'fast') in log)
            slow.commit()  # the older id commits after the newer one was applied
        assert wait_for(lambda: ('b', 'slow') in log)
        assert log == [('b', 'fast'), ('b', 'slow')]
    finally:
        engine.dispose()


def test_a_restart_committed_late_still_runs_once_the_node_ahead_is_back(app, ha):
    """The restart lands in a hole while node a still runs its old process: b must not drop it."""
    from sqlalchemy.orm import Session
    from models import ClusterCommand
    from services.scheduler_leader import _dedicated_engine, application_url
    cluster, log = _Cluster(app), []
    for name in ('a', 'b'):
        _node_row(app, name)
    b = ha('b', restart_action=cluster.action('b'), guard=30,
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    b.start()
    assert wait_for(lambda: b.seen is not None)
    with app.app_context():
        engine = _dedicated_engine(application_url())
    try:
        with Session(bind=engine) as slow, Session(bind=engine) as fast:
            slow.add(ClusterCommand(kind=cc.RESTART, created_at=utc_now()))
            slow.flush()  # id taken, not committed
            fast.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "fast"}', created_at=utc_now()))
            fast.commit()
            assert wait_for(lambda: ('b', 'fast') in log)
            slow.commit()
        assert wait_for(lambda: b._restart_wait is not None)  # b saw it, a is ahead
        assert cluster.events == []
        _back(app, 'a')
        assert wait_for(lambda: ('up', 'b') in cluster.events)  # nothing left to touch b's row later
    finally:
        engine.dispose()


class _Cluster:
    """Restart actions that simulate the node going down, then coming back later."""

    def __init__(self, app, down_for=0.4):
        self.app, self.down_for = app, down_for
        self.events = []
        self.lock = threading.Lock()

    def action(self, name):
        def restart():
            with self.lock:
                self.events.append(('down', name))

            def come_back():
                time.sleep(self.down_for)
                with self.lock:
                    self.events.append(('up', name))  # before the row says so: the next one may go then
                _back(self.app, name)
            threading.Thread(target=come_back, daemon=True).start()
        return restart


def test_rolling_restart_goes_in_node_order_one_at_a_time(app, ha):
    cluster = _Cluster(app)
    names = ['a', 'b', 'c']
    for name in names:
        _node_row(app, name)
    appliers = [ha(n, restart_action=cluster.action(n), guard=30) for n in reversed(names)]
    _emit(app, cc.RESTART)
    for applier in appliers:
        applier.start()
    assert wait_for(lambda: len(cluster.events) == 6, timeout=15)
    assert cluster.events == [('down', 'a'), ('up', 'a'), ('down', 'b'), ('up', 'b'),
                              ('down', 'c'), ('up', 'c')]


def test_a_node_back_under_the_same_pid_releases_the_next_one(app, ha):
    """A restarted container often reuses its pid: the heartbeat still carries the new started_at."""
    from services.scheduler_leader import write_heartbeat
    events = []

    def beat(name, started_at):
        with app.app_context():
            write_heartbeat(PREFIX + name, False, started_at)

    def restart_a():
        events.append(('down', 'a'))
        threading.Timer(0.3, beat, args=('a', utc_now())).start()
    for name in ('a', 'b'):
        beat(name, utc_now() - timedelta(seconds=60))
    appliers = [ha('a', restart_action=restart_a, guard=30),
                ha('b', clock=lambda: utc_now() + LAG, restart_action=lambda: events.append(('down', 'b')),
                   guard=30)]
    _emit(app, cc.RESTART)
    for applier in appliers:
        applier.start()
    assert wait_for(lambda: ('down', 'b') in events, timeout=8)


def test_a_node_started_after_the_restart_command_is_spared(app, ha):
    cluster = _Cluster(app)
    log = []
    restart_id = _emit(app, cc.RESTART)
    _node_row(app, 'late', started_at=utc_now())
    late = ha('late', started_at=utc_now(), restart_action=cluster.action('late'),
              handlers={cc.RELOAD_SYSLOG: _recorder(log, 'late')})
    after = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})
    late.seen = restart_id - 1  # as if the restart committed after this process read its cursor
    late.start()
    assert wait_for(lambda: late.seen == after)
    assert restart_id < after and log == [('late', 'after')]
    assert cluster.events == []


def test_a_node_waiting_its_turn_keeps_applying_reloads_in_order(app, ha):
    cluster, log = _Cluster(app), []
    for name in ('a', 'b'):
        _node_row(app, name)
    b = ha('b', restart_action=cluster.action('b'), guard=30,
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    _emit(app, cc.RESTART)
    b.start()
    assert wait_for(lambda: b._restart_wait is not None)  # a is ahead and still on its old process
    started = time.monotonic()
    _emit(app, cc.RELOAD_SYSLOG, {'mark': 1})
    _emit(app, cc.RELOAD_SYSLOG, {'mark': 2})
    assert wait_for(lambda: len(log) == 2, timeout=10)
    assert time.monotonic() - started < 10
    assert log == [('b', 1), ('b', 2)] and cluster.events == []
    _back(app, 'a')
    assert wait_for(lambda: ('up', 'b') in cluster.events)  # the restart still runs, once
    assert cluster.events == [('down', 'b'), ('up', 'b')]


LAG = timedelta(hours=1)


def _lagging():
    return utc_now() - LAG


def test_a_node_whose_clock_lags_is_spared_by_a_restart_older_than_its_process(app, ha):
    cluster, log = _Cluster(app), []
    restart_id = _emit(app, cc.RESTART)
    _node_row(app, 'n', started_at=utc_now())
    n = ha('n', clock=_lagging, started_at=_lagging(), restart_action=cluster.action('n'),
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'n')})
    n.start()
    assert wait_for(lambda: n.seen is not None)
    after = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})  # emitted once n runs: never in its start cursor
    assert wait_for(lambda: n.seen == after)
    assert restart_id < after and log == [('n', 'after')]
    assert cluster.events == []


def test_skewed_clocks_keep_the_rolling_restart_in_turn(app, ha, monkeypatch):
    """Node a's host clock is an hour late, b's an hour early: a's heartbeat and start time,
    read by b, still say whether a is back."""
    from services import scheduler_service
    from services.scheduler_service import SchedulerService
    monkeypatch.setattr(scheduler_service, 'utc_now', _lagging)  # only node a runs a scheduler here
    events = []

    def beat_a(started_ago):
        sched = SchedulerService(node_id=PREFIX + 'a')
        sched._app = app
        sched._started_at -= started_ago
        sched._heartbeat(force=True)

    def restart_a():
        events.append(('down', 'a'))

        def back():
            time.sleep(0.3)
            events.append(('up', 'a'))
            beat_a(timedelta(0))
        threading.Thread(target=back, daemon=True).start()
    beat_a(timedelta(seconds=60))
    _node_row(app, 'b')
    appliers = [ha('a', clock=_lagging, started_at=_lagging() - timedelta(seconds=30),
                   restart_action=restart_a, guard=30),
                ha('b', clock=lambda: utc_now() + LAG, restart_action=lambda: events.append(('down', 'b')),
                   guard=30)]
    _emit(app, cc.RESTART)
    for applier in appliers:
        applier.start()
    assert wait_for(lambda: ('down', 'b') in events, timeout=8)
    assert events == [('down', 'a'), ('up', 'a'), ('down', 'b')]


def test_a_dead_node_holds_the_next_one_only_for_the_guard_delay(app, ha):
    cluster = _Cluster(app)
    _node_row(app, 'a')  # fresh heartbeat, but nothing runs there any more
    _node_row(app, 'b')
    b = ha('b', restart_action=cluster.action('b'), guard=1.0)
    _emit(app, cc.RESTART)
    started = time.monotonic()
    b.start()
    assert wait_for(lambda: ('down', 'b') in cluster.events, timeout=8)
    assert time.monotonic() - started >= 1.0
    assert wait_for(lambda: ('up', 'b') in cluster.events)  # nothing left to touch b's row later


def test_a_single_node_cluster_restarts_at_once(app, ha):
    cluster = _Cluster(app)
    _node_row(app, 'solo')
    solo = ha('solo', restart_action=cluster.action('solo'), guard=60)
    _emit(app, cc.RESTART)
    solo.start()
    assert wait_for(lambda: ('down', 'solo') in cluster.events, timeout=5)


def test_two_processes_of_one_node_restart_it_once(app, ha):
    cluster = _Cluster(app, down_for=30)
    _node_row(app, 'n')
    first = ha('n', restart_action=cluster.action('n'), guard=60)
    second = ha('n', restart_action=cluster.action('n'), guard=60)
    restart_id = _emit(app, cc.RESTART)
    first.start()
    second.start()
    assert wait_for(lambda: first.seen == restart_id and second.seen == restart_id)
    time.sleep(0.2)  # a second action would be immediate: both appliers already passed the command
    assert cluster.events == [('down', 'n')]


def test_restart_service_in_ha_queues_a_rolling_restart_and_writes_no_file(app, ha, monkeypatch, tmp_path):
    from config import settings
    from models import ClusterCommand
    monkeypatch.setattr(settings, 'DATA_DIR', tmp_path)
    monkeypatch.setattr(settings, 'is_docker', lambda: True)
    with app.app_context():
        ok, _ = settings.restart_ucm_service()
        kinds = [c.kind for c in ClusterCommand.query.all()]
    assert ok is True and kinds == [cc.RESTART]
    assert not (tmp_path / '.restart_requested').exists()


def test_service_restart_route_is_allowed_in_ha_even_in_a_container(app, auth_client, ha, monkeypatch):
    from models import ClusterCommand
    monkeypatch.setattr('api.v2.system.service.is_docker', lambda: True)
    r = auth_client.post('/api/v2/system/service/restart', json={})
    assert r.status_code == 200, r.data
    with app.app_context():
        assert [c.kind for c in ClusterCommand.query.all()] == [cc.RESTART]


def test_health_reports_command_seen_per_node(app, client, ha, monkeypatch):
    _node_row(app, 'h', seen=7)
    cluster = client.get('/health').get_json()['cluster']
    assert cluster['command_seen'][PREFIX + 'h'] == 7


def test_the_leader_purges_commands_older_than_a_day(app, ha):
    from models import ClusterCommand, db
    with app.app_context():
        old = ClusterCommand(kind=cc.RESTART, created_at=utc_now() - timedelta(hours=25))
        recent = ClusterCommand(kind=cc.RESTART, created_at=utc_now() - timedelta(hours=23))
        db.session.add_all([old, recent])
        db.session.commit()
        recent_id = recent.id
        cc.purge_old_commands()
        assert [c.id for c in ClusterCommand.query.all()] == [recent_id]
