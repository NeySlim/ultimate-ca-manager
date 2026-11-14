"""HA: two live processes never share a node identifier. Each node process writes a random
token with its heartbeat; a second one under the same UCM_NODE_ID refuses to start, a running
one that finds its row taken stops leading and fails readiness, and a restart of the same node
(clean stop, or heartbeat expired) always starts."""
import os
import secrets
import signal
import subprocess
import sys
import textwrap
import threading
import time
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

from config.settings import Config
from services import scheduler_leader, scheduler_service
from services.scheduler_service import SchedulerService
from tests import pg_app_harness

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

BACKEND = Path(__file__).resolve().parents[1]
PREFIX = f'nid-{secrets.token_hex(3)}-'
WAKE = 0.2


def wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _now(app):
    with app.app_context():
        return scheduler_leader.cluster_utc_now()


def _put(app, node_id, token, age=0.0, fingerprint=None, leader=False):
    """Write a row as another process would, in one statement."""
    from models import db
    with app.app_context():
        now = scheduler_leader.cluster_utc_now() - timedelta(seconds=age)
        db.session.execute(text(
            "INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, pid, instance_token,"
            " kek_fingerprint) VALUES (:n, :t, :t, :l, 1, :tok, :kek) ON CONFLICT (node_id) DO UPDATE SET"
            " started_at = :t, heartbeat_at = :t, is_leader = :l, instance_token = :tok, kek_fingerprint = :kek"),
            {'n': node_id, 't': now, 'l': leader, 'tok': token, 'kek': fingerprint})
        db.session.commit()


def _row(app, node_id):
    from models import ClusterNode, db
    with app.app_context():
        db.session.expire_all()
        node = db.session.get(ClusterNode, node_id)
        return None if node is None else (node.instance_token, node.is_leader)


@pytest.fixture
def ha(app, monkeypatch, tmp_path):
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr('config.settings.DATA_DIR', tmp_path, raising=False)
    monkeypatch.setattr(scheduler_leader, 'LEADER_LOCK_KEY', secrets.randbits(62))
    monkeypatch.setattr(scheduler_service, 'LOCK_RETRY_SECONDS', 0.1)
    made = []

    def make(name, **kw):
        s = SchedulerService(wake_interval=WAKE, node_id=PREFIX + name, **kw)
        made.append(s)
        return s
    yield make
    for s in made:
        s.stop(timeout=10)
    from models import ClusterNode, db
    with app.app_context():
        ClusterNode.query.filter(ClusterNode.node_id.like(PREFIX + '%')).delete(synchronize_session=False)
        db.session.commit()


# ------------------------------------------------------------ 1. instance token

def test_the_heartbeat_carries_the_process_token(app, ha):
    a = ha('tok', instance_token='token-a')
    a.start(app=app)
    assert wait_for(lambda: _row(app, PREFIX + 'tok') == ('token-a', True))


def test_the_token_is_drawn_once_and_reaches_the_scheduler_process(monkeypatch):
    monkeypatch.delenv(scheduler_leader.INSTANCE_TOKEN_ENV, raising=False)
    token = scheduler_leader.instance_token()
    assert len(token) == 32 and scheduler_leader.instance_token() == token
    import scheduler_supervisor
    seen = {}
    monkeypatch.setattr(scheduler_supervisor.subprocess, 'Popen',
                        lambda cmd, cwd, env: seen.update(env) or None)
    scheduler_supervisor.SchedulerSupervisor()._spawn()
    assert seen[scheduler_leader.INSTANCE_TOKEN_ENV] == token


# ------------------------------------------------------------ 2. refusal at start

def test_a_fresh_row_of_another_live_token_refuses_the_start(app, ha):
    node = PREFIX + 'dup'
    _put(app, node, 'live')
    beats = []

    def beat(_):
        beats.append(1)
        _put(app, node, 'live')  # the other process keeps heartbeating
    with app.app_context():
        # The timeout message would also name the identifier: only the live-process one counts
        with pytest.raises(scheduler_leader.NodeIdTaken,
                           match=f'{node} is already used by another live.*distinct UCM_NODE_ID'):
            scheduler_leader.claim_node_at_start(node, 'mine', stale_seconds=2, poll=0.05, sleep=beat,
                                                 release_at_exit=False)
    assert beats and _row(app, node)[0] == 'live'


def test_the_wait_for_a_held_row_keeps_no_transaction_open(app, ha):
    """A server with idle_in_transaction_session_timeout would end the session mid-wait."""
    from models import db
    node = PREFIX + 'idle'
    _put(app, node, 'old', age=0.5)
    with app.app_context():
        engine = db.engine
    idle = []

    def pause(_):
        with engine.connect() as probe:
            idle.append(probe.execute(text(
                "SELECT count(*) FROM pg_stat_activity WHERE application_name = :name"
                " AND state LIKE 'idle in transaction%' AND pid <> pg_backend_pid()"),
                {'name': pg_app_harness.SCHEMA}).scalar())
        time.sleep(0.05)
    with app.app_context():
        scheduler_leader.claim_node_at_start(node, 'new', stale_seconds=1, poll=0.05, sleep=pause,
                                             release_at_exit=False)
    assert idle and set(idle) == {0}


def test_a_row_of_a_crashed_run_is_taken_once_its_heartbeat_expires(app, ha):
    node = PREFIX + 'crashed'
    _put(app, node, 'old', age=1.0, leader=True)
    with app.app_context():
        waited = scheduler_leader.claim_node_at_start(node, 'new', stale_seconds=1.5, poll=0.05,
                                                      release_at_exit=False)
    assert 0.3 < waited < 1.5
    assert _row(app, node) == ('new', False)  # the dead run's leader flag goes with it


@pytest.mark.parametrize('token,age', [('same', 0.0), (None, 0.0), ('old', 5.0)])
def test_a_restart_of_the_same_node_is_never_refused_nor_delayed(app, ha, token, age):
    node = PREFIX + 'again'
    _put(app, node, token, age=age)
    polls = []
    with app.app_context():
        waited = scheduler_leader.claim_node_at_start(node, 'same', stale_seconds=3, poll=0.05,
                                                      sleep=polls.append, release_at_exit=False)
    # Taken at the first try: not one poll, whatever the database's round trip costs
    assert polls == [] and waited < 3 and _row(app, node)[0] == 'same'


def test_a_claim_alone_does_not_make_the_node_ready(app, ha):
    """Readiness waits for the scheduler process's first heartbeat, as before the claim."""
    node = PREFIX + 'fresh'
    with app.app_context():
        scheduler_leader.claim_node_at_start(node, 'mine', release_at_exit=False)
        assert scheduler_leader.node_registered(node) is False
        assert scheduler_leader.write_heartbeat(node, False, scheduler_leader.cluster_utc_now(), 'mine')
        assert scheduler_leader.node_registered(node) is True


def _campaign(current=None, order=(), done=()):
    from services import update_campaign as uc
    return {'id': 'c1', 'status': uc.RUNNING, 'target': '99.0', 'order': list(order),
            'done': list(done), 'skipped': [], 'current': current,
            'packages': {'deb': {'name': 'ucm.deb'}}}


def _own_nodes():
    from services import update_campaign
    return {k: v for k, v in update_campaign._nodes().items() if k.startswith(PREFIX)}


def test_a_claim_after_a_clean_stop_is_not_the_node_back(app, ha):
    """Until the scheduler's first heartbeat, a claimed row still reads as the previous run:
    neither a rolling update nor a rolling restart takes it for the new process."""
    from models import db
    from services import cluster_commands, update_campaign as uc
    node = PREFIX + 'roll'
    with app.app_context():
        before = scheduler_leader.cluster_utc_now() - timedelta(seconds=30)
        assert scheduler_leader.write_heartbeat(node, False, before, 'old')
        scheduler_leader.release_node(node, 'old')
        since = scheduler_leader.cluster_utc_now()
        scheduler_leader.claim_node_at_start(node, 'new', release_at_exit=False)
        now = scheduler_leader.cluster_utc_now()
        current = {'node': node, 'since': uc._iso(since), 'state': uc.DISPATCHED}
        step = uc.plan_step(_campaign(current, order=[node]), _own_nodes(), now,
                            stale_seconds=60, guard=600)
        assert step == (None, None)
        rows = [r for r in db.session.execute(cluster_commands._NODES_SQL).fetchall()
                if r[0].startswith(PREFIX)]
        assert cluster_commands.pending_predecessors(node + 'z', rows, since, now, 60) == [node]


def test_a_node_joining_during_a_campaign_waits_for_its_first_heartbeat(app, ha):
    from services import update_campaign as uc
    done = PREFIX + 'done'
    with app.app_context():
        assert scheduler_leader.write_heartbeat(done, False, scheduler_leader.cluster_utc_now(), 'd')
        scheduler_leader.claim_node_at_start(PREFIX + 'joiner', 'j', release_at_exit=False)
        _, event = uc.plan_step(_campaign(order=[done], done=[done]), _own_nodes(),
                                scheduler_leader.cluster_utc_now(), stale_seconds=60, guard=600)
    assert event == ('finished', None, None)


def test_a_clean_stop_releases_the_row(app, ha):
    node = PREFIX + 'clean'
    _put(app, node, 'mine')
    with app.app_context():
        assert scheduler_leader.release_node(node, 'other') is False
        assert scheduler_leader.release_node(node, 'mine') is True
    assert _row(app, node)[0] is None


# ------------------------------------------------------------ 3. no race

def test_two_processes_claiming_together_one_wins(app, ha):
    """Both wait on a row lock, then claim at once: a read before the write would let both in."""
    from models import db
    node = PREFIX + 'race'
    _put(app, node, None, age=600)  # stale: free for anyone
    with app.app_context():
        engine = db.engine
    blocker = engine.connect()
    blocker.execute(text("SELECT 1 FROM cluster_nodes WHERE node_id = :n FOR UPDATE"), {'n': node})
    results = {}

    def claim(token):
        with app.app_context():
            try:
                results[token] = scheduler_leader._claim(node, token, 60)
            finally:
                db.session.remove()
    threads = [threading.Thread(target=claim, args=(t,)) for t in ('t1', 't2')]
    for t in threads:
        t.start()
    try:
        def waiting():
            with engine.connect() as probe:
                return probe.execute(text(
                    "SELECT count(*) FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
                    "WHERE NOT l.granted AND a.application_name = :name"),
                    {'name': pg_app_harness.SCHEMA}).scalar() >= 2
        assert wait_for(waiting, timeout=10)
    finally:
        blocker.rollback()
        blocker.close()
    for t in threads:
        t.join(15)
    assert sorted(results.values()) == [False, True]
    assert _row(app, node)[0] == next(t for t, won in results.items() if won)


# ------------------------------------------------------------ 4. running

def test_a_running_node_whose_row_is_taken_stops_leading_and_fails_readiness(app, client, ha,
                                                                              monkeypatch, caplog):
    import logging
    caplog.set_level(logging.INFO, logger='services.scheduler_service')
    node = PREFIX + 'taken'
    monkeypatch.setattr(Config, 'NODE_ID', node)
    _put(app, node, 'intruder')
    stop = threading.Event()

    def intruder():
        while not stop.is_set():
            _put(app, node, 'intruder')
            time.sleep(0.05)
    beat = threading.Thread(target=intruder, daemon=True)
    beat.start()
    s = ha('taken')  # this process's own token
    s.start(app=app)
    try:
        assert wait_for(lambda: s.deposed)
        time.sleep(5 * WAKE)
        assert not s._owns_lock and 'Scheduler lock acquired' not in caplog.text
        assert _row(app, node)[0] == 'intruder'  # never overwritten
        r = client.get('/health/ready')
        assert r.status_code == 503
        assert 'distinct UCM_NODE_ID' in r.get_json()['checks']['cluster']['message']
        assert r.get_json()['leader'] is False
    finally:
        stop.set()
        beat.join(5)
    # The intruder gone, its heartbeat expires: this process holds the row again and may lead
    assert wait_for(lambda: not s.deposed and s._owns_lock, timeout=10)
    assert _row(app, node)[0] == scheduler_leader.instance_token()
    assert client.get('/health/ready').status_code == 200


def test_a_leader_flag_written_by_another_token_is_not_this_node_leading(app, client, ha, monkeypatch):
    """A web worker reads leadership from the row: an intruder's leader flag is not its own."""
    node = PREFIX + 'flag'
    monkeypatch.setattr(Config, 'NODE_ID', node)
    monkeypatch.setattr(scheduler_service, '_scheduler', SchedulerService(wake_interval=60, node_id=node))
    _put(app, node, 'intruder', leader=True)
    with app.app_context():
        assert scheduler_leader.node_is_leader(node, 60) is False
    assert client.get('/health').get_json()['leader'] is False
    _put(app, node, scheduler_leader.instance_token(), leader=True)  # its own flag still counts
    with app.app_context():
        assert scheduler_leader.node_is_leader(node, 60) is True
    assert client.get('/health').get_json()['leader'] is True


def test_a_leader_whose_row_is_taken_gives_the_lock_up(app, ha):
    """A deposed leader releases the leader lock, so another node takes the lead."""
    node = PREFIX + 'deposed'
    s = ha('deposed')
    s.start(app=app)
    assert wait_for(lambda: s._owns_lock and _row(app, node)[1] is True, timeout=10)
    stop = threading.Event()

    def intruder():
        while not stop.is_set():
            _put(app, node, 'intruder', leader=True)
            time.sleep(0.05)
    beat = threading.Thread(target=intruder, daemon=True)
    beat.start()
    try:
        assert wait_for(lambda: s.deposed, timeout=10)
        assert wait_for(lambda: not s._owns_lock)
        other = ha('successor')
        other.start(app=app)
        assert wait_for(lambda: other._owns_lock, timeout=10)
        assert not s._owns_lock
    finally:
        stop.set()
        beat.join(5)


# ------------------------------------------------------------ 5. KEK fingerprint check

def test_the_kek_check_sees_another_process_under_this_identifier(app, ha, monkeypatch):
    from security import master_key_bootstrap
    node = PREFIX + 'kek'
    monkeypatch.setattr(Config, 'NODE_ID', node)
    _put(app, node, 'stranger', fingerprint='ffffffffffffffff')
    with app.app_context():
        assert master_key_bootstrap.live_peers_with_another_kek() == [(node, 'ffffffffffffffff')]
    _put(app, node, scheduler_leader.instance_token(), fingerprint='ffffffffffffffff')
    with app.app_context():
        assert master_key_bootstrap.live_peers_with_another_kek() == []
    _put(app, node, None, fingerprint='ffffffffffffffff')  # released by a clean stop: our own run
    with app.app_context():
        assert master_key_bootstrap.live_peers_with_another_kek() == []


# ------------------------------------------------------------ real processes

BOOT = textwrap.dedent('''
    import sys, time
    import dotenv
    dotenv.load_dotenv = lambda *a, **k: False
    import os
    from pathlib import Path
    from security import encryption  # nor the host's master key
    encryption.MASTER_KEY_PATH = Path(os.environ['DATA_DIR']) / 'master.key'
    encryption.key_encryption.reload()
    from services import scheduler_leader, scheduler_service
    scheduler_service.WAKE_INTERVAL_SECONDS = float(sys.argv[2])
    scheduler_leader.CLAIM_POLL_SECONDS = 0.1
    claim = scheduler_leader.claim_node_at_start
    def timed(*a, **k):
        polls = []
        def sleep(s):
            polls.append(s)
            time.sleep(s)
        waited = claim(*a, sleep=sleep, **k)
        print(f'CLAIMED {time.time():.3f} {waited:.3f} {len(polls)}', flush=True)
        return waited
    scheduler_leader.claim_node_at_start = timed
    from config import settings
    from utils.db_url import sqlalchemy_url
    settings.TestingConfig.SQLALCHEMY_DATABASE_URI = sqlalchemy_url(os.environ['DATABASE_URL'])
    from app import create_app
    app = create_app('testing')
    print('BOOTED', flush=True)
    if sys.argv[1] == 'hold':
        from config.settings import Config
        with app.app_context():
            started = scheduler_leader.cluster_utc_now()
        while True:
            with app.app_context():
                scheduler_leader.write_heartbeat(Config.NODE_ID, False, started)
            time.sleep(0.3)
''')


@pytest.fixture
def boot(tmp_path):
    from cryptography.fernet import Fernet
    name = f'{pg_app_harness.SCHEMA}_nid{secrets.token_hex(2)}'
    pg_app_harness._new_schema(pg_app_harness._marker[0].cursor(), name)
    kek = Fernet.generate_key().decode()
    procs = []

    def start(mode, n, wake):
        data = tmp_path / f'run{n}'
        data.mkdir()
        env = {k: v for k, v in os.environ.items() if k != scheduler_leader.INSTANCE_TOKEN_ENV}
        env.update(UCM_HA='1', UCM_NODE_ID='same-node', DATA_DIR=str(data),
                   DATABASE_PATH=str(data / 'ucm.db'), DATABASE_URL=pg_app_harness.app_url(name),
                   SECRET_KEY='nid-test', KEY_ENCRYPTION_KEY=kek, UCM_SKIP_SECRET_VALIDATION='1')
        p = subprocess.Popen([sys.executable, '-c', BOOT, mode, str(wake)], cwd=BACKEND, env=env,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        procs.append(p)
        return p
    start.url = pg_app_harness.app_url(name)
    yield start
    for p in procs:
        if p.poll() is None:
            p.kill()
            p.wait(10)


def _read_until(proc, marker, timeout=180):
    lines, deadline = [], time.monotonic() + timeout
    while time.monotonic() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        lines.append(line)
        if line.startswith(marker):
            return line, ''.join(lines)
    raise AssertionError(f'{marker} not seen: ' + ''.join(lines)[-3000:])


def test_real_nodes_under_one_identifier(boot):
    wake = 4.0  # stale window: 12 s, longer than a start
    holder = boot('hold', 0, wake)
    _read_until(holder, 'BOOTED')

    duplicate = boot('once', 1, wake)
    out = duplicate.communicate(timeout=180)[0]
    assert duplicate.returncode != 0, out[-3000:]
    assert 'same-node is already used by another live UCM process' in out
    assert 'Give each node a distinct UCM_NODE_ID' in out and 'BOOTED' not in out

    # Killed without a word: the next run of this node waits for the heartbeat to expire
    holder.send_signal(signal.SIGKILL)
    killed = time.time()
    holder.wait(10)
    from sqlalchemy import create_engine
    from utils.db_url import sqlalchemy_url
    engine = create_engine(sqlalchemy_url(boot.url))
    try:
        asked = time.time()
        with engine.connect() as conn:  # the dead run's heartbeat age, on the server's clock
            age = conn.execute(text(
                "SELECT extract(epoch FROM (clock_timestamp() AT TIME ZONE 'UTC') - heartbeat_at)"
                " FROM cluster_nodes WHERE node_id = 'same-node'")).scalar()
    finally:
        engine.dispose()
    expires = asked + 3 * wake - float(age)
    restart = boot('once', 2, wake)
    line, out = _read_until(restart, 'CLAIMED')
    claimed_at, waited = float(line.split()[1]), float(line.split()[2])
    # Not before that heartbeat expires; bounded above by the stale window plus a start
    assert expires - 0.2 <= claimed_at <= killed + 3 * wake + 30, out
    out += restart.communicate(timeout=180)[0]
    assert restart.returncode == 0 and 'BOOTED' in out, out[-3000:]
    print(f'restart after SIGKILL claimed the row {claimed_at - killed:.2f}s after the kill, '
          f'{claimed_at - expires:.2f}s after expiry, waited {waited:.2f}s (stale window {3 * wake:.0f}s)')

    # That run stopped cleanly: the row is free, the next one starts at once
    again = boot('once', 3, wake)
    out = again.communicate(timeout=180)[0]
    assert again.returncode == 0, out[-3000:]
    claimed = next(ln for ln in out.splitlines() if ln.startswith('CLAIMED')).split()
    assert claimed[3] == '0' and float(claimed[2]) < 3 * wake, out  # no poll: taken at once


def test_a_refused_duplicate_leaves_the_live_node_scans_alone(boot):
    """The claim comes before anything this node's start would change, such as failing the
    discovery scans recorded under its identifier."""
    from sqlalchemy import create_engine
    from utils.db_url import sqlalchemy_url
    holder = boot('hold', 0, 4.0)
    _read_until(holder, 'BOOTED')
    engine = create_engine(sqlalchemy_url(boot.url))
    try:
        with engine.begin() as conn:
            run = conn.execute(text(
                "INSERT INTO discovery_scan_runs (started_at, status, total_targets, targets_scanned,"
                " certs_found, new_certs, changed_certs, errors, triggered_by, timeout, max_workers,"
                " resolve_dns, node_id) VALUES (now(), 'running', 1, 0, 0, 0, 0, 0, 'manual', 5, 20,"
                " false, 'same-node') RETURNING id")).scalar()
        duplicate = boot('once', 1, 4.0)
        out = duplicate.communicate(timeout=180)[0]
        assert duplicate.returncode != 0 and 'distinct UCM_NODE_ID' in out, out[-3000:]
        with engine.connect() as conn:
            assert conn.execute(text("SELECT status FROM discovery_scan_runs WHERE id = :i"),
                                {'i': run}).scalar() == 'running'
    finally:
        engine.dispose()
