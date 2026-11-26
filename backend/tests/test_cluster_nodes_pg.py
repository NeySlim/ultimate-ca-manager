"""HA node registry: every scheduler process heartbeats, one row carries the leader flag,
/health reports the cluster in HA only, readiness waits until this node has ever registered."""
import secrets
import time
from datetime import timedelta

import pytest

from config.settings import Config
from services import scheduler_leader, scheduler_service
from services.scheduler_service import SchedulerService
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

WAKE = 0.2


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def rows(app):
    from models import ClusterNode, db
    with app.app_context():
        db.session.expire_all()
        return {n.node_id: n.is_leader for n in ClusterNode.query.all()
                if n.node_id.startswith(PREFIX)}


PREFIX = f'test-{secrets.token_hex(3)}-'


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path, raising=False)
    monkeypatch.setattr(scheduler_leader, 'LEADER_LOCK_KEY', secrets.randbits(62))
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', 0.2)
    from models import ClusterNode, db
    with app.app_context():
        ClusterNode.query.delete()
        db.session.commit()
    made = []

    def make(name):
        s = SchedulerService(wake_interval=WAKE, node_id=PREFIX + name)
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop(timeout=10)
    from models import ClusterNode, db
    with app.app_context():
        ClusterNode.query.delete()  # the registry of the shared test schema starts empty
        db.session.commit()


def test_both_nodes_heartbeat_and_one_row_is_leader(app, ha):
    a, b = ha('a'), ha('b')
    a.start(app=app)
    assert wait_for(lambda: a._owns_lock)
    b.start(app=app)
    assert wait_for(lambda: len(rows(app)) == 2)
    assert rows(app) == {PREFIX + 'a': True, PREFIX + 'b': False}

    a.stop(timeout=10)  # b takes over: the flag moves, never on two rows
    assert wait_for(lambda: rows(app) == {PREFIX + 'a': False, PREFIX + 'b': True})


def test_the_heartbeat_publishes_the_package_family(app, ha, monkeypatch):
    import services.updates as updates
    from models import ClusterNode, db
    monkeypatch.setattr(updates, 'package_family', lambda: 'rpm-el9')
    a = ha('a')
    a.start(app=app)
    assert wait_for(lambda: PREFIX + 'a' in rows(app))
    a.stop(timeout=10)
    with app.app_context():
        assert db.session.get(ClusterNode, PREFIX + 'a').package_family == 'rpm-el9'
        detail = {n['node_id']: n for n in scheduler_leader.cluster_nodes_detail(WAKE)}
    assert detail[PREFIX + 'a']['package_family'] == 'rpm-el9'


def test_a_node_without_heartbeat_for_three_passes_is_stale(app, ha):
    from models import ClusterNode, db
    a = ha('a')
    a.start(app=app)
    assert wait_for(lambda: PREFIX + 'a' in rows(app))
    a.stop(timeout=10)
    with app.app_context():
        node = db.session.get(ClusterNode, PREFIX + 'a')
        node.heartbeat_at = utc_now() - timedelta(seconds=3 * WAKE - 0.1)
        db.session.commit()
        fresh = scheduler_leader.cluster_summary(WAKE)
        node.heartbeat_at = utc_now() - timedelta(seconds=3 * WAKE + 0.1)
        db.session.commit()
        stale = scheduler_leader.cluster_summary(WAKE)
    assert fresh['nodes'] == 1 and fresh['stale'] == 0
    assert stale['nodes'] == 1 and stale['stale'] == 1


def test_health_carries_the_cluster_in_ha_only(app, client, monkeypatch, ha):
    monkeypatch.setattr(Config, 'NODE_ID', PREFIX + 'a')
    a = ha('a')
    a.start(app=app)
    assert wait_for(lambda: rows(app).get(PREFIX + 'a') is True)
    cluster = client.get('/health').get_json()['cluster']
    assert cluster['leader_node_id'] == PREFIX + 'a'
    assert cluster['nodes'] >= 1 and cluster['stale'] >= 0
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert 'cluster' not in client.get('/health').get_json()


def test_readiness_waits_for_the_first_heartbeat_in_ha(app, client, monkeypatch, ha):
    monkeypatch.setattr(Config, 'NODE_ID', PREFIX + 'late')
    r = client.get('/health/ready')
    assert r.status_code == 503 and r.get_json()['checks']['cluster']['status'] == 'error'
    monkeypatch.setattr(Config, 'HA_MODE', False)
    assert client.get('/health/ready').status_code == 200
    monkeypatch.setattr(Config, 'HA_MODE', True)
    ha('late').start(app=app)
    assert wait_for(lambda: PREFIX + 'late' in rows(app))
    assert client.get('/health/ready').status_code == 200


def test_a_new_leader_clears_the_flag_a_crashed_one_left(app, ha):
    from models import ClusterNode, db
    with app.app_context():
        then = utc_now()
        db.session.add(ClusterNode(node_id=PREFIX + 'crashed', started_at=then, heartbeat_at=then,
                                   is_leader=True, pid=1))
        db.session.commit()
    ha('b').start(app=app)
    assert wait_for(lambda: rows(app) == {PREFIX + 'crashed': False, PREFIX + 'b': True})


def test_a_pass_longer_than_the_stale_window_keeps_the_leader_fresh(app, ha, monkeypatch):
    """A task that outlasts three passes must not leave the cluster without a leader."""
    import time as real_time
    import types
    import utils.datetime_utils as dtu
    shift = {'s': 0.0}
    real_now = dtu.utc_now
    monkeypatch.setattr(scheduler_service, 'time', types.SimpleNamespace(
        time=real_time.time, monotonic=lambda: real_time.monotonic() + shift['s']))
    monkeypatch.setattr(dtu, 'utc_now', lambda: real_now() + timedelta(seconds=shift['s']))
    seen = []

    def slow():
        if not seen:
            shift['s'] += 200  # beyond STALE_PASSES * wake_interval

    def probe():
        if not seen:
            seen.append(scheduler_leader.cluster_summary(60)['leader_node_id'])

    s = SchedulerService(wake_interval=60, node_id=PREFIX + 'slow')
    for name, func in (('slow', slow), ('probe', probe)):
        s.register_task(name, func, interval=0)
        s.tasks[name]._created_at -= timedelta(seconds=60)
    s.start(app=app)
    try:
        assert wait_for(lambda: seen)
    finally:
        s.stop(timeout=10)
    assert seen == [PREFIX + 'slow']


def _long_task(s, name, release, started):
    def run():
        started.set()
        release.wait(10)
    s.register_task(name, run, interval=3600)
    s.tasks[name]._created_at -= timedelta(seconds=3600)


def test_the_leader_stays_fresh_during_one_task_longer_than_the_stale_window(app, ha):
    """One task alone outlasting STALE_PASSES passes: the leader's row and the state it
    publishes stay fresh while it runs, as the followers' do."""
    import threading
    release, started = threading.Event(), threading.Event()
    a = ha('a')
    _long_task(a, 'long', release, started)
    a.start(app=app)
    try:
        assert started.wait(5)
        time.sleep(scheduler_leader.STALE_PASSES * WAKE * 3)
        with app.app_context():
            summary = scheduler_leader.cluster_summary(WAKE)
            assert a._owns_lock
            assert summary['leader_node_id'] == PREFIX + 'a' and summary['stale'] == 0, summary
            assert not a._stale(a._published_state())
    finally:
        release.set()


def test_a_leader_that_lost_its_lock_during_a_long_task_never_reclaims_the_flag(app, ha):
    """Its session gone, the other node leads: the beat of the running task stops, it never
    writes the leader flag back over the new leader's."""
    import threading
    from models import db
    from sqlalchemy import text
    release, started = threading.Event(), threading.Event()
    a, b = ha('a'), ha('b')
    _long_task(a, 'long', release, started)
    a.start(app=app)
    try:
        assert started.wait(5) and a._owns_lock
        b.start(app=app)
        assert wait_for(lambda: len(rows(app)) == 2)
        with app.app_context():
            db.session.execute(text('SELECT pg_terminate_backend(:p)'), {'p': a._leader_lock.backend_pid})
            db.session.commit()
        assert wait_for(lambda: rows(app) == {PREFIX + 'a': False, PREFIX + 'b': True})
        seen = set()
        deadline = time.monotonic() + scheduler_leader.STALE_PASSES * WAKE * 3
        while time.monotonic() < deadline:
            seen.add(tuple(sorted(rows(app).items())))
            time.sleep(WAKE / 4)
        assert seen == {((PREFIX + 'a', False), (PREFIX + 'b', True))}, seen
    finally:
        release.set()


def _beat(app, name, token, age=0.0):
    """A heartbeat of node ``name`` written ``age`` seconds ago."""
    from models import ClusterNode, db
    with app.app_context():
        assert scheduler_leader.write_heartbeat(PREFIX + name, False, utc_now(), token, WAKE)
        if age:
            db.session.get(ClusterNode, PREFIX + name).heartbeat_at = \
                scheduler_leader.cluster_utc_now() - timedelta(seconds=age)
            db.session.commit()


def _ours(entries):
    return sorted(e['node_id'][len(PREFIX):] for e in entries if e['node_id'].startswith(PREFIX))


GONE = scheduler_leader.GONE_PASSES * WAKE


def test_a_node_stopped_cleanly_is_counted_no_more(app, ha):
    """A rolling restart under Kubernetes replaces every pod by one of another name: the
    replaced ones released their rows and count neither in nodes nor in stale."""
    _beat(app, 'live', 'live-token')
    _beat(app, 'gone', 'gone-token')
    with app.app_context():
        assert scheduler_leader.release_node(PREFIX + 'gone', 'gone-token')
        summary = scheduler_leader.cluster_summary(WAKE)
    assert (summary['nodes'], summary['stale']) == (1, 0)


def test_a_node_silent_past_the_gone_window_counts_nowhere(app, ha):
    _beat(app, 'live', 'live-token')
    _beat(app, 'late', 'late-token', age=3 * WAKE + 0.1)  # stale, still counted
    _beat(app, 'lost', 'lost-token', age=GONE + 1)  # killed long ago
    with app.app_context():
        summary = scheduler_leader.cluster_summary(WAKE)
        detail = scheduler_leader.cluster_nodes_detail(WAKE)
    assert (summary['nodes'], summary['stale']) == (2, 1)
    assert _ours(detail) == ['late', 'live']


def test_a_node_stopped_cleanly_is_listed_stopped_and_never_stale(app, ha):
    """The status page judges as /health does: a released row is a stopped node, not a silent one."""
    _beat(app, 'late', 'late-token', age=3 * WAKE + 0.1)
    _beat(app, 'gone', 'gone-token', age=3 * WAKE + 0.1)
    with app.app_context():
        from models import ClusterNode, db
        assert scheduler_leader.release_node(PREFIX + 'gone', 'gone-token')
        db.session.get(ClusterNode, PREFIX + 'gone').is_leader = True  # as a leader stopped last leaves it
        db.session.commit()
        summary = scheduler_leader.cluster_summary(WAKE)
        detail = {n['node_id'][len(PREFIX):]: n for n in scheduler_leader.cluster_nodes_detail(WAKE)
                  if n['node_id'].startswith(PREFIX)}
    assert (summary['nodes'], summary['stale']) == (1, 1)
    assert (detail['gone']['stopped'], detail['gone']['stale']) == (True, False)
    assert detail['gone']['leader'] is False  # a released row leads nothing, flag left or not
    assert (detail['late']['stopped'], detail['late']['stale']) == (False, True)


def test_the_leader_deletes_the_rows_of_gone_nodes_and_a_node_back_writes_one(app, ha):
    from models import ClusterNode, db
    leader = ha('leader')
    leader.start(app=app)
    assert wait_for(lambda: rows(app).get(PREFIX + 'leader') is True)
    _beat(app, 'late', 'late-token', age=3 * WAKE + 0.1)
    _beat(app, 'lost', 'lost-token', age=GONE + 30)
    # After a stale window of leadership: one pass at most
    assert wait_for(lambda: PREFIX + 'lost' not in rows(app), timeout=3 * WAKE + 5)
    assert PREFIX + 'late' in rows(app) and PREFIX + 'leader' in rows(app)
    _beat(app, 'lost', 'lost-token')
    with app.app_context():
        assert db.session.get(ClusterNode, PREFIX + 'lost') is not None
        assert scheduler_leader.cluster_summary(WAKE)['nodes'] >= 3


def test_a_leader_new_to_the_lock_deletes_nothing(app, ha):
    """After a database cut every heartbeat is old: the leader waits a stale window, in which
    every live node beats again, before it deletes a row."""
    leader = ha('fresh-leader')
    leader._led_since = time.monotonic()
    leader._owns_lock = True
    _beat(app, 'quiet', 'quiet-token', age=GONE + 30)
    with app.app_context():
        leader._app = app
        leader._prune_registry()
    assert PREFIX + 'quiet' in rows(app)
    leader._led_since -= 3 * WAKE + 0.1
    with app.app_context():
        leader._prune_registry()
    assert PREFIX + 'quiet' not in rows(app)
    leader._owns_lock = False
