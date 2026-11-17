"""Background jobs on two real nodes: one active job per slot on the whole cluster, who takes
what, what becomes of a job whose node dies or loses the lead, a cancellation from the other
node, and a restore whose every node then serves the restored state.

A job is held at a named point by a pause file of its node (tests/ha/guard/ha_bench_pauses.py),
so it is RUNNING (read in the jobs table) when the bench acts on it; no product code changes.
"""
import json
import threading
import time

import pytest

from services.cluster_maintenance import LEASE_SECONDS as MAINTENANCE_LEASE, OBSERVE_TTL_SECONDS
from services.jobs.runner import RECOVER_SECONDS
from services.jobs.store import LEASE_SECONDS, NOT_TAKEN_SECONDS
from services.scheduler_leader import LEADER_LOCK_KEY, STALE_PASSES
from services.scheduler_service import LOCK_RETRY_SECONDS, WAKE_INTERVAL_SECONDS
from tests.ha.cluster import READY_TIMEOUT, Client, create_ca, single_leader, wait_until

pytestmark = pytest.mark.ha

PASSWORD = 'ha-bench-jobs-2026'
ASYNC = {'Prefer': 'respond-async'}
FINAL = ('succeeded', 'failed', 'cancelled')
TAKEOVER_BOUND = LOCK_RETRY_SECONDS + STALE_PASSES * WAKE_INTERVAL_SECONDS
MARGIN = 30


# -- helpers -----------------------------------------------------------------

def _roles(cluster):
    """(leader, follower) as the nodes report them now."""
    leader = wait_until(lambda: single_leader(cluster.nodes, settling=True), 120, 'one leader')
    return leader, next(n for n in cluster.nodes if n is not leader)


def _login(cluster, node):
    """Signed in on ``node``; a view still showing a maintenance just lifted refuses it for
    OBSERVE_TTL_SECONDS at most."""
    def attempt():
        try:
            return Client.login(node, cluster.password)
        except AssertionError as e:
            if ': 503 ' not in str(e):
                raise
            return None
    return wait_until(attempt, 3 * OBSERVE_TTL_SECONDS + 30, f'sign-in on {node.name}')


def _job(cluster, job_id):
    rows = cluster.sql('SELECT state, reason, phase, executor, node_id, secret, lease_expires_at, '
                       'result, cancel_requested FROM background_jobs WHERE id = %s', (job_id,))
    if not rows:
        return None
    keys = ('state', 'reason', 'phase', 'executor', 'node_id', 'secret', 'lease', 'result',
            'cancel_requested')
    job = dict(zip(keys, rows[0]))
    job['by'] = (job['executor'] or '').split('/')[0] or None
    return job


def _final(cluster, job_id, timeout):
    return wait_until(lambda: (_job(cluster, job_id) or {}).get('state') in FINAL and
                      _job(cluster, job_id), timeout, f'job {job_id} final')


def _audit_lines(cluster, job_id):
    return cluster.sql('SELECT count(*) FROM audit_logs WHERE resource_id = %s', (job_id,))[0][0]


def _active(cluster):
    return cluster.sql("SELECT id, kind FROM background_jobs WHERE state IN ('pending', 'running')")


def _post(client, path, payload=None, headers=None, **kw):
    return client.http.post(client.node.url(path), json=payload if 'files' not in kw else None,
                            headers={**client._headers(), **(headers or {})}, timeout=120, **kw)


def _backup(client, headers=ASYNC):
    return _post(client, '/api/v2/system/backup', {'password': PASSWORD}, headers)


def _restore(client, archive, headers=ASYNC):
    return client.http.post(client.node.url('/api/v2/system/restore'),
                            headers={**client._headers(), **(headers or {})},
                            files={'file': (archive['name'], archive['content'])},
                            data={'password': PASSWORD}, timeout=120)


def _accepted(r):
    assert r.status_code == 202, f'{r.status_code} {r.text[:500]}'
    return r.json()['data']['job']['id']


def _cancel(client, job_id):
    return _post(client, f'/api/v2/system/jobs/{job_id}/cancel')


def _backups(client):
    r = client.get('/api/v2/system/backups?per_page=100')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:300]}'
    return sorted(item['filename'] for item in r.json()['data']['items'])


def _cas(client):
    r = client.get('/api/v2/cas?per_page=100')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:300]}'
    data = r.json()['data']
    items = data if isinstance(data, list) else data.get('items', [])
    return {ca.get('descr') or ca.get('common_name') for ca in items}


def _busy(r, job_id, kind):
    """409 naming the active job: id, type, start and requester."""
    assert r.status_code == 409, f'{r.status_code} {r.text[:500]}'
    named = r.json()['details']['job']
    assert named['id'] == job_id and named['kind'] == kind, named
    assert named['created_at'] and named['requested_by']['username'] == 'admin', named


def _running_at(cluster, node, job_id, point, phase=None):
    """The job is RUNNING on ``node``, held at ``point``: read in the table, before acting."""
    wait_until(lambda: node.paused(point), 120, f'{node.name} paused at {point}')
    job = _job(cluster, job_id)
    assert job['state'] == 'running' and job['by'] == node.name, job
    if phase is not None:
        assert job['phase'] == phase, job
    return job


def _refused(r):
    """[the answer] when it is the maintenance's 503 (a Response is falsy), None otherwise
    (409 while the node has not yet seen the maintenance)."""
    assert r.status_code in (409, 503), f'{r.status_code} {r.text[:300]}'
    return [r] if r.status_code == 503 else None


def _maintenance(cluster):
    rows = cluster.sql('SELECT phase, node_id FROM cluster_maintenance')
    return rows[0] if rows else None


def _writes_accepted(cluster, label):
    """Every node takes a write again (each view is read again past OBSERVE_TTL_SECONDS)."""
    for node in cluster.nodes:
        client = _login(cluster, node)
        wait_until(lambda: client.post('/api/v2/cas', {
            'type': 'root', 'commonName': f'{label} {node.name}', 'organization': 'HA bench',
            'country': 'US', 'keyAlgo': 'RSA', 'keySize': 2048, 'validityYears': 5,
            'hashAlgorithm': 'sha256'}).status_code in (200, 201),
            3 * OBSERVE_TTL_SECONDS + 30, f'{node.name} accepts writes')


def _back(node):
    """A killed node starts again, with no pause left."""
    node.release()
    node.start()
    wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')


def _epoch(cluster):
    rows = cluster.sql("SELECT value FROM system_config WHERE key = 'session.restore_epoch'")
    return int(rows[0][0]) if rows and rows[0][0] else 0


def _rolling_restart(cluster, nodes):
    """The rolling restart of the live nodes, as their watchers would run it."""
    for node in nodes:
        restart_file = node.data_dir / '.restart_requested'
        wait_until(lambda: restart_file.exists() or not node.alive(), READY_TIMEOUT,
                   f'node {node.name} takes its turn of the rolling restart')
        node.stop()
        restart_file.unlink(missing_ok=True)
        node.start()
        wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')


@pytest.fixture(scope='module')
def archive(cluster):
    """An archive made with 'HA jobs kept CA'; 'HA jobs dropped CA' comes after it."""
    client = _login(cluster, cluster[0])
    create_ca(client, 'HA jobs kept CA')
    r = _backup(client, headers={})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']
    content = client.get(f'/api/v2/system/backup/{name}/download')
    assert content.status_code == 200, content.text[:300]
    create_ca(client, 'HA jobs dropped CA')
    return {'name': name, 'content': content.content}


@pytest.fixture(autouse=True)
def _no_job_left(cluster):
    """A failed test leaves no job running, no pause, no node down, for the next one."""
    yield
    cluster.sql("UPDATE background_jobs SET cancel_requested = true "
                "WHERE state IN ('pending', 'running')")
    for node in cluster.nodes:
        node.release()
    if not _active(cluster) and all(n.alive() for n in cluster.nodes):
        return
    for node in cluster.nodes:
        if not node.alive():
            _back(node)
    wait_until(lambda: not _active(cluster) and _maintenance(cluster) is None,
               MAINTENANCE_LEASE + NOT_TAKEN_SECONDS + MARGIN, 'no job nor maintenance left')


# -- invariants 1, 2 (unbound jobs) and 7 (a backup cancelled from the other node) --

def test_one_active_job_per_slot_on_the_cluster_taken_by_the_leader(cluster, archive):
    leader, follower = _roles(cluster)
    on_leader = _login(cluster, leader)
    on_follower = _login(cluster, follower)
    listed = _backups(on_leader)
    for node in cluster.nodes:
        node.pause('backup-exporting')

    # Asked of the follower, taken by the leader, read the same from both nodes
    job_id = _accepted(_backup(on_follower))
    job = _running_at(cluster, leader, job_id, 'backup-exporting', 'exporting')
    assert job['node_id'] is None and job['secret'] is None
    seen = [c.get(f'/api/v2/system/jobs/{job_id}').json()['data'] for c in (on_leader, on_follower)]
    assert [(s['id'], s['state'], s['kind']) for s in seen] == [(job_id, 'running', 'backup')] * 2

    # The same slot from the other node, and a restore beside it: 409 naming the backup
    _busy(_backup(on_leader), job_id, 'backup')
    _busy(_restore(on_follower, archive), job_id, 'backup')
    assert not list((follower.data_dir / 'tmp').glob('job-*'))  # the refused upload's file went

    # Cancelled from the node that does not run it: no archive is published
    r = _cancel(on_follower, job_id)
    assert r.status_code == 200, r.text[:300]
    for node in cluster.nodes:
        node.release()
    done = _final(cluster, job_id, 60)
    assert (done['state'], done['reason']) == ('cancelled', 'cancelled'), done
    assert _audit_lines(cluster, job_id) == 1
    assert _backups(on_follower) == listed == _backups(on_leader)

    # A verification running on the leader: a restore asked of the follower is refused too
    for node in cluster.nodes:
        node.pause('audit_verify-verifying')
    r = on_follower.http.get(follower.url('/api/v2/audit/verify'), headers=ASYNC, timeout=60)
    verify_id = _accepted(r)
    _running_at(cluster, leader, verify_id, 'audit_verify-verifying')
    _busy(_restore(on_follower, archive), verify_id, 'audit_verify')
    for node in cluster.nodes:
        node.release()
    assert _final(cluster, verify_id, 60)['state'] == 'succeeded'

    # Two starts of one slot at the same instant on two nodes: one job, one 409 naming it
    for node in cluster.nodes:
        node.pause('backup')
    clients, answers, barrier = (on_leader, on_follower), {}, threading.Barrier(2)

    def start(client):
        barrier.wait(10)
        answers[client.node.name] = _backup(client)
    threads = [threading.Thread(target=start, args=(c,)) for c in clients]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(60)
    codes = sorted(r.status_code for r in answers.values())
    assert codes == [202, 409], {n: (r.status_code, r.text[:200]) for n, r in answers.items()}
    won = next(r for r in answers.values() if r.status_code == 202)
    lost = next(r for r in answers.values() if r.status_code == 409)
    winner = _accepted(won)
    _busy(lost, winner, 'backup')
    assert [row[0] for row in _active(cluster)] == [winner]
    _running_at(cluster, leader, winner, 'backup')
    assert _cancel(on_leader, winner).status_code == 200
    for node in cluster.nodes:
        node.release()
    assert _final(cluster, winner, 60)['state'] == 'cancelled'
    assert _backups(on_leader) == listed


# -- invariants 2 (a restore is its receiver's), 1 (503 during a restore) and 7 --

def test_a_restore_is_taken_by_the_follower_that_received_it_and_cancelled_from_the_leader(
        cluster, archive):
    leader, follower = _roles(cluster)
    on_leader = _login(cluster, leader)
    on_follower = _login(cluster, follower)

    # Pending: bound to the follower, which holds the archive; the leader never takes it
    follower.pause('claim')
    pending = _accepted(_restore(on_follower, archive))
    wait_until(lambda: follower.paused('claim'), 60, 'the follower about to take the restore')
    time.sleep(3)  # several passes of the leader's runner
    job = _job(cluster, pending)
    assert (job['state'], job['node_id'], job['executor']) == ('pending', follower.name, None), job
    assert job['secret'] is not None  # encrypted until the take
    archive_file = follower.job_file(f'job-{pending}.archive')
    assert archive_file.exists() and not leader.job_file(archive_file.name).exists()
    # Cancelled from the leader: at once, secret cleared, and the follower's sweep drops the file
    r = _cancel(on_leader, pending)
    assert r.status_code == 200 and r.json()['message'] == 'Job cancelled', r.text[:300]
    done = _job(cluster, pending)
    assert (done['state'], done['secret']) == ('cancelled', None), done
    follower.release('claim')
    wait_until(lambda: not archive_file.exists(), 3 * RECOVER_SECONDS, 'the archive file swept')
    assert _job(cluster, pending)['executor'] is None
    assert _audit_lines(cluster, pending) == 1

    # Running on the follower in the cluster maintenance, before its commit
    follower.pause('restore-applying')
    running = _accepted(_restore(on_follower, archive))
    _running_at(cluster, follower, running, 'restore-applying', 'applying')
    assert _maintenance(cluster) == ('restoring', follower.name)
    # A job asked of either node during the restore: 503 of the maintenance, Retry-After
    for client in (on_leader, on_follower):
        r, = wait_until(lambda: _refused(_backup(client)), 3 * OBSERVE_TTL_SECONDS,
                        f'{client.node.name} refuses a job during the restore')
        assert r.json()['code'] == 'maintenance' and r.headers['Retry-After'] == '30', r.text[:300]
    assert [row[0] for row in _active(cluster)] == [running]
    # Cancelled from the leader, through the maintenance: rolled back, lifted on every node
    r = _cancel(on_leader, running)
    assert r.status_code == 200 and r.json()['message'] == 'Cancellation requested', r.text[:300]
    follower.release('restore-applying')
    done = _final(cluster, running, 120)
    assert (done['state'], done['reason'], done['by']) == ('cancelled', 'cancelled', follower.name), done
    assert _audit_lines(cluster, running) == 1
    wait_until(lambda: _maintenance(cluster) is None, 60, 'the maintenance lifted')
    _writes_accepted(cluster, 'HA jobs after cancel')
    # Nothing was restored
    assert {'HA jobs kept CA', 'HA jobs dropped CA'} <= _cas(_login(cluster, leader))
    assert not follower.job_file(f'job-{running}.archive').exists()


# -- invariants 2 and 8: a restore asked of the follower, then every node serves its state --

def test_a_restore_asked_of_the_follower_is_served_by_every_node_after_it(cluster, archive):
    from tests.ha.cluster import restore_answer
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    before = {node.name: _login(cluster, node).http.cookies.get_dict()
              for node in cluster.nodes}
    epoch = _epoch(cluster)
    answer = restore_answer(on_follower, follower, archive['name'], archive['content'], PASSWORD,
                            cluster, prefer='respond-async')
    assert answer.status_code == 200, answer.text[:1000]
    job_id = answer.accepted.json()['data']['job']['id']
    job = _job(cluster, job_id)
    assert (job['state'], job['phase'], job['by'], job['node_id']) == (
        'succeeded', 'crls_regenerated', follower.name, follower.name), job
    assert _epoch(cluster) == epoch + 1
    _rolling_restart(cluster, cluster.nodes)
    wait_until(lambda: _maintenance(cluster) is None, 120, 'the maintenance lifted')
    for node in cluster.nodes:
        for cookies in before.values():
            assert Client(node, cookies=cookies).get('/api/v2/account/profile').status_code == 401
        again = _login(cluster, node)
        names = _cas(again)
        assert 'HA jobs kept CA' in names and 'HA jobs dropped CA' not in names, (node.name, names)
        seen = again.get(f'/api/v2/system/jobs/{job_id}')
        assert seen.status_code == 200, seen.text[:300]
        assert seen.json()['data']['state'] == 'succeeded'
        assert seen.json()['data']['result']['code'] == 200
    assert _audit_lines(cluster, job_id) == 1


# -- invariant 6: the lead lost without dying --

def _leader_lock_backend(cluster, node):
    rows = cluster.sql(
        "SELECT l.pid, l.classid, l.objid FROM pg_locks l JOIN pg_stat_activity a ON a.pid = l.pid "
        "WHERE l.locktype = 'advisory' AND l.granted AND a.application_name = %s",
        (cluster.app_name(node.name),))
    pids = [pid for pid, c, o in rows if ((int(c) << 32) | int(o)) == LEADER_LOCK_KEY]
    return pids[0] if pids else None


def test_a_job_whose_node_loses_the_lead_ends_on_that_node(cluster):
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    listed = _backups(on_follower)
    for node in cluster.nodes:
        node.pause('backup-exporting')
    job_id = _accepted(_backup(on_follower))
    taken = _running_at(cluster, leader, job_id, 'backup-exporting')

    pid = _leader_lock_backend(cluster, leader)
    assert pid is not None
    cluster.sql('SELECT pg_terminate_backend(%s)', (pid,))
    wait_until(lambda: single_leader(cluster.nodes, settling=True) is follower, TAKEOVER_BOUND + MARGIN,
               'the follower takes the lead')
    # Past the lease the job was taken with: still the old leader's, renewed by it, and alone
    deadline = time.monotonic() + LEASE_SECONDS + 2 * RECOVER_SECONDS
    while time.monotonic() < deadline:
        job = _job(cluster, job_id)
        assert (job['state'], job['executor']) == ('running', taken['executor']), job
        assert [row[0] for row in _active(cluster)] == [job_id]
        time.sleep(5)
    assert single_leader(cluster.nodes) is follower
    for node in cluster.nodes:
        node.release()
    done = _final(cluster, job_id, 120)
    assert (done['state'], done['executor']) == ('succeeded', taken['executor']), done
    assert _audit_lines(cluster, job_id) == 1
    made = json.loads(done['result'])['data']['filename']
    assert _backups(on_follower) == sorted(listed + [made])


# -- invariant 3: the executor is killed --

def test_a_backup_whose_node_dies_ends_executor_lost_and_frees_its_slot(cluster):
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    listed = _backups(on_follower)
    leader.pause('backup-exporting')
    job_id = _accepted(_backup(on_follower))
    _running_at(cluster, leader, job_id, 'backup-exporting', 'exporting')

    leader.kill()
    killed = time.monotonic()
    done = _final(cluster, job_id, LEASE_SECONDS + RECOVER_SECONDS + TAKEOVER_BOUND + MARGIN)
    took = time.monotonic() - killed
    assert (done['state'], done['reason']) == ('failed', 'executor_lost'), done
    assert done['secret'] is None and done['lease'] is None
    assert _audit_lines(cluster, job_id) == 1
    assert _backups(on_follower) == listed  # no partial archive
    print(f'backup concluded executor_lost {took:.0f}s after its node was killed')
    # The slot is free: a new backup runs on the survivor
    r = _backup(on_follower, headers={})
    assert r.status_code == 200, r.text[:500]
    assert _backups(on_follower) == sorted(listed + [r.json()['data']['filename']])
    _back(leader)


# -- invariant 4: the node that received the archive dies before the take, or before the commit --

def test_a_restore_whose_receiver_dies_before_the_take_is_never_taken(cluster, archive):
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    follower.pause('claim')
    job_id = _accepted(_restore(on_follower, archive))
    wait_until(lambda: follower.paused('claim'), 60, 'the follower about to take the restore')
    assert _job(cluster, job_id)['state'] == 'pending'
    created = time.monotonic()
    follower.kill()
    archive_file = follower.job_file(f'job-{job_id}.archive')

    # No maintenance was set: the leader writes meanwhile
    assert _maintenance(cluster) is None
    create_ca(_login(cluster, leader), 'HA jobs while pending')
    done = _final(cluster, job_id, NOT_TAKEN_SECONDS + RECOVER_SECONDS + MARGIN)
    print(f'restore concluded not_taken {time.monotonic() - created:.0f}s after its creation')
    assert (done['state'], done['reason'], done['secret']) == ('failed', 'not_taken', None), done
    assert _audit_lines(cluster, job_id) == 1
    seen = _login(cluster, leader).get(f'/api/v2/system/jobs/{job_id}').json()['data']
    assert seen['state'] == 'failed' and seen['reason'] == 'not_taken'
    # Its file stays on the dead node's disk until the node's first pass
    assert archive_file.exists()
    _back(follower)
    wait_until(lambda: not archive_file.exists(), 3 * RECOVER_SECONDS, 'the archive file swept at return')


def test_a_restore_whose_receiver_dies_before_the_commit_fails_and_lifts_the_maintenance(
        cluster, archive):
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    follower.pause('restore-applying')
    job_id = _accepted(_restore(on_follower, archive))
    _running_at(cluster, follower, job_id, 'restore-applying', 'applying')
    assert _maintenance(cluster) == ('restoring', follower.name)
    archive_file = follower.job_file(f'job-{job_id}.archive')

    follower.kill()
    killed = time.monotonic()
    done = _final(cluster, job_id, MAINTENANCE_LEASE + RECOVER_SECONDS + TAKEOVER_BOUND + MARGIN)
    took = time.monotonic() - killed
    assert (done['state'], done['reason']) == ('failed', 'executor_lost'), done
    assert _audit_lines(cluster, job_id) == 1
    assert _maintenance(cluster) is None
    print(f'restore concluded executor_lost {took:.0f}s after its node was killed in the maintenance')
    on_leader = _login(cluster, leader)
    seen = on_leader.get(f'/api/v2/system/jobs/{job_id}').json()['data']
    assert seen['reason'] == 'executor_lost'
    create_ca(on_leader, 'HA jobs after a lost restore')  # no node stays in 503
    assert 'HA jobs after a lost restore' in _cas(on_leader)
    assert archive_file.exists()
    _back(follower)
    wait_until(lambda: not archive_file.exists(), 3 * RECOVER_SECONDS, 'the archive file swept at return')
    _writes_accepted(cluster, 'HA jobs after the return')


# -- invariant 5: the executor dies after the commit, before the end steps --

def test_a_restore_whose_node_dies_after_its_commit_is_finished_once(cluster, archive):
    leader, follower = _roles(cluster)
    on_follower = _login(cluster, follower)
    before = _login(cluster, leader)
    create_ca(before, 'HA jobs replaced CA')
    before = before.http.cookies.get_dict()
    epoch = _epoch(cluster)
    follower.pause('restore-finish')
    job_id = _accepted(_restore(on_follower, archive))
    wait_until(lambda: follower.paused('restore-finish'), 120, 'the restore committed')
    job = _job(cluster, job_id)
    assert (job['state'], job['phase'], job['by']) == ('running', 'committed', follower.name), job
    assert _maintenance(cluster) == ('committed', follower.name)

    follower.kill()
    killed = time.monotonic()
    # The maintenance's lease ends: the survivor revokes the sessions (once) and asks the restart
    wait_until(lambda: (_maintenance(cluster) or ('',))[0] == 'restarting',
               MAINTENANCE_LEASE + MARGIN, 'the committed restore completed by the survivor')
    completed = time.monotonic() - killed
    assert _job(cluster, job_id)['phase'] == 'sessions_revoked'
    assert _epoch(cluster) == epoch + 1
    _rolling_restart(cluster, [leader])
    done = _final(cluster, job_id, LEASE_SECONDS + RECOVER_SECONDS + MARGIN)
    took = time.monotonic() - killed
    assert (done['state'], done['phase'], done['by']) == ('succeeded', 'crls_regenerated', leader.name), done
    assert json.loads(done['result'])['code'] == 200
    assert _epoch(cluster) == epoch + 1  # the recovery found it advanced: not twice
    assert _audit_lines(cluster, job_id) == 1
    wait_until(lambda: _maintenance(cluster) is None, 120, 'the maintenance lifted')
    print(f'committed restore: completed {completed:.0f}s, concluded {took:.0f}s after its node was killed')
    archive_file = follower.job_file(f'job-{job_id}.archive')
    assert archive_file.exists()
    _back(follower)
    wait_until(lambda: not archive_file.exists(), 3 * RECOVER_SECONDS, 'the archive file swept at return')
    assert _job(cluster, job_id)['by'] == leader.name  # the returning node ran nothing again
    for node in cluster.nodes:
        assert Client(node, cookies=before).get('/api/v2/account/profile').status_code == 401
        names = _cas(_login(cluster, node))
        assert 'HA jobs kept CA' in names and 'HA jobs replaced CA' not in names, (node.name, names)
