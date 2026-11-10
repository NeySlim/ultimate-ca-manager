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


@pytest.fixture
def rate_limits(app):
    """Puts the class-level rate limit state and the stored settings back as they were."""
    from models import SystemConfig, db
    from security.rate_limiter import STORED_KEY, RateLimitConfig
    saved = (RateLimitConfig._limits_loaded, RateLimitConfig._enabled,
             dict(RateLimitConfig._custom_limits), set(RateLimitConfig._whitelist))
    yield RateLimitConfig
    (RateLimitConfig._limits_loaded, RateLimitConfig._enabled,
     RateLimitConfig._custom_limits, RateLimitConfig._whitelist) = saved
    with app.app_context():
        SystemConfig.query.filter_by(key=STORED_KEY).delete()
        db.session.commit()


def test_rate_limits_reach_b_over_b_own_environment(app, auth_client, ha, rate_limits, monkeypatch):
    """The command carries what the API stored, not node A's effective limits."""
    import json
    from models import ClusterCommand
    r = auth_client.put('/api/v2/system/security/rate-limit', json={
        'custom_limits': {'/api/v2/cc-test': {'rpm': 7, 'burst': 2}}, 'whitelist_add': ['192.0.2.7']})
    assert r.status_code == 200, r.data
    with app.app_context():
        payload = json.loads(ClusterCommand.query.one().payload)
    assert payload == {'custom_limits': {'/api/v2/cc-test': {'rpm': 7, 'burst': 2}},
                       'whitelist_add': ['192.0.2.7'], 'whitelist_remove': []}
    # Node B: its own environment, booted before the change
    monkeypatch.setenv('RATE_LIMIT_WHITELIST', '10.9.9.9')
    monkeypatch.setenv('RATE_LIMIT_ENABLED', 'false')
    rate_limits.compose(None)
    assert '/api/v2/cc-test' not in rate_limits.get_config()['custom_limits']
    ha('b').start()
    assert wait_for(lambda: rate_limits.get_config()['custom_limits'].get('/api/v2/cc-test')
                    == {'rpm': 7, 'burst': 2})
    config = rate_limits.get_config()
    assert set(config['whitelist']) == {'10.9.9.9', '192.0.2.7'} and config['enabled'] is False


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


def _restart_seen(app, name):
    from models import ClusterNode, db
    with app.app_context():
        db.session.expire_all()
        node = db.session.get(ClusterNode, PREFIX + name)
        return node.restart_seen if node else None


def test_a_second_restart_while_one_is_held_is_absorbed(app, ha):
    """The held restart covers the newer one: reloads behind it go on, the node restarts once."""
    cluster, log = _Cluster(app), []
    for name in ('a', 'b'):
        _node_row(app, name)
    b = ha('b', restart_action=cluster.action('b'), guard=30,
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    _emit(app, cc.RESTART)
    b.start()
    assert wait_for(lambda: b._held is not None)
    second = _emit(app, cc.RESTART)
    started = time.monotonic()
    _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})
    assert wait_for(lambda: log == [('b', 'after')], timeout=5)
    assert time.monotonic() - started < 5 and cluster.events == []
    _back(app, 'a')
    assert wait_for(lambda: ('up', 'b') in cluster.events)
    time.sleep(0.2)
    assert cluster.events == [('down', 'b'), ('up', 'b')]
    assert _restart_seen(app, 'b') == second  # a sibling process cannot claim the newer one


def test_the_held_restart_waits_for_the_node_ahead_to_restart_for_the_newer_one(app, ha):
    """a came back for the first restart only: b, holding both, waits for a's second restart."""
    cluster = _Cluster(app)
    for name in ('a', 'b'):
        _node_row(app, name)
    b = ha('b', restart_action=cluster.action('b'), guard=30)
    first = _emit(app, cc.RESTART)
    b.start()
    assert wait_for(lambda: b._held is not None)
    from models import ClusterCommand, ClusterNode, db
    with app.app_context():  # one commit: b never sees a back without the newer restart
        issued = db.session.get(ClusterCommand, first).created_at
        node = db.session.get(ClusterNode, PREFIX + 'a')
        node.started_at = node.heartbeat_at = issued + timedelta(milliseconds=50)
        newer = ClusterCommand(kind=cc.RESTART, created_at=issued + timedelta(milliseconds=100))
        db.session.add(newer)
        db.session.commit()
        second = newer.id
    assert wait_for(lambda: b.seen == second and b._held is not None and b._held.id == second)
    time.sleep(0.3)
    assert cluster.events == []
    _back(app, 'a')
    assert wait_for(lambda: ('down', 'b') in cluster.events)


def _in_hole(applier, command_id):
    return any(lo <= command_id <= hi for lo, hi, _ in list(applier._holes))


def test_a_restart_committed_late_while_another_is_held_is_absorbed(app, ha):
    """The late one fills its hole: it is neither read again nor a second restart."""
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
            late_id = slow.query(ClusterCommand).one().id
            fast.add(ClusterCommand(kind=cc.RESTART, created_at=utc_now()))
            fast.commit()
            held_id = fast.query(ClusterCommand).one().id
            assert wait_for(lambda: b._held is not None and b._held.id == held_id and _in_hole(b, late_id))
            slow.commit()
        assert wait_for(lambda: not _in_hole(b, late_id))
        after = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})
        assert wait_for(lambda: b.seen == after and log == [('b', 'after')])
        assert b._held.id == held_id and cluster.events == []
        _back(app, 'a')
        assert wait_for(lambda: ('up', 'b') in cluster.events)
        assert cluster.events == [('down', 'b'), ('up', 'b')]
    finally:
        engine.dispose()


def test_a_late_restart_survives_an_error_while_it_is_applied(app, ha, monkeypatch):
    """The hole stays open until the command is applied: a failed pass reads it again."""
    from sqlalchemy.orm import Session
    from models import ClusterCommand
    from services.scheduler_leader import _dedicated_engine, application_url
    log, restarts, calls = [], [], []
    real = cc.pending_predecessors

    def once_broken(*args, **kwargs):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError('database went away')
        return real(*args, **kwargs)
    monkeypatch.setattr(cc, 'pending_predecessors', once_broken)
    _node_row(app, 'solo')
    solo = ha('solo', restart_action=lambda: restarts.append('restart'),
              handlers={cc.RELOAD_SYSLOG: _recorder(log, 'solo')})
    solo.start()
    assert wait_for(lambda: solo.seen is not None)
    with app.app_context():
        engine = _dedicated_engine(application_url())
    try:
        with Session(bind=engine) as slow, Session(bind=engine) as fast:
            slow.add(ClusterCommand(kind=cc.RESTART, created_at=utc_now()))
            slow.flush()  # id taken, not committed
            fast.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "fast"}', created_at=utc_now()))
            fast.commit()
            assert wait_for(lambda: ('solo', 'fast') in log)
            slow.commit()
        assert wait_for(lambda: restarts == ['restart'])
        assert len(calls) >= 2
    finally:
        engine.dispose()


def test_a_restart_action_that_raises_is_retried_and_reloads_go_on(app, ha, monkeypatch):
    monkeypatch.setattr(cc, 'RESTART_RETRY_FIRST', 0.1)
    log, attempts, emitted = [], [], []

    def flaky():
        attempts.append('restart')
        if len(attempts) == 1:
            emitted.append(_emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'}))  # before the retry
            raise OSError('signal file not writable')
    _node_row(app, 'solo')
    solo = ha('solo', restart_action=flaky,
              handlers={cc.RELOAD_SYSLOG: lambda payload: log.append((payload['mark'], solo.restarting))})
    restart_id = _emit(app, cc.RESTART)
    solo.start()
    assert wait_for(lambda: len(attempts) == 2)
    assert log == [('after', False)] and solo.seen == emitted[0]
    assert solo.restarting is True and _restart_seen(app, 'solo') == restart_id
    time.sleep(0.2)
    assert attempts == ['restart', 'restart']  # a restart that ran is not repeated


def test_a_starting_node_replays_recent_reloads_but_no_restart_older_than_itself(app, ha):
    """A reload committed while the process read its settings is replayed; reloads are idempotent."""
    from models import ClusterCommand, db
    cluster, log = _Cluster(app), []
    _node_row(app, 'n')
    started = utc_now()
    with app.app_context():
        rows = [ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "old"}',
                               created_at=started - cc.START_REPLAY - timedelta(seconds=30)),
                ClusterCommand(kind=cc.RESTART, created_at=started - timedelta(seconds=5)),
                ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "recent"}',
                               created_at=started - timedelta(seconds=5))]
        for row in rows:
            db.session.add(row)
            db.session.flush()
        db.session.commit()
        last = rows[-1].id
    n = ha('n', started_at=started, restart_action=cluster.action('n'),
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'n')})
    n.start()
    assert wait_for(lambda: n.seen == last)
    assert log == [('n', 'recent')]
    time.sleep(0.2)
    assert cluster.events == []


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


def test_health_reports_only_the_answering_node_command_seen(app, client, ha, monkeypatch):
    monkeypatch.setattr(Config, 'NODE_ID', PREFIX + 'h')
    _node_row(app, 'h', seen=7)
    _node_row(app, 'other', seen=5)
    cluster = client.get('/health').get_json()['cluster']
    assert cluster['command_seen'] == 7
    assert PREFIX + 'other' not in str(cluster)  # the probe is public: no other node is named


def test_service_status_lists_every_node_to_an_admin_only(app, client, auth_client, ha):
    _node_row(app, 'h', seen=7)
    _node_row(app, 'other', seen=5)
    assert client.get('/api/v2/system/service/status').status_code == 401
    r = auth_client.get('/api/v2/system/service/status')
    assert r.status_code == 200, r.data
    nodes = {n['node_id']: n for n in r.get_json()['data']['cluster']['nodes']}
    assert nodes[PREFIX + 'h']['command_seen'] == 7 and nodes[PREFIX + 'other']['command_seen'] == 5


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


class _FakeMonotonic:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _set_restart_seen(app, name, value):
    from models import ClusterNode, db
    with app.app_context():
        db.session.get(ClusterNode, PREFIX + name).restart_seen = value
        db.session.commit()


def _fail_until(solo, clock, attempts, count):
    """Advances the fake clock one second per pass until ``count`` attempts were made."""
    start = clock.t
    while len(attempts) < count:
        clock.t += 1
        solo.run_once()
        assert clock.t - start <= 600


def _failure_lines(caplog):
    import logging
    return [r.levelno for r in caplog.records
            if r.name == cc.logger.name and 'failed' in r.getMessage() and r.levelno >= logging.WARNING]


def test_a_failing_restart_backs_off_and_logs_one_line_per_step(app, ha, caplog):
    """2 s, 4 s ... 60 s between attempts; ERROR once, then one line per step; reloads go on."""
    import logging
    clock, attempts, log, fail = _FakeMonotonic(), [], [], [True]

    def action():
        attempts.append(clock.t)
        if fail[0]:
            raise OSError('signal file not writable')
    _node_row(app, 'solo')
    solo = ha('solo', monotonic=clock, restart_action=action,
              handlers={cc.RELOAD_SYSLOG: _recorder(log, 'solo')})
    caplog.set_level(logging.INFO, logger=cc.logger.name)
    _emit(app, cc.RESTART)
    solo.run_once()
    _fail_until(solo, clock, attempts, 9)  # past the gap grace when earlier ids are missing
    assert [b - a for a, b in zip(attempts, attempts[1:])] == [2, 4, 8, 16, 32, 60, 60, 60]
    mark = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'waiting'})
    solo.run_once()  # mid-wait: no attempt, the reload is applied
    assert solo.seen == mark and log == [('solo', 'waiting')] and len(attempts) == 9
    lines = [r for r in caplog.records if r.name == cc.logger.name and 'failed' in r.getMessage()]
    assert [r.levelno for r in lines] == [logging.ERROR] + [logging.WARNING] * 5
    fail[0] = False
    clock.t += 60
    solo.run_once()
    assert len(attempts) == 10 and solo.restarting
    assert solo._retry_delay is None  # a restart that ran starts the next failure from 2 s


def test_a_new_restart_after_an_unclaimed_retry_starts_its_backoff_over(app, ha, caplog):
    """The held restart, claimed meanwhile by a sibling process, is dropped: the next one
    that fails is logged at once and retried after the first step."""
    import logging
    clock, attempts = _FakeMonotonic(), []

    def action():
        attempts.append(clock.t)
        raise OSError('signal file not writable')
    _node_row(app, 'solo')
    solo = ha('solo', monotonic=clock, restart_action=action)
    caplog.set_level(logging.INFO, logger=cc.logger.name)
    first = _emit(app, cc.RESTART)
    solo.run_once()
    _fail_until(solo, clock, attempts, 7)  # 2, 4, 8, 16, 32, 60 s
    _set_restart_seen(app, 'solo', first)  # a sibling process took it
    clock.t += 60
    solo.run_once()
    assert len(attempts) == 7
    caplog.clear()
    _emit(app, cc.RESTART)
    _fail_until(solo, clock, attempts, 8)
    failed_at = attempts[-1]
    assert _failure_lines(caplog) == [logging.ERROR]
    _fail_until(solo, clock, attempts, 9)
    assert attempts[-1] - failed_at == cc.RESTART_RETRY_FIRST


def test_a_claim_not_given_back_after_a_failed_restart_is_given_back_later(app, ha, monkeypatch, caplog):
    """The database is lost while the claim is given back: reloads go on, the claim is given
    back on a later pass and the restart is retried after its delay."""
    import logging
    from sqlalchemy import text
    clock, attempts, log = _FakeMonotonic(), [], []
    real_release = cc._RELEASE_SQL

    def action():
        attempts.append(clock.t)
        if len(attempts) == 1:
            monkeypatch.setattr(cc, '_RELEASE_SQL', text('SELECT cc_no_such_function()'))
            raise OSError('signal file not writable')
    _node_row(app, 'solo')
    solo = ha('solo', monotonic=clock, restart_action=action,
              handlers={cc.RELOAD_SYSLOG: _recorder(log, 'solo')})
    caplog.set_level(logging.INFO, logger=cc.logger.name)
    restart_id = _emit(app, cc.RESTART)
    solo.run_once()
    _fail_until(solo, clock, attempts, 1)
    assert _restart_seen(app, 'solo') == restart_id  # still claimed
    assert any(r.levelno == logging.ERROR and 'given back' in r.getMessage() for r in caplog.records)
    monkeypatch.setattr(cc, '_RELEASE_SQL', real_release)
    mark = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})
    solo.run_once()  # same instant: the claim is given back, no attempt yet
    assert solo.seen == mark and log == [('solo', 'after')]
    assert _restart_seen(app, 'solo') is None and len(attempts) == 1
    _fail_until(solo, clock, attempts, 2)
    assert attempts[1] - attempts[0] == cc.RESTART_RETRY_FIRST
    assert solo.restarting and _restart_seen(app, 'solo') == restart_id


def test_stop_during_a_failed_restart_is_not_undone(app, ha):
    """stop() lands between the failed restart's check of _stopping and its _stop.clear()."""
    clock = _FakeMonotonic()

    def fail():
        raise OSError('signal file not writable')
    _node_row(app, 'solo')
    solo = ha('solo', monotonic=clock, restart_action=fail)

    class StopRacesClear(threading.Event):
        def clear(self):
            if not solo._stopping:
                solo.stop()  # no thread: stop() returns without joining
            super().clear()
    solo._stop = StopRacesClear()
    _emit(app, cc.RESTART)
    solo.run_once()
    clock.t += 1
    solo.run_once()
    assert solo._stopping
    assert solo._stop.is_set()  # the applier loop ends instead of reopening a connection


@pytest.mark.parametrize('behind_newer', [False, True], ids=['above-cursor', 'in-hole'])
def test_a_restart_committed_after_the_node_started_runs_though_created_before(app, ha, behind_newer):
    """Its change was not committed when the node read its settings: the node restarts."""
    from sqlalchemy.orm import Session
    from models import ClusterCommand
    from services.scheduler_leader import _dedicated_engine, application_url
    cluster, log = _Cluster(app), []
    _node_row(app, 'n')
    started = utc_now()
    n = ha('n', started_at=started, restart_action=cluster.action('n'),
           handlers={cc.RELOAD_SYSLOG: _recorder(log, 'n')})
    with app.app_context():
        engine = _dedicated_engine(application_url())
    try:
        with Session(bind=engine) as slow, Session(bind=engine) as fast:
            slow.add(ClusterCommand(kind=cc.RESTART, created_at=started - timedelta(seconds=5)))
            slow.flush()  # id taken before the node starts, committed after its first pass
            n.start()
            assert wait_for(lambda: n.seen is not None)
            if behind_newer:
                fast.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "fast"}',
                                        created_at=utc_now()))
                fast.commit()
                assert wait_for(lambda: ('n', 'fast') in log)
            slow.commit()
        assert wait_for(lambda: ('down', 'n') in cluster.events)
    finally:
        engine.dispose()


def test_a_late_reload_whose_handler_always_raises_closes_its_hole_and_holds_nothing(app, ha):
    from sqlalchemy.orm import Session
    from models import ClusterCommand
    from services.scheduler_leader import _dedicated_engine, application_url
    clock, log, calls = _FakeMonotonic(), [], []

    def boom(payload):
        calls.append(payload)
        raise TypeError('invalid payload')
    b = ha('b', monotonic=clock, handlers={cc.RELOAD_RATE_LIMITS: boom, cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    b.run_once()
    with app.app_context():
        engine = _dedicated_engine(application_url())
    try:
        with Session(bind=engine) as slow, Session(bind=engine) as fast:
            slow.add(ClusterCommand(kind=cc.RELOAD_RATE_LIMITS, payload='"not an object"', created_at=utc_now()))
            slow.flush()
            late = slow.query(ClusterCommand).one().id
            fast.add(ClusterCommand(kind=cc.RELOAD_SYSLOG, payload='{"mark": "fast"}', created_at=utc_now()))
            fast.commit()
            for _ in range(3):
                clock.t += 1  # past the gap grace: the late id becomes a hole
                b.run_once()
            assert log == [('b', 'fast')] and _in_hole(b, late)
            slow.commit()
        b.run_once()
        assert calls == ['not an object'] and not _in_hole(b, late)
        after = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'after'})
        clock.t += 1
        b.run_once()
        b.run_once()
        assert b.seen == after and log == [('b', 'fast'), ('b', 'after')] and len(calls) == 1
    finally:
        engine.dispose()


def test_a_hole_whose_command_never_commits_expires(app, ha):
    from models import db
    clock, log = _FakeMonotonic(), []
    b = ha('b', monotonic=clock, handlers={cc.RELOAD_SYSLOG: _recorder(log, 'b')})
    b.run_once()
    with app.app_context():
        lost = cc.emit(cc.RELOAD_SYSLOG, {'mark': 'rolled-back'})
        db.session.flush()
        lost_id = lost.id
        db.session.rollback()
    kept = _emit(app, cc.RELOAD_SYSLOG, {'mark': 'kept'})
    for _ in range(3):
        clock.t += 1
        b.run_once()
    assert b.seen == kept and _in_hole(b, lost_id)
    clock.t += cc.HOLE_TTL_SECONDS - 10
    b.run_once()
    assert _in_hole(b, lost_id)
    clock.t += 20
    b.run_once()
    assert not _in_hole(b, lost_id) and log == [('b', 'kept')]
