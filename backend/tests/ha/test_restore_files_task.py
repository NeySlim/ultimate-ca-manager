"""A restore made on A, nodes with directories of their own: the cluster stays in
maintenance until its rolling restart, so no node's files move before it; at its turn B
rewrites a PEM that differs and deletes the file of a removed row in its own directory."""
import base64

import pytest

from tests.ha.cluster import READY_TIMEOUT, create_ca, issue, restore_answer, wait_until
from tests.ha.test_restore_files import _cert_names, _crt_files, _matches

pytestmark = pytest.mark.ha

PASSWORD = 'ha-bench-restore-files-task-2026'


def test_each_node_reconciles_its_own_directories_at_its_restart(cluster, admin):
    a, b = cluster.nodes[:2]
    on_b = admin.on(b)
    ca = create_ca(admin, 'HA restore files task CA')
    kept = issue(on_b, ca['id'], 'kept.files-task.ucm-ha.test')
    r = admin.post('/api/v2/system/backup', {'password': PASSWORD})
    assert r.status_code == 200, r.text[:500]
    name = r.json()['data']['filename']
    archive = admin.get(f'/api/v2/system/backup/{name}/download')
    assert archive.status_code == 200, archive.text[:300]

    removed = issue(on_b, ca['id'], 'removed.files-task.ucm-ha.test')
    wait_until(lambda: any(n.startswith('removed.files-task') for n in _crt_files(b)),
               60, 'B writes the file of the certificate issued after the archive')
    removed_name = next(n for n in _crt_files(b) if n.startswith('removed.files-task'))
    kept_name = next(n for n in _cert_names(cluster) if n.startswith('kept.files-task'))
    (b.data_dir / 'certs' / kept_name).write_bytes(b'differs from the row')
    assert not (b.data_dir / 'certs').is_symlink()

    def restore():
        found = restore_answer(admin, a, name, archive.content, PASSWORD, cluster)
        if found.status_code == 409 and 'maintenance_not_acknowledged' in found.text:
            return None
        if found.status_code == 503:  # the refused attempt's maintenance, not yet seen lifted here
            return None
        return [found]
    (r,) = wait_until(restore, 240, 'the restore acknowledged by every node')
    assert r.status_code == 200, r.text[:1000]
    assert r.json()['data']['files']['removals'] >= 1
    wanted = base64.b64decode(cluster.sql('SELECT crt FROM certificates WHERE id = %s',
                                          (kept['id'],))[0][0])
    # Until its restart B serves nothing new: its own files have not moved
    assert (b.data_dir / 'certs' / kept_name).read_bytes() == b'differs from the row'
    assert removed_name in _crt_files(b)

    # The rolling restart, one node at a time
    for node in cluster.nodes:
        node.stop()
        (node.data_dir / '.restart_requested').unlink(missing_ok=True)
        node.start()
        wait_until(node.ready, READY_TIMEOUT, f'node {node.name} ready again')
    for node in cluster.nodes:
        wait_until(lambda node=node: _matches(node, cluster), 60,
                   f'{node.name} follows the restore')
        assert removed_name not in _crt_files(node), node.name
    assert (b.data_dir / 'certs' / kept_name).read_bytes() == wanted
    assert not (b.data_dir / 'certs').is_symlink()
    assert removed['id']
