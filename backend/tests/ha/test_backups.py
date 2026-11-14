"""A backup taken on one node is listed the same on both, downloads from the other byte for
byte, still does once its node is gone, and retention runs on the leader alone."""
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


def test_a_backup_on_a_is_listed_on_b_and_downloads_after_a_is_gone(cluster, admin):
    a, b = cluster.nodes
    r = admin.post('/api/v2/system/backup', {'password': PASSWORD})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']

    on_b = admin.on(b)
    seen_a, seen_b = _listing(admin), _listing(on_b)
    assert seen_a['items'] == seen_b['items']
    (item,) = [i for i in seen_b['items'] if i['filename'] == name]
    assert item['node'] == a.name and seen_b['meta']['storage'] == 'database'

    # Retention asked on either node runs once, on the leader
    leader = wait_until(lambda: _leader(cluster.nodes), 60, 'one leader')
    follower = b if leader is a else a
    r = admin.on(follower).post('/api/v2/system/scheduler/backup_retention/run')
    assert r.status_code == 200, r.text[:500]
    assert task_runs(follower.app_log_text(), 'backup_retention') == 0
    assert task_runs(leader.app_log_text(), 'backup_retention') >= 1

    # Resumed at mid-archive from B, through gunicorn's own wsgi.file_wrapper
    url = f'/api/v2/system/backup/{name}/download'
    cut = item['size_bytes'] // 2
    first = on_b.get(url, headers={'Range': f'bytes=0-{cut - 1}'})
    rest = on_b.get(url, headers={'Range': f'bytes={cut}-', 'If-Range': f'"{item["sha256"]}"'})
    assert (first.status_code, rest.status_code) == (206, 206), (first.text[:200], rest.text[:200])
    assert rest.headers['Content-Range'] == f'bytes {cut}-{item["size_bytes"] - 1}/{item["size_bytes"]}'
    assert hashlib.sha256(first.content + rest.content).hexdigest() == item['sha256']

    a.kill()
    wait_until(lambda: not a.alive(), 30, f'{a.name} gone')
    r = on_b.get(url)
    assert r.status_code == 200, r.text[:500]
    assert hashlib.sha256(r.content).hexdigest() == item['sha256']
    assert len(r.content) == item['size_bytes']
    assert r.headers['Repr-Digest'] == (
        'sha-256=:' + base64.b64encode(hashlib.sha256(r.content).digest()).decode() + ':')
    assert r.content[:4] == b'UCMB'
