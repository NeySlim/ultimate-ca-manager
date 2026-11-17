"""A backup asked of one node is made by the leader, listed the same on both, downloads from the
other byte for byte, still does once its node is gone, and retention runs on the leader alone."""
import base64
import hashlib

import pytest

from tests.ha.cluster import task_runs, wait_until

pytestmark = pytest.mark.ha

PASSWORD = 'ha-bench-backup-2026'


def _listing(client):
    r = client.get('/api/v2/system/backups?per_page=100')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:500]}'
    return r.json()['data']


def _leader(nodes):
    leaders = [node for node in nodes if node.health()['leader'] is True]
    return leaders[0] if len(leaders) == 1 else None


def test_a_backup_asked_of_a_follower_is_made_by_the_leader_and_downloads_after_it_is_gone(cluster, admin):
    a, b = cluster.nodes
    # A manual backup is a background job: the leader makes it, whichever node is asked
    writer = wait_until(lambda: _leader(cluster.nodes), 60, 'one leader')
    other = b if writer is a else a
    on_other = admin.on(other)
    r = on_other.post('/api/v2/system/backup', {'password': PASSWORD})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']

    seen_writer, seen_other = _listing(admin.on(writer)), _listing(on_other)
    assert seen_writer['items'] == seen_other['items']
    (item,) = [i for i in seen_other['items'] if i['filename'] == name]
    assert item['node'] == writer.name and seen_other['meta']['storage'] == 'database'

    # Retention asked on either node runs once, on the leader
    leader = wait_until(lambda: _leader(cluster.nodes), 60, 'one leader')
    follower = b if leader is a else a
    r = admin.on(follower).post('/api/v2/system/scheduler/backup_retention/run')
    assert r.status_code == 200, r.text[:500]
    assert task_runs(follower.app_log_text(), 'backup_retention') == 0
    assert task_runs(leader.app_log_text(), 'backup_retention') >= 1

    # Resumed at mid-archive from the other node, through gunicorn's own wsgi.file_wrapper
    url = f'/api/v2/system/backup/{name}/download'
    cut = item['size_bytes'] // 2
    first = on_other.get(url, headers={'Range': f'bytes=0-{cut - 1}'})
    rest = on_other.get(url, headers={'Range': f'bytes={cut}-', 'If-Range': f'"{item["sha256"]}"'})
    assert (first.status_code, rest.status_code) == (206, 206), (first.text[:200], rest.text[:200])
    assert rest.headers['Content-Range'] == f'bytes {cut}-{item["size_bytes"] - 1}/{item["size_bytes"]}'
    assert hashlib.sha256(first.content + rest.content).hexdigest() == item['sha256']

    writer.kill()
    wait_until(lambda: not writer.alive(), 30, f'{writer.name} gone')
    r = on_other.get(url)
    assert r.status_code == 200, r.text[:500]
    assert hashlib.sha256(r.content).hexdigest() == item['sha256']
    assert len(r.content) == item['size_bytes']
    assert r.headers['Repr-Digest'] == (
        'sha-256=:' + base64.b64encode(hashlib.sha256(r.content).digest()).decode() + ':')
    assert r.content[:4] == b'UCMB'
