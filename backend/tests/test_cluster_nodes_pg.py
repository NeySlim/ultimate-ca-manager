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
