"""HA cluster maintenance on PostgreSQL: two applications on one schema, as two nodes.

Node A is the session application (the API, the restore routes), node B a second Flask
application on the same database with the maintenance gate, its write guard, a write
route and the health routes. Each runs a CommandApplier over a connection of its own.
"""
import io
import secrets
import threading
import time
from datetime import timedelta

import pytest
from flask import Flask, jsonify
from sqlalchemy import text

from config.settings import Config
from models import db
from services import cluster_commands as cc
from services import cluster_maintenance as cm
from services.backup.manifest import SECTIONS
from tests import pg_app_harness
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')

PREFIX = f'hd1-{secrets.token_hex(3)}-'
PASSWORD = 'Hd1-Restore-Password-2026'
TICK = 0.05


def wait_for(predicate, timeout=8.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _sql(app, statement, params=None):
    """The test's own reads and writes, past the write guard of a node in maintenance."""
    with app.app_context(), cm.exempt():
        result = db.session.execute(text(statement), params or {})
        rows = result.fetchall() if result.returns_rows else None
        db.session.commit()
        return rows


def _reset_view(app):
    view = cm.view_of(app)
    view.row, view.observed, view.process_started, view.deadline = None, None, None, 0.0


def _clean(app):
    _sql(app, "DELETE FROM cluster_maintenance")
    _sql(app, "DELETE FROM cluster_nodes")
    _sql(app, "DELETE FROM users WHERE username LIKE :p", {'p': PREFIX + '%'})
    _sql(app, "DELETE FROM system_config WHERE key LIKE :p", {'p': PREFIX + '%'})


def _node_row(app, name, started_at=None):
    now = utc_now()
    _sql(app, "INSERT INTO cluster_nodes (node_id, started_at, heartbeat_at, is_leader, pid) "
              "VALUES (:n, :s, :h, false, 1)",
         {'n': PREFIX + name, 's': started_at or now - timedelta(seconds=60), 'h': now})


def _back(app, name):
    """What a restarted node's scheduler process writes: a later started_at, a fresh heartbeat."""
    now = utc_now()
    _sql(app, "UPDATE cluster_nodes SET started_at = :t, heartbeat_at = :t WHERE node_id = :n",
         {'t': now, 'n': PREFIX + name})


def _row(app):
    with app.app_context(), cm.exempt():
        row = cm.read_row(db.session)
        db.session.rollback()
        return row


def _node_b(app):
    b = Flask('hd1_node_b')
    b.config.update(SQLALCHEMY_DATABASE_URI=app.config['SQLALCHEMY_DATABASE_URI'],
                    SQLALCHEMY_ENGINE_OPTIONS=app.config.get('SQLALCHEMY_ENGINE_OPTIONS', {}),
                    SECRET_KEY='hd1-node-b')
    db.init_app(b)
    cm.init_app(b)
    from api.health_routes import health_bp
    b.register_blueprint(health_bp)

    @b.route('/write', methods=['POST'])
    def write():
        from models import SystemConfig
        db.session.add(SystemConfig(key=f'{PREFIX}w-{secrets.token_hex(4)}', value='b'))
        db.session.commit()
        return jsonify(ok=True), 201

    @b.route('/read')
    def read():
        return jsonify(n=db.session.execute(text("SELECT count(*) FROM users")).scalar())

    return b


@pytest.fixture
def cluster(app, monkeypatch):
    """Nodes A and B registered and fresh; ``start(name)`` runs that node's applier."""
    monkeypatch.setattr(Config, 'HA_MODE', True)
    monkeypatch.setattr(Config, 'NODE_ID', PREFIX + 'a')
    monkeypatch.setattr(cc, 'GAP_GRACE_SECONDS', 0.3)
    monkeypatch.setattr(cm, 'ACK_TIMEOUT_SECONDS', 4)
    monkeypatch.setattr(cm, 'ACK_POLL_SECONDS', 0.05)
    monkeypatch.setattr(cm, 'OBSERVE_TTL_SECONDS', 0.2)
    _clean(app)
    floor = _sql(app, "SELECT COALESCE(MAX(id), 0) FROM cluster_commands")[0][0]
    _reset_view(app)
    b = _node_b(app)
    _node_row(app, 'a')
    _node_row(app, 'b')
    restarts, appliers = [], []

    def start(name, started_at=None):
        target = app if name == 'a' else b
        applier = cc.CommandApplier(
            target, PREFIX + name, tick=TICK, record=True, scheduler_ack=True,
            started_at=started_at or utc_now() - timedelta(seconds=30),
            restart_action=lambda: restarts.append(name)).start()
        appliers.append(applier)
        return applier

    yield type('Cluster', (), {'a': app, 'b': b, 'start': staticmethod(start), 'restarts': restarts,
                               'appliers': appliers, 'floor': floor})
    for applier in appliers:
        applier.stop()
    _clean(app)
    _sql(app, "DELETE FROM cluster_commands WHERE id > :f", {'f': floor})
    _reset_view(app)
    with b.app_context():
        db.session.remove()
        db.engine.dispose()


def _archive(app):
    """A backup of the users alone, taken now: a replacing restore puts back exactly them."""
    from services.backup_service import BackupService
    with app.app_context():
        blob = BackupService().create_backup(PASSWORD, include={n: n == 'users' for n in SECTIONS})
        db.session.remove()
    return blob


def _add_user(app, name):
    from models import User
    with app.app_context(), cm.exempt():
        db.session.add(User(username=PREFIX + name, email=f'{PREFIX}{name}@example.test',
                            role='viewer', password_hash='x'))
        db.session.commit()


def _user_exists(app, name):
    return bool(_sql(app, "SELECT 1 FROM users WHERE username = :u", {'u': PREFIX + name}))


def _restore(client, blob, path='/api/v2/system/restore'):
    return client.post(path, data={'file': (io.BytesIO(blob), 'hd1.ucmbkp'), 'password': PASSWORD},
                       content_type='multipart/form-data')


def test_b_observes_the_maintenance_refuses_writes_and_acknowledges(cluster, auth_client):
    a, b = cluster.a, cluster.b
    cluster.start('a')
    cluster.start('b')
    bc = b.test_client()
    assert bc.post('/write').status_code == 201

    r = auth_client.post('/api/v2/system/maintenance', json={'lease_minutes': 5})
    assert r.status_code == 200, r.data
    token = _row(a)['token']
    acks = _sql(a, "SELECT node_id, maintenance_ack, maintenance_ack_scheduler FROM cluster_nodes "
                   "ORDER BY node_id")
    assert acks == [(PREFIX + 'a', token, token), (PREFIX + 'b', token, token)]

    refused = bc.post('/write')
    assert refused.status_code == 503 and refused.headers['Retry-After'] == str(cm.RETRY_AFTER_SECONDS)
    assert refused.get_json()['code'] == 'maintenance'
    assert bc.get('/read').status_code == 200
    ready = bc.get('/health/ready')
    assert ready.status_code == 503 and ready.get_json()['status'] == 'maintenance'
    health = bc.get('/health')
    assert health.status_code == 200 and health.get_json()['maintenance']['reason'] == 'manual'
    # A refuses too, except the status and the lift
    assert auth_client.post('/api/v2/certificates', json={}).status_code == 503
    status = auth_client.get('/api/v2/system/maintenance')
    assert status.status_code == 200
    assert all(n['acknowledged'] for n in status.get_json()['data']['nodes'])

    # Lifted from node A: B writes again within a few ticks
    assert auth_client.delete('/api/v2/system/maintenance').status_code == 200
    assert _row(a) is None
    assert wait_for(lambda: bc.post('/write').status_code == 201)
    assert bc.get('/health/ready').get_json()['status'] != 'maintenance'


def test_a_write_flushed_before_the_maintenance_does_not_commit_after_it(cluster):
    b = cluster.b
    from models import SystemConfig
    with b.app_context():
        db.session.add(SystemConfig(key=PREFIX + 'early', value='x'))
        db.session.flush()
        now = utc_now()
        cm.view_of(b).set({'token': 't', 'reason': 'manual', 'phase': cm.PHASE_MANUAL,
                           'started_at': now, 'expires_at': now + timedelta(minutes=1),
                           'restored_at': None, 'node_id': 'x', 'actor': None}, now)
        with pytest.raises(cm.MaintenanceActive):
            db.session.commit()
        db.session.rollback()
    _reset_view(b)
    assert not _sql(b, "SELECT 1 FROM system_config WHERE key = :k", {'k': PREFIX + 'early'})


def _held_row(app, phase, expires_in, holder='dead'):
    now = _sql(app, "SELECT clock_timestamp() AT TIME ZONE 'UTC'")[0][0]
    _sql(app, "INSERT INTO cluster_maintenance (id, token, reason, phase, started_at, expires_at, "
              "node_id) VALUES (1, :t, 'restore', :p, :s, :e, 'gone-node')",
         {'t': holder, 'p': phase, 's': now, 'e': now + timedelta(seconds=expires_in)})


def test_the_lease_of_a_dead_holder_ends_the_maintenance(cluster):
    b = cluster.b
    _held_row(b, cm.PHASE_RESTORING, 1.5)
    cluster.start('b')
    bc = b.test_client()
    assert wait_for(lambda: bc.post('/write').status_code == 503)
    assert wait_for(lambda: _row(b) is None, timeout=6)
    assert wait_for(lambda: bc.post('/write').status_code == 201)
    assert _sql(b, "SELECT count(*) FROM cluster_commands WHERE kind = 'restart' AND id > :f",
                {'f': cluster.floor})[0][0] == 0


def test_a_committed_restore_whose_holder_died_is_completed_by_another_node(cluster):
    a, b = cluster.a, cluster.b
    with a.app_context():
        from models import User, UserSession
        admin = User.query.filter_by(username='admin').one()
        db.session.add(UserSession(user_id=admin.id, session_id=PREFIX + 'old'))
        db.session.commit()
        from auth.session_epoch import current_epoch
        epoch = current_epoch()
    _held_row(b, cm.PHASE_COMMITTED, 0.5)
    cluster.start('b')
    assert wait_for(lambda: (_row(b) or {}).get('phase') == cm.PHASE_RESTARTING, timeout=6)
    with a.app_context():
        assert current_epoch() > epoch, 'the sessions begun before the restore still count'
    # The session rows go in a transaction of their own, after the one that sets the phase
    assert wait_for(lambda: not _sql(a, "SELECT 1 FROM user_sessions WHERE session_id = :s",
                                     {'s': PREFIX + 'old'}))
    assert _sql(a, "SELECT count(*) FROM cluster_commands WHERE kind = 'restart' AND id > :f",
                {'f': cluster.floor})[0][0] == 1
    # B has not restarted: still out of service, and never in between
    assert b.test_client().post('/write').status_code == 503
    assert wait_for(lambda: cm.view_of(b).row['phase'] == cm.PHASE_RESTARTING)
    assert b.test_client().post('/write').status_code == 503


def test_a_node_starting_during_an_uncommitted_restore_waits_for_its_end(cluster):
    a = cluster.a
    _held_row(a, cm.PHASE_RESTORING, 60)
    url = pg_app_harness.app_url(pg_app_harness.SCHEMA)
    done = threading.Event()
    starter = threading.Thread(target=lambda: (cm.wait_while_restoring(url, poll=0.05), done.set()))
    starter.start()
    try:
        assert not done.wait(0.5)
        _sql(a, "UPDATE cluster_maintenance SET phase = :p", {'p': cm.PHASE_COMMITTED})
        assert done.wait(5)
    finally:
        _sql(a, "DELETE FROM cluster_maintenance")
        starter.join(5)
