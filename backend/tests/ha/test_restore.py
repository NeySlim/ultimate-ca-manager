"""A restore launched on node A while node B issues certificates: it starts once every node
acknowledged the maintenance, B refuses from its acknowledgement on, every node restarts in
turn, then B serves the restored state and accepts writes again."""
import threading
import time

import pytest
import requests

from services.cluster_maintenance import OBSERVE_TTL_SECONDS
from tests.ha.cluster import READY_TIMEOUT, Client, create_ca, issue, node_counts, wait_until

pytestmark = [pytest.mark.ha, node_counts(2, 3)]

PASSWORD = 'ha-bench-restore-2026'


def _cas(client):
    """{name: id} of the authorities the node serves."""
    r = client.get('/api/v2/cas?per_page=100')
    assert r.status_code == 200, f'{client.node.name}: {r.status_code} {r.text[:300]}'
    data = r.json()['data']
    items = data if isinstance(data, list) else data.get('items', [])
    return {ca.get('descr') or ca.get('common_name'): ca['id'] for ca in items}


def test_a_restore_on_a_while_b_writes(cluster, admin):
    a, b = cluster.nodes[:2]
    before = create_ca(admin, 'HA restore kept CA')
    r = admin.post('/api/v2/system/backup', {'password': PASSWORD})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']
    archive = admin.get(f'/api/v2/system/backup/{name}/download')
    assert archive.status_code == 200, archive.text[:300]

    on_b = admin.on(b)
    create_ca(on_b, 'HA restore dropped CA')
    outcomes, stop = [], threading.Event()

    def write_on_b():
        n = 0
        while not stop.is_set():
            n += 1
            try:
                r = on_b.post('/api/v2/certificates', {'cn': f'w{n}.ucm-ha.test',
                                                         'ca_id': before['id'], 'validity_days': 30})
                outcomes.append((time.monotonic(), r.status_code, r.headers.get('Retry-After')))
            except requests.RequestException:
                outcomes.append((time.monotonic(), None, None))
            time.sleep(0.1)
    writer = threading.Thread(target=write_on_b)
    writer.start()
    try:
        wait_until(lambda: any(code in (200, 201) for _, code, _ in outcomes), 60, 'B issues')
        started = time.monotonic()
        r = admin.http.post(a.url('/api/v2/system/restore'), headers=admin._headers(),
                            files={'file': (name, archive.content)}, data={'password': PASSWORD},
                            timeout=300)
        assert r.status_code == 200, r.text[:1000]
        restored_in = time.monotonic() - started
        assert r.json()['data']['restart_requested'] is True
        time.sleep(1)
    finally:
        stop.set()
        writer.join(30)

    codes = [code for _, code, _ in outcomes]
    first = codes.index(503)
    # From B's acknowledgement on, every write was refused, with a delay to retry after
    assert set(codes[first:]) == {503}, codes
    assert all(retry == '30' for _, code, retry in outcomes if code == 503)
    for node in cluster.nodes[1:]:
        assert node.ready() is None, node.name  # out of the load balancer's rotation
        # Each process reads the row again once its view is older than OBSERVE_TTL_SECONDS
        wait_until(lambda: node.health()['maintenance']['phase'] == 'restarting',
                   3 * OBSERVE_TTL_SECONDS, f'node {node.name} shows the restore as done')

    # The rolling restart, as the watchers would run it: node A, then B (then C)
    for node in cluster.nodes:
        restart_file = node.data_dir / '.restart_requested'
        wait_until(lambda: restart_file.exists() or not node.alive(), READY_TIMEOUT,
                   f'node {node.name} takes its turn of the rolling restart')
        node.stop()
        restart_file.unlink(missing_ok=True)
        node.start()
        wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')

    wait_until(lambda: all(n.health().get('maintenance') is None for n in cluster.nodes), 60,
               'the maintenance lifted on every node')
    # Lifted once every fresh heartbeat carries a start after the restore
    serving = time.monotonic()
    wait_until(lambda: cluster.sql('SELECT count(*) FROM cluster_maintenance')[0][0] == 0, 120,
               'the maintenance row removed')
    lifted_in = time.monotonic() - serving
    # The sessions of before are gone; B serves the restored state and accepts writes
    again = Client.login(b, cluster.password)
    names = _cas(again)
    assert 'HA restore kept CA' in names and 'HA restore dropped CA' not in names, names
    issue(again, names['HA restore kept CA'], 'after-restore.ucm-ha.test')
    print(f'restore with acknowledgements: {restored_in:.1f}s; B refused from write {first} '
          f'of {len(codes)}; row removed {lifted_in:.1f}s after both nodes served')
