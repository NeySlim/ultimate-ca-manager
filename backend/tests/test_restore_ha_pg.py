"""A restore in HA on PostgreSQL, node A the session application and node B a second one
(test_cluster_maintenance_pg.py): it waits for every node, commits or rolls back whole,
and lifts the maintenance once every node restarted on the restored state."""
import io
import secrets
import threading
import time

import pytest

from config.settings import Config
from models import db
from services import cluster_commands as cc
from services import cluster_maintenance as cm
from tests import pg_app_harness
from tests.test_cluster_maintenance_pg import (  # noqa: F401  (cluster: fixture)
    PREFIX, _add_user, _archive, _back, _restore, _row, _sql, _user_exists, cluster, wait_for,
)
from utils.datetime_utils import utc_now

pytestmark = pytest.mark.skipif(not pg_app_harness.ENABLED,
                                reason='needs UCM_TEST_APP_PG_URL (HA runs on PostgreSQL)')


def test_a_restore_waits_for_every_fresh_node_and_names_the_silent_one(cluster, auth_client):
    a = cluster.a
    cluster.start('a')  # B is registered and fresh, but its applier never runs
    blob = _archive(a)
    _add_user(a, 'after-backup')

    r = _restore(auth_client, blob)
    assert r.status_code == 409, r.data
    body = r.get_json()
    assert body['code'] == 'maintenance_not_acknowledged'
    assert body['nodes'] == {PREFIX + 'b': ['web', 'scheduler']}
    assert PREFIX + 'b' in body['detail']
    # Nothing restored, nothing left set
    assert _user_exists(a, 'after-backup')
    assert _row(a) is None
    assert wait_for(lambda: not cm.view_of(a).active())


def test_a_restore_on_a_reaches_b_through_the_rolling_restart(cluster, auth_client):
    a, b = cluster.a, cluster.b
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    _add_user(a, 'after-backup')
    bc = b.test_client()

    outcomes, stop = [], threading.Event()

    def write_on_b():
        while not stop.is_set():
            outcomes.append(bc.post('/write').status_code)
            time.sleep(0.01)
    writer = threading.Thread(target=write_on_b)
    writer.start()
    try:
        assert wait_for(lambda: 201 in outcomes)
        r = _restore(auth_client, blob)
        assert r.status_code == 200, r.data
        data = r.get_json()['data']
        assert data['restart_requested'] is True
        assert data['restart_detail'] == cc.ROLLING_RESTART_MESSAGE
        time.sleep(0.3)
    finally:
        stop.set()
        writer.join()

    # B was refused from its acknowledgement on, and is still: it has not restarted
    first = outcomes.index(503)
    assert set(outcomes[first:]) == {503}, outcomes
    assert not _user_exists(a, 'after-backup')
    row = _row(a)
    assert row['phase'] == cm.PHASE_RESTARTING and row['restored_at'] is not None
    restarts = _sql(a, "SELECT count(*) FROM cluster_commands WHERE kind = 'restart' AND id > :f",
                    {'f': cluster.floor})
    assert restarts[0][0] == 1
    assert _sql(a, "SELECT count(*) FROM user_sessions")[0][0] == 0
    assert bc.post('/write').status_code == 503

    # B restarts first: a process started after restored_at serves, A still refuses
    for applier in cluster.appliers:
        applier.stop()
    _back(a, 'b')
    cm.view_of(b).process_started = utc_now()
    cluster.start('b', started_at=utc_now())
    assert wait_for(lambda: bc.post('/write').status_code == 201)
    assert cm.view_of(a).active()
    assert _row(a) is not None
    # Then A: every fresh node runs the restored state, the maintenance is lifted
    _back(a, 'a')
    cm.view_of(a).process_started = utc_now()
    cluster.start('a', started_at=utc_now())
    assert wait_for(lambda: _row(a) is None)
    assert wait_for(lambda: not cm.view_of(a).active())


def test_a_failed_restore_rolls_back_and_lifts_the_maintenance(cluster, auth_client, monkeypatch):
    a, b = cluster.a, cluster.b
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    _add_user(a, 'after-backup')
    from services.backup.restore_core import RestoreCoreMixin
    real = RestoreCoreMixin._apply_all

    def broken(self, *args, **kwargs):
        real(self, *args, **kwargs)
        raise RuntimeError('disk on fire')
    monkeypatch.setattr(RestoreCoreMixin, '_apply_all', broken)

    r = _restore(auth_client, blob, '/api/v2/settings/backup/restore')
    assert r.status_code == 500, r.data
    assert _user_exists(a, 'after-backup')
    assert _row(a) is None
    assert wait_for(lambda: b.test_client().post('/write').status_code == 201)
    assert _sql(a, "SELECT count(*) FROM cluster_commands WHERE kind = 'restart' AND id > :f",
                {'f': cluster.floor})[0][0] == 0


def test_a_maintenance_lifted_during_the_restore_rolls_it_back(cluster, auth_client, monkeypatch):
    a = cluster.a
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    _add_user(a, 'after-backup')
    from services.backup.restore_core import RestoreCoreMixin
    real = RestoreCoreMixin._apply_all

    def lifted_meanwhile(self, *args, **kwargs):
        real(self, *args, **kwargs)
        # An administrator lifts it from node B while the transaction runs
        with cluster.b.app_context():
            assert cm.lift('someone') is not None
    monkeypatch.setattr(RestoreCoreMixin, '_apply_all', lifted_meanwhile)

    r = _restore(auth_client, blob)
    assert r.status_code == 409, r.data
    assert r.get_json()['code'] == 'maintenance_lost'
    assert _user_exists(a, 'after-backup')
    assert _row(a) is None


def test_a_restore_longer_than_its_lease_renews_it(cluster, auth_client, monkeypatch):
    a = cluster.a
    monkeypatch.setattr(cm, 'LEASE_SECONDS', 1)
    monkeypatch.setattr(cm, 'RENEW_SECONDS', 0.2)
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    _add_user(a, 'after-backup')
    from services.backup.restore_core import RestoreCoreMixin
    real = RestoreCoreMixin._apply_all

    def slow(self, *args, **kwargs):
        real(self, *args, **kwargs)
        time.sleep(2.5)
    monkeypatch.setattr(RestoreCoreMixin, '_apply_all', slow)

    r = _restore(auth_client, blob)
    assert r.status_code == 200, r.data
    assert not _user_exists(a, 'after-backup')
    assert _row(a)['phase'] == cm.PHASE_RESTARTING


def _flipped_tail(blob):
    """The archive with its last byte changed: the header and first chunk still open."""
    return blob[:-1] + bytes([blob[-1] ^ 0x01])


@pytest.mark.parametrize('path', ['/api/v2/system/restore', '/api/v2/settings/backup/restore'])
@pytest.mark.parametrize('case', ['wrong_password', 'not_a_backup'])
def test_an_archive_refused_before_decryption_never_sets_the_maintenance(
        cluster, auth_client, monkeypatch, path, case):
    a, b = cluster.a, cluster.b
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    begun = []
    real_begin = cm.Hold.begin.__func__
    monkeypatch.setattr(cm.Hold, 'begin', classmethod(
        lambda cls, *args, **kwargs: begun.append(1) or real_begin(cls, *args, **kwargs)))
    bc = b.test_client()
    outcomes, stop = [], threading.Event()

    def write_on_b():
        while not stop.is_set():
            outcomes.append(bc.post('/write').status_code)
            time.sleep(0.01)
    writer = threading.Thread(target=write_on_b)
    writer.start()
    try:
        assert wait_for(lambda: 201 in outcomes)
        if case == 'wrong_password':
            r = auth_client.post(path, data={'file': (io.BytesIO(blob), 'hd1.ucmbkp'),
                                             'password': 'not-the-password'},
                                 content_type='multipart/form-data')
        else:
            r = _restore(auth_client, secrets.token_bytes(4096), path)
        time.sleep(0.2)
    finally:
        stop.set()
        writer.join()
    assert r.status_code == 400, r.data
    assert begun == []
    assert _row(a) is None
    assert set(outcomes) == {201}, outcomes


def test_an_archive_failing_past_its_first_chunk_is_refused_under_the_maintenance(
        cluster, auth_client):
    a = cluster.a
    cluster.start('a')
    cluster.start('b')
    blob = _archive(a)
    _add_user(a, 'after-backup')
    r = _restore(auth_client, _flipped_tail(blob))
    assert r.status_code == 400, r.data
    assert _user_exists(a, 'after-backup')
    assert wait_for(lambda: _row(a) is None)
